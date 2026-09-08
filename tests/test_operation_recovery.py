import copy
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend import mod_ops, operation_recovery, storage


class OperationRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        patches = patch.multiple(storage, MODS_JSON=str(self.root / "mods.json"),
                                 SETTINGS_FILE=str(self.root / "settings.json"),
                                 STORAGE_DIR=str(self.root / "library"), BACKUPS_DIR=str(self.root / "backups"))
        patches.start()
        self.addCleanup(patches.stop)
        storage.ensure_dirs()
        settings = storage.load_settings()
        settings["mods_path"] = str(self.root / "game")
        storage.save_settings(settings)
        game_guard = patch.object(mod_ops, "_ensure_game_operation_allowed")
        game_guard.start()
        self.addCleanup(game_guard.stop)
        paths = patch.object(mod_ops, "_paths_from_bundle", return_value=["Marvel/Content/Meshes/SK_Hero.uasset"])
        paths.start()
        self.addCleanup(paths.stop)
        self.source = self.root / "Hero.pak"
        self.source.write_bytes(b"original mod bytes")
        self.archive = self.root / "Hero.zip"
        self.archive.write_bytes(b"original archive bytes")

    def install(self):
        return mod_ops.add_mod([str(self.source)], {"name": "Hero", "character": "Hela",
                                                   "archive_paths": [str(self.archive)]})

    def interrupted(self, kind):
        journals = [entry for entry in storage.list_operation_journals()
                    if entry.get("kind") == kind and entry.get("phase") not in {"completed", "recovered", "aborted", "cancelled"}]
        self.assertEqual(len(journals), 1)
        journal = operation_recovery.Journal.load(journals[0]["id"])
        journal.release()  # Uma nova instância não tem o registro em memória.
        return journal

    def active_path(self, record):
        return pathlib.Path(mod_ops._game_target_dir(record, str(self.root / "game"))) / record["files"][0]["name"]

    def profile(self, record):
        settings = storage.load_settings()
        target = mod_ops._snapshot_mod_states([record])[0]
        target.update(enabled=False, priority=8)
        settings["profiles"] = [{"id": "profile", "name": "Desligado", "mods": [target]}]
        storage.save_settings(settings)

    def test_interrupted_staging_never_changes_catalog_or_sources(self):
        def interrupted_copy(source, destination, **kwargs):
            pathlib.Path(destination).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(destination).write_bytes(b"partial")
            raise SystemExit("process ended during copy")
        with patch.object(mod_ops.operation_jobs, "copy_file", side_effect=interrupted_copy):
            with self.assertRaises(SystemExit):
                self.install()
        journal = self.interrupted("import")
        self.assertFalse(journal.data["mutation_started"])
        self.assertEqual(storage.load_mods(), [])
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertFalse((pathlib.Path(journal.root) / "payload").exists())
        self.assertEqual(self.source.read_bytes(), b"original mod bytes")
        self.assertEqual(self.archive.read_bytes(), b"original archive bytes")

    def test_import_crash_before_catalog_save_restores_game_and_removes_only_new_storage(self):
        with patch.object(storage, "save_mods", side_effect=SystemExit("process ended before save")):
            with self.assertRaises(SystemExit):
                self.install()
        journal = self.interrupted("import")
        staged_record = journal.data["after_records"][0]
        active = self.active_path(staged_record)
        self.assertTrue(active.exists())
        self.assertEqual(storage.load_mods(), [])
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertFalse(active.exists())
        self.assertFalse(pathlib.Path(mod_ops._storage_dir(staged_record)).exists())
        self.assertTrue(self.source.exists())
        self.assertTrue(self.archive.exists())
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["already_recovered"])

    def test_import_crash_after_catalog_save_can_be_rolled_back(self):
        original_mark = operation_recovery.Journal.mark
        def crash(journal, phase):
            if phase == "catalog_saved":
                raise SystemExit("process ended after save")
            return original_mark(journal, phase)
        with patch.object(operation_recovery.Journal, "mark", new=crash):
            with self.assertRaises(SystemExit):
                self.install()
        journal = self.interrupted("import")
        self.assertEqual(len(storage.load_mods()), 1)
        self.assertEqual(len(operation_recovery.list_pending()), 1)
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertEqual(storage.load_mods(), [])
        self.assertEqual(operation_recovery.list_pending(), [])
        self.assertTrue(self.archive.exists())

    def test_success_finishes_journal_and_discards_large_temporary_files(self):
        record = self.install()
        self.assertEqual(self.active_path(record).read_bytes(), self.source.read_bytes())
        journals = storage.list_operation_journals()
        self.assertEqual([entry["phase"] for entry in journals], ["completed"])
        root = pathlib.Path(storage.operation_dir(journals[0]["id"]))
        self.assertFalse((root / "payload").exists())
        self.assertFalse((root / "files").exists())
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_profile_crash_before_save_restores_files_even_when_catalog_still_says_enabled(self):
        record = self.install()
        self.profile(record)
        before = copy.deepcopy(storage.load_mods())
        with patch.object(storage, "save_mods", side_effect=SystemExit("process ended")):
            with self.assertRaises(SystemExit):
                mod_ops.apply_profile("profile")
        journal = self.interrupted("profile")
        self.assertFalse(self.active_path(record).exists())
        self.assertEqual(storage.load_mods(), before)
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertEqual(self.active_path(record).read_bytes(), self.source.read_bytes())
        self.assertEqual(storage.load_mods(), before)

    def test_profile_crash_after_save_restores_settings_and_preserves_independent_edits(self):
        record = self.install()
        self.profile(record)
        before_snapshot = storage.load_settings()["last_recovery_snapshot"]
        original_mark = operation_recovery.Journal.mark
        def crash(journal, phase):
            if phase == "catalog_saved":
                raise SystemExit("process ended after both JSON saves")
            return original_mark(journal, phase)
        with patch.object(operation_recovery.Journal, "mark", new=crash):
            with self.assertRaises(SystemExit):
                mod_ops.apply_profile("profile")
        journal = self.interrupted("profile")
        self.assertFalse(storage.load_mods()[0]["enabled"])
        self.assertIsNotNone(storage.load_settings()["last_recovery_snapshot"])
        current = storage.load_mods()
        current[0]["name"] = "Renamed after restart"
        storage.save_mods(current)
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        current = storage.load_mods()[0]
        self.assertEqual(current["name"], "Renamed after restart")
        self.assertTrue(current["enabled"])
        self.assertEqual(current["priority"], 1)
        self.assertEqual(storage.load_settings()["last_recovery_snapshot"], before_snapshot)
        self.assertEqual(self.active_path(record).read_bytes(), self.source.read_bytes())

    def test_profile_save_error_rolls_back_without_leaving_a_pending_operation(self):
        record = self.install()
        self.profile(record)
        before = storage.load_mods()
        original_save = storage.save_mods
        calls = 0
        def fail_once(mods):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("disk full")
            return original_save(mods)
        with patch.object(storage, "save_mods", side_effect=fail_once):
            result = mod_ops.apply_profile("profile")
        self.assertFalse(result["ok"])
        self.assertEqual(storage.load_mods(), before)
        self.assertTrue(self.active_path(record).exists())
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_game_lock_keeps_recovery_pending_without_touching_files(self):
        record = self.install()
        self.profile(record)
        with patch.object(storage, "save_mods", side_effect=SystemExit("process ended")):
            with self.assertRaises(SystemExit):
                mod_ops.apply_profile("profile")
        journal = self.interrupted("profile")
        with patch.object(mod_ops, "_ensure_game_operation_allowed", side_effect=OSError("Jogo aberto")):
            result = mod_ops.recover_interrupted_operation(journal.id)
        self.assertFalse(result["ok"])
        self.assertIn("Jogo aberto", result["error"])
        self.assertFalse(self.active_path(record).exists())
        self.assertEqual(len(operation_recovery.list_pending()), 1)
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])

    def test_recovery_refuses_changes_to_the_same_operational_field(self):
        record = self.install()
        self.profile(record)
        with patch.object(storage, "save_mods", side_effect=SystemExit("process ended")):
            with self.assertRaises(SystemExit):
                mod_ops.apply_profile("profile")
        journal = self.interrupted("profile")
        mods = storage.load_mods()
        mods[0]["priority"] = 4
        storage.save_mods(mods)
        result = mod_ops.recover_interrupted_operation(journal.id)
        self.assertFalse(result["ok"])
        self.assertEqual(storage.load_mods()[0]["priority"], 4)
        self.assertFalse(self.active_path(record).exists())
        self.assertEqual(len(operation_recovery.list_pending()), 1)

    def test_tampered_recovery_path_cannot_remove_an_unrelated_file(self):
        with patch.object(storage, "save_mods", side_effect=SystemExit("process ended")):
            with self.assertRaises(SystemExit):
                self.install()
        journal = self.interrupted("import")
        unrelated = self.root / "keep.txt"
        unrelated.write_bytes(b"keep")
        journal.data["files"].append({"path": str(unrelated), "root": str(self.root), "existed": False})
        journal.save()
        self.assertFalse(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertEqual(unrelated.read_bytes(), b"keep")

    def test_changed_library_path_is_rejected_before_any_restore(self):
        with patch.object(storage, "save_mods", side_effect=SystemExit("process ended")):
            with self.assertRaises(SystemExit):
                self.install()
        journal = self.interrupted("import")
        record = journal.data["after_records"][0]
        active = self.active_path(record)
        private = pathlib.Path(mod_ops._storage_dir(record))
        with patch.object(storage, "STORAGE_DIR", str(self.root / "another-library")):
            result = mod_ops.recover_interrupted_operation(journal.id)
        self.assertFalse(result["ok"])
        self.assertIn("biblioteca mudou", result["error"])
        self.assertTrue(active.exists())
        self.assertTrue(private.exists())
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])

    def test_tampered_owned_directory_is_rejected_before_removing_active_files(self):
        with patch.object(storage, "save_mods", side_effect=SystemExit("process ended")):
            with self.assertRaises(SystemExit):
                self.install()
        journal = self.interrupted("import")
        record = journal.data["after_records"][0]
        unrelated = pathlib.Path(storage.STORAGE_DIR) / "unregistered-library-archive"
        unrelated.mkdir()
        (unrelated / "keep.zip").write_bytes(b"preserve")
        journal.data["owned_dirs"].append(str(unrelated))
        journal.save()
        self.assertFalse(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertTrue(self.active_path(record).exists())
        self.assertEqual((unrelated / "keep.zip").read_bytes(), b"preserve")

    def test_profile_external_backup_is_not_overwritten_and_recovers_original_bytes(self):
        record = self.install()
        private = pathlib.Path(mod_ops._storage_dir(record)) / record["files"][0]["name"]
        private_bytes = private.read_bytes()
        active = self.active_path(record)
        active.unlink()
        active.write_bytes(b"different active external package")
        active_bytes = active.read_bytes()
        mods = storage.load_mods()
        mods[0]["external"] = True
        storage.save_mods(mods)
        self.profile(mods[0])
        with patch.object(storage, "save_mods", side_effect=SystemExit("process ended")):
            with self.assertRaises(SystemExit):
                mod_ops.apply_profile("profile")
        journal = self.interrupted("profile")
        self.assertEqual(private.read_bytes(), private_bytes)
        self.assertFalse(active.exists())
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertEqual(private.read_bytes(), private_bytes)
        self.assertEqual(active.read_bytes(), active_bytes)
        self.assertTrue(storage.load_mods()[0]["external"])

    def test_external_component_switch_backs_up_files_missing_from_top_level_list(self):
        game = self.root / "game" / "external"
        (game / "main").mkdir(parents=True)
        (game / "variation").mkdir()
        (game / "main" / "Hero.pak").write_bytes(b"main")
        (game / "variation" / "Hero.pak").write_bytes(b"variation")
        main_file = {"name": str(pathlib.Path("main") / "Hero.pak")}
        variation_file = {"name": str(pathlib.Path("variation") / "Hero.pak")}
        record = {"id": "external", "name": "External", "folder": "external", "external": True,
                  "enabled": True, "files": [main_file], "components": [
                      {"id": "main", "name": "Main", "files": [main_file], "enabled": True},
                      {"id": "variation", "name": "Variation", "files": [variation_file], "enabled": True}]}
        storage.save_mods([record])
        result = mod_ops.toggle_component("external", "variation")
        self.assertTrue(result["ok"], result)
        record = storage.load_mods()[0]
        private = pathlib.Path(mod_ops._storage_dir(record))
        self.assertEqual((private / main_file["name"]).read_bytes(), b"main")
        self.assertEqual((private / variation_file["name"]).read_bytes(), b"variation")
        self.assertFalse((game / variation_file["name"]).exists())
        self.assertTrue(mod_ops.toggle_component("external", "variation")["ok"])
        self.assertEqual((game / variation_file["name"]).read_bytes(), b"variation")

    def test_external_component_switch_accepts_existing_backup_hardlink(self):
        record = self.install()
        mods = storage.load_mods()
        mods[0]["external"] = True
        storage.save_mods(mods)
        result = mod_ops.toggle_component(record["id"], record["components"][0]["id"])
        self.assertTrue(result["ok"], result)
        self.assertFalse(self.active_path(record).exists())
        private = pathlib.Path(mod_ops._storage_dir(record)) / record["files"][0]["name"]
        self.assertEqual(private.read_bytes(), self.source.read_bytes())

    def test_missing_backup_refuses_disable_before_removing_the_only_active_copy(self):
        record = self.install()
        private = pathlib.Path(mod_ops._storage_dir(record)) / record["files"][0]["name"]
        private.unlink()
        result = mod_ops.toggle_component(record["id"], record["components"][0]["id"])
        self.assertFalse(result["ok"])
        self.assertEqual(self.active_path(record).read_bytes(), self.source.read_bytes())
        self.assertTrue(storage.load_mods()[0]["components"][0]["enabled"])

    def test_failed_recovery_can_be_repeated_without_losing_snapshots(self):
        original_mark = operation_recovery.Journal.mark
        def crash(journal, phase):
            if phase == "catalog_saved":
                raise SystemExit("process ended after save")
            return original_mark(journal, phase)
        with patch.object(operation_recovery.Journal, "mark", new=crash):
            with self.assertRaises(SystemExit):
                self.install()
        journal = self.interrupted("import")
        record = storage.load_mods()[0]
        with patch.object(storage, "save_mods", side_effect=OSError("disk temporarily unavailable")):
            self.assertFalse(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertFalse(self.active_path(record).exists())
        self.assertTrue(pathlib.Path(mod_ops._storage_dir(record)).exists())
        self.assertEqual(len(operation_recovery.list_pending()), 1)
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertEqual(storage.load_mods(), [])
        self.assertFalse(pathlib.Path(mod_ops._storage_dir(record)).exists())

    def test_another_process_cannot_recover_a_live_import(self):
        code = """import sys
from backend import operation_recovery, storage
storage.BACKUPS_DIR, storage.STORAGE_DIR = sys.argv[1:3]
journal = operation_recovery.Journal.create('import', 'Live import')
print(journal.id, flush=True)
sys.stdin.readline()
journal.finish('cancelled')
"""
        process = subprocess.Popen([sys.executable, "-c", code, storage.BACKUPS_DIR, storage.STORAGE_DIR],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        def cleanup():
            if process.poll() is None:
                process.kill()
            process.communicate()
        self.addCleanup(cleanup)
        operation_id = process.stdout.readline().strip()
        self.assertTrue(operation_id)
        self.assertTrue(operation_recovery.is_live(operation_id))
        self.assertEqual(operation_recovery.list_pending(), [])
        with self.assertRaisesRegex(ValueError, "outra instância"):
            operation_recovery.Journal.load(operation_id, resume=True)
        self.assertFalse(mod_ops.recover_interrupted_operation(operation_id)["ok"])
        process.communicate("\n", timeout=10)
        self.assertEqual(process.returncode, 0)
        self.assertFalse(operation_recovery.is_live(operation_id))


if __name__ == "__main__":
    unittest.main()
