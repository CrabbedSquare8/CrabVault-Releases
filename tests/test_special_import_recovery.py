import copy
import os
import pathlib
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend import mod_ops, operation_jobs, operation_recovery, special_imports, storage


class SpecialImportRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        patches = patch.multiple(storage, MODS_JSON=str(self.root / "mods.json"), SETTINGS_FILE=str(self.root / "settings.json"),
                                 STORAGE_DIR=str(self.root / "library"), BACKUPS_DIR=str(self.root / "backups"))
        patches.start()
        self.addCleanup(patches.stop)
        storage.ensure_dirs()
        self.marvel = self.root / "game" / "Marvel"
        self.game = self.marvel / "Content" / "Paks" / "~mods"
        self.win64 = self.marvel / "Binaries" / "Win64"
        self.content = self.marvel / "Content" / "Marvel"
        self.movies = self.content / "MoviesBink"
        for folder in (self.game, self.win64, self.movies):
            folder.mkdir(parents=True, exist_ok=True)
        settings = storage.load_settings()
        settings["mods_path"] = str(self.game)
        storage.save_settings(settings)
        guard = patch.object(mod_ops, "_ensure_game_operation_allowed")
        self.guard = guard.start()
        self.addCleanup(guard.stop)
        self.addCleanup(self.release_journals)
        (self.movies / "Intro.bk2").write_bytes(b"original intro")
        (self.movies / "Unrelated.bk2").write_bytes(b"unrelated cinematic")
        (self.win64 / "dxgi.dll").write_bytes(b"original dll")
        (self.win64 / "game.exe").write_bytes(b"unrelated executable")

    def release_journals(self):
        for item in storage.list_operation_journals():
            operation_recovery.Journal.load(item["id"]).release()

    def source(self, name, data=b"modded content"):
        path = self.root / "sources" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def install_reshade(self, **meta):
        source = self.source("dxgi.dll")
        return mod_ops.add_reshade_mod([source], {"name": "Preset", **meta})

    def install_background(self, **meta):
        source = self.source("Intro.bk2")
        return mod_ops.add_background_mod([source], {"name": "Cinematics", "relative_paths": {os.path.normcase(source): "MoviesBink/Intro.bk2"}, **meta})

    def interrupted(self):
        entries = [item for item in storage.list_operation_journals() if item["phase"] not in {"completed", "cancelled", "aborted", "recovered"}]
        self.assertEqual(len(entries), 1)
        journal = operation_recovery.Journal.load(entries[0]["id"])
        journal.release()
        return journal

    def wait(self, job_id):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            result = operation_jobs.get_status(job_id)
            if result.get("state") in {"completed", "failed", "cancelled"}:
                return result
            time.sleep(0.01)
        self.fail("worker did not finish")

    def test_success_reshade_keeps_tree_hashes_sources_and_unrelated_files(self):
        shader = self.source("nested/Effect.fx", b"shader")
        dll = self.source("dxgi.dll", b"reshade")
        archive1 = self.source("first/preset.zip", b"first archive")
        archive2 = self.source("second/preset.zip", b"second archive")
        record = mod_ops.add_reshade_mod([dll, shader], {"name": "Preset", "archive_paths": [archive1, archive2],
                                                       "relative_paths": {os.path.normcase(shader): "reshade-shaders/Shaders/Effect.fx"}})
        private = pathlib.Path(mod_ops._storage_dir(record))
        self.assertEqual((self.win64 / "dxgi.dll").read_bytes(), b"reshade")
        self.assertEqual((self.win64 / "reshade-shaders/Shaders/Effect.fx").read_bytes(), b"shader")
        self.assertEqual((self.win64 / "game.exe").read_bytes(), b"unrelated executable")
        self.assertEqual([str(len(entry["sha256"])) for entry in record["files"]], ["64", "64"])
        self.assertEqual([ (private / name).read_bytes() for name in record["archives"] ], [b"first archive", b"second archive"])
        self.assertTrue(pathlib.Path(dll).exists())
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_reshade_failure_rolls_back_exact_bytes_and_catalog(self):
        original_save = storage.save_mods
        calls = 0
        def fail_once(mods):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("disk full")
            return original_save(mods)
        with patch.object(storage, "save_mods", side_effect=fail_once):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.install_reshade()
        self.assertEqual((self.win64 / "dxgi.dll").read_bytes(), b"original dll")
        self.assertEqual(storage.load_mods(), [])
        self.assertEqual(list(pathlib.Path(storage.STORAGE_DIR).rglob("dxgi.dll")), [])
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_crash_during_staging_is_discardable_without_touching_game(self):
        original_copy = operation_jobs.copy_file
        def crash(*args, **kwargs):
            original_copy(*args, **kwargs)
            raise SystemExit("crash")
        with patch.object(operation_jobs, "copy_file", side_effect=crash), self.assertRaises(SystemExit):
            self.install_reshade()
        journal = self.interrupted()
        self.assertFalse(journal.data["mutation_started"])
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertEqual((self.win64 / "dxgi.dll").read_bytes(), b"original dll")
        self.assertFalse((pathlib.Path(journal.root) / "payload").exists())

    def test_crash_before_catalog_save_restores_overwritten_layer(self):
        first = self.install_reshade()
        original_catalog = copy.deepcopy(storage.load_mods())
        source = self.source("second.dll", b"second layer")
        with patch.object(storage, "save_mods", side_effect=SystemExit("crash")), self.assertRaises(SystemExit):
            mod_ops.add_reshade_mod([source], {"name": "Second", "relative_paths": {os.path.normcase(source): "dxgi.dll"}})
        journal = self.interrupted()
        self.assertEqual((self.win64 / "dxgi.dll").read_bytes(), b"second layer")
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertEqual((self.win64 / "dxgi.dll").read_bytes(), b"modded content")
        self.assertEqual(storage.load_mods(), original_catalog)
        self.assertTrue(pathlib.Path(mod_ops._storage_dir(first)).exists())

    def test_crash_after_catalog_save_is_recovered_without_settings_changes(self):
        before = storage.load_settings()
        original = operation_recovery.Journal.mark
        def crash(journal, phase):
            if phase == "catalog_saved":
                raise SystemExit("crash")
            return original(journal, phase)
        with patch.object(operation_recovery.Journal, "mark", new=crash), self.assertRaises(SystemExit):
            self.install_reshade()
        journal = self.interrupted()
        self.assertEqual(len(storage.load_mods()), 1)
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertEqual(storage.load_settings(), before)
        self.assertEqual(storage.load_mods(), [])

    def test_background_snapshot_only_contains_imported_targets_and_backup_is_complete(self):
        with patch.object(storage, "save_mods", side_effect=SystemExit("crash")), self.assertRaises(SystemExit):
            self.install_background()
        journal = self.interrupted()
        captured = [pathlib.Path(item["path"]).name for item in journal.data["files"]]
        self.assertEqual(len(captured), 2)  # um BK2 e seu temporário de publicação
        self.assertIn("Intro.bk2", captured)
        self.assertNotIn("Unrelated.bk2", captured)
        backup = pathlib.Path(mod_ops._movies_backup_dir())
        self.assertEqual((backup / "Intro.bk2").read_bytes(), b"original intro")
        self.assertEqual((backup / "Unrelated.bk2").read_bytes(), b"unrelated cinematic")
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertEqual((self.movies / "Intro.bk2").read_bytes(), b"original intro")
        self.assertEqual((backup / "Intro.bk2").read_bytes(), b"original intro")

    def test_background_addon_is_private_and_does_not_overwrite_parent_layer(self):
        parent = self.install_background()
        before = copy.deepcopy(storage.load_mods()[0])
        source = self.source("addon.bk2", b"addon movie")
        addon = mod_ops.add_background_mod([source], {"name": "Addon", "parent_background_id": parent["id"],
                                                        "relative_paths": {os.path.normcase(source): "nested/MoviesBink/Intro.bk2"}})
        self.assertFalse(addon["enabled"])
        self.assertTrue(all(not component["enabled"] for component in addon["components"]))
        self.assertEqual((self.movies / "Intro.bk2").read_bytes(), b"modded content")
        self.assertEqual(storage.load_mods()[0], before)
        journal = next(item for item in storage.list_operation_journals() if item["after_records"][0]["id"] == addon["id"])
        self.assertEqual(journal["files"], [])

    def test_parent_removed_during_copy_prevents_addon_commit(self):
        parent = self.install_background()
        original_copy = operation_jobs.copy_file
        def remove_parent(*args, **kwargs):
            result = original_copy(*args, **kwargs)
            storage.save_mods([])
            return result
        with patch.object(operation_jobs, "copy_file", side_effect=remove_parent), self.assertRaisesRegex(ValueError, "destino"):
            self.install_background(parent_background_id=parent["id"])
        self.assertEqual(storage.load_mods(), [])
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_cancel_during_copy_restores_nothing_because_game_is_untouched(self):
        reached, release = threading.Event(), threading.Event()
        original = operation_jobs.OperationJob.progress
        def pause(job, stage, message, current=0, total=0, unit="items"):
            original(job, stage, message, current, total, unit)
            if stage == "copying" and not reached.is_set():
                reached.set()
                release.wait(4)
        with patch.object(operation_jobs.OperationJob, "progress", new=pause):
            started = operation_jobs.start("test", lambda _: self.install_reshade())
            self.assertTrue(reached.wait(3))
            self.assertTrue(operation_jobs.cancel(started["job_id"])["ok"])
            release.set()
            self.assertEqual(self.wait(started["job_id"])["state"], "cancelled")
        self.assertEqual(storage.load_mods(), [])
        self.assertEqual((self.win64 / "dxgi.dll").read_bytes(), b"original dll")
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_cancel_during_original_movies_backup_does_not_publish_partial_backup(self):
        reached, release = threading.Event(), threading.Event()
        original = operation_jobs.OperationJob.progress
        def pause(job, stage, message, current=0, total=0, unit="items"):
            original(job, stage, message, current, total, unit)
            if stage == "backup" and not reached.is_set():
                reached.set()
                release.wait(4)
        with patch.object(operation_jobs.OperationJob, "progress", new=pause):
            started = operation_jobs.start("test", lambda _: self.install_background())
            self.assertTrue(reached.wait(3))
            self.assertTrue(operation_jobs.cancel(started["job_id"])["ok"])
            release.set()
            self.assertEqual(self.wait(started["job_id"])["state"], "cancelled")
        self.assertFalse(pathlib.Path(mod_ops._movies_backup_dir()).exists())
        self.assertEqual((self.movies / "Intro.bk2").read_bytes(), b"original intro")

    def test_cancellation_is_locked_before_game_publication(self):
        reached, release = threading.Event(), threading.Event()
        original = special_imports._publish_file
        def pause(*args):
            reached.set()
            release.wait(4)
            return original(*args)
        with patch.object(special_imports, "_publish_file", side_effect=pause):
            started = operation_jobs.start("test", lambda _: self.install_reshade())
            self.assertTrue(reached.wait(3))
            self.assertFalse(operation_jobs.cancel(started["job_id"])["ok"])
            release.set()
            self.assertEqual(self.wait(started["job_id"])["state"], "completed")

    def test_game_lock_prevents_commit(self):
        self.guard.side_effect = OSError("jogo aberto")
        with self.assertRaisesRegex(OSError, "jogo aberto"):
            self.install_reshade()
        self.assertEqual(storage.load_mods(), [])
        self.assertEqual((self.win64 / "dxgi.dll").read_bytes(), b"original dll")

    def test_recovery_refuses_changed_game_path_before_touching_files(self):
        with patch.object(storage, "save_mods", side_effect=SystemExit("crash")), self.assertRaises(SystemExit):
            self.install_reshade()
        journal = self.interrupted()
        settings = storage.load_settings()
        settings["mods_path"] = str(self.root / "other-game")
        storage.save_settings(settings)
        self.assertFalse(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertEqual((self.win64 / "dxgi.dll").read_bytes(), b"modded content")

    def test_recovery_refuses_new_layer_even_with_identical_bytes(self):
        with patch.object(storage, "save_mods", side_effect=SystemExit("crash")), self.assertRaises(SystemExit):
            self.install_reshade()
        journal = self.interrupted()
        self.install_reshade(name="Later layer")
        result = mod_ops.recover_interrupted_operation(journal.id)
        self.assertFalse(result["ok"])
        self.assertIn("camada", result["error"])
        self.assertEqual((self.win64 / "dxgi.dll").read_bytes(), b"modded content")

    def test_recovery_refuses_external_byte_change(self):
        with patch.object(storage, "save_mods", side_effect=SystemExit("crash")), self.assertRaises(SystemExit):
            self.install_reshade()
        journal = self.interrupted()
        (self.win64 / "dxgi.dll").write_bytes(b"external new bytes")
        result = mod_ops.recover_interrupted_operation(journal.id)
        self.assertFalse(result["ok"])
        self.assertIn("alterado", result["error"])
        self.assertEqual((self.win64 / "dxgi.dll").read_bytes(), b"external new bytes")

    def test_interrupted_atomic_copy_cleans_only_its_temporary_file(self):
        def crash(source, target, temporary):
            pathlib.Path(temporary).write_bytes(b"partial")
            raise SystemExit("crash before atomic replace")
        with patch.object(special_imports, "_publish_file", side_effect=crash), self.assertRaises(SystemExit):
            self.install_reshade()
        journal = self.interrupted()
        self.assertEqual((self.win64 / "dxgi.dll").read_bytes(), b"original dll")
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertEqual(list(self.win64.glob(".mm-import-*.tmp")), [])
        self.assertEqual((self.win64 / "game.exe").read_bytes(), b"unrelated executable")

    def test_existing_movies_backup_is_never_overwritten(self):
        self.install_background()
        source = self.source("replacement.bk2", b"later movie")
        mod_ops.add_background_mod([source], {"name": "Later", "relative_paths": {os.path.normcase(source): "MoviesBink/Intro.bk2"}})
        self.assertEqual((pathlib.Path(mod_ops._movies_backup_dir()) / "Intro.bk2").read_bytes(), b"original intro")
        self.assertEqual((self.movies / "Intro.bk2").read_bytes(), b"later movie")

    def test_conflicting_archive_paths_abort_without_overwriting(self):
        first = self.source("one/effect.fx", b"first")
        second = self.source("two/effect.fx", b"second")
        with self.assertRaisesRegex(ValueError, "Importe essas versões separadamente"):
            mod_ops.add_reshade_mod([first, second], {"name": "Duplicate"})
        self.assertEqual(storage.load_mods(), [])
        self.assertEqual(list(self.win64.glob("effect.fx")), [])

    def test_background_non_cinematic_extra_is_not_a_game_snapshot_target(self):
        movie = self.source("Intro.bk2")
        readme = self.source("Readme.txt")
        mod_ops.add_background_mod([movie, readme], {"name": "Movie", "relative_paths": {os.path.normcase(movie): "MoviesBink/Intro.bk2"}})
        journal = storage.list_operation_journals()[0]
        self.assertFalse(any(pathlib.Path(item["path"]).name == "Readme.txt" for item in journal["files"]))
        self.assertFalse((self.content / "Readme.txt").exists())

    def test_audio_banks_are_prepared_privately_and_originals_are_resolvable(self):
        parent = self.install_background()
        pak = self.source("audio.pak", b"pak source")
        tool = self.source("UAssetTool.exe")
        def fake_run(command):
            if command[1] == "extract_pak":
                root = pathlib.Path(command[3])
                (root / "one").mkdir()
                (root / "two").mkdir()
                (root / "one" / "Garden.bnk").write_bytes(b"first bank")
                (root / "two" / "Garden.bnk").write_bytes(b"second bank")
            else:
                pathlib.Path(command[2]).write_bytes(pathlib.Path(command[3]).read_bytes())
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch.object(mod_ops, "_UASSET_TOOL", tool), patch.object(special_imports, "_run_tool", side_effect=fake_run):
            record = mod_ops.add_background_audio_mod([pak], {"name": "Audio", "parent_background_id": parent["id"]})
        self.assertEqual(len(record["components"]), 2)
        self.assertFalse(record["enabled"])
        self.assertNotEqual(record["files"][0]["name"], record["files"][1]["name"])
        for component in record["components"]:
            self.assertFalse(component["enabled"])
            archive = mod_ops._background_audio_archive_for_component(record, component)
            self.assertEqual(pathlib.Path(archive).read_bytes(), b"pak source")
        self.assertEqual(list(self.game.rglob("*.pak")), [])
        self.assertTrue(pathlib.Path(pak).exists())

    def test_audio_tool_failure_removes_staging_and_preserves_parent(self):
        parent = self.install_background()
        before = storage.load_mods()
        pak = self.source("audio.pak")
        tool = self.source("UAssetTool.exe")
        with patch.object(mod_ops, "_UASSET_TOOL", tool), patch.object(special_imports, "_run_tool", side_effect=OSError("tool failed")):
            with self.assertRaisesRegex(OSError, "tool failed"):
                mod_ops.add_background_audio_mod([pak], {"parent_background_id": parent["id"]})
        self.assertEqual(storage.load_mods(), before)
        self.assertEqual(operation_recovery.list_pending(), [])
        self.assertTrue(pathlib.Path(pak).exists())

    def test_audio_extraction_uses_cancellable_job_process(self):
        parent = self.install_background()
        pak = self.source("audio.pak")
        tool = self.source("UAssetTool.exe")
        reached, release = threading.Event(), threading.Event()
        def run(job, command, timeout=120):
            self.assertEqual(command[1], "extract_pak")
            reached.set()
            release.wait(4)
            job.check()
        with patch.object(mod_ops, "_UASSET_TOOL", tool), patch.object(operation_jobs.OperationJob, "run", new=run):
            started = operation_jobs.start("test", lambda _: mod_ops.add_background_audio_mod([pak], {"parent_background_id": parent["id"]}))
            self.assertTrue(reached.wait(3))
            self.assertTrue(operation_jobs.cancel(started["job_id"])["ok"])
            release.set()
            self.assertEqual(self.wait(started["job_id"])["state"], "cancelled")
        self.assertEqual(len(storage.load_mods()), 1)
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_crash_in_middle_of_multiple_files_restores_every_target(self):
        first = self.source("one.dll", b"first replacement")
        second = self.source("two.fx", b"new shader")
        original = special_imports._publish_file
        calls = 0
        def crash(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise SystemExit("process ended after first file")
            return original(*args)
        with patch.object(special_imports, "_publish_file", side_effect=crash), self.assertRaises(SystemExit):
            mod_ops.add_reshade_mod([first, second], {"name": "Multiple", "relative_paths": {os.path.normcase(first): "dxgi.dll"}})
        journal = self.interrupted()
        self.assertEqual((self.win64 / "dxgi.dll").read_bytes(), b"first replacement")
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertEqual((self.win64 / "dxgi.dll").read_bytes(), b"original dll")
        self.assertFalse((self.win64 / "two.fx").exists())

    def test_background_multiple_cinematics_use_distinct_atomic_targets(self):
        first = self.source("Intro.bk2", b"new intro")
        second = self.source("Next.bk2", b"new next")
        mod_ops.add_background_mod([first, second], {"name": "Two movies", "relative_paths": {
            os.path.normcase(first): "MoviesBink/Intro.bk2", os.path.normcase(second): "MoviesBink/Next.bk2"}})
        self.assertEqual((self.movies / "Intro.bk2").read_bytes(), b"new intro")
        self.assertEqual((self.movies / "Next.bk2").read_bytes(), b"new next")
        self.assertEqual(list(self.movies.glob(".mm-import-*.tmp")), [])

    def test_crash_while_preparing_original_backup_does_not_publish_it(self):
        original = special_imports._copy
        def crash(source, destination, *args):
            result = original(source, destination, *args)
            if "original_moviesbink" in destination:
                raise SystemExit("backup copy interrupted")
            return result
        with patch.object(special_imports, "_copy", side_effect=crash), self.assertRaises(SystemExit):
            self.install_background()
        journal = self.interrupted()
        self.assertFalse(pathlib.Path(mod_ops._movies_backup_dir()).exists())
        self.assertTrue(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertEqual((self.movies / "Intro.bk2").read_bytes(), b"original intro")

    def test_changed_source_is_rejected_before_commit(self):
        original = operation_jobs.copy_file
        def change_source(source, destination, **kwargs):
            result = original(source, destination, **kwargs)
            pathlib.Path(source).write_bytes(b"newer user file")
            return result
        with patch.object(operation_jobs, "copy_file", side_effect=change_source), self.assertRaisesRegex(ValueError, "mudou"):
            self.install_reshade()
        self.assertEqual(storage.load_mods(), [])
        self.assertEqual((self.win64 / "dxgi.dll").read_bytes(), b"original dll")

    def test_injected_temporary_target_is_rejected_before_recovery(self):
        with patch.object(storage, "save_mods", side_effect=SystemExit("crash")), self.assertRaises(SystemExit):
            self.install_reshade()
        journal = self.interrupted()
        journal.data["files"].append({"path": str(self.win64 / "game.exe"), "root": str(self.win64), "existed": False})
        journal.save()
        self.assertFalse(mod_ops.recover_interrupted_operation(journal.id)["ok"])
        self.assertEqual((self.win64 / "game.exe").read_bytes(), b"unrelated executable")

    def test_invalid_relative_path_does_not_escape_staging(self):
        source = self.source("file.fx")
        for relative in ("../outside.fx", "C:outside.fx", "shader.fx:secret"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                mod_ops.add_reshade_mod([source], {"name": "Invalid", "relative_paths": {os.path.normcase(source): relative}})
        self.assertEqual(storage.load_mods(), [])

    def test_import_uses_supplied_preparation_journal(self):
        journal = operation_recovery.Journal.create("import", "Preparation")
        record = self.install_reshade(_operation_journal=journal)
        entries = storage.list_operation_journals()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], journal.id)
        self.assertEqual(entries[0]["kind"], "import_reshade")
        self.assertEqual(entries[0]["after_records"][0]["id"], record["id"])


if __name__ == "__main__":
    unittest.main()
