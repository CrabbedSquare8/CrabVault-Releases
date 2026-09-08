import copy
import hashlib
import json
import os
import pathlib
import shutil
import stat
import tempfile
import types
import unittest
import zipfile
from unittest.mock import patch

from backend import full_backup, operation_jobs, storage


class FullBackupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        overrides = {"MODS_JSON": str(self.root / "mods.json"), "SETTINGS_FILE": str(self.root / "settings.json"),
                     "STORAGE_DIR": str(self.root / "library"), "BACKUPS_DIR": str(self.root / "backups")}
        if hasattr(storage, "PERSONAL_CORRECTIONS_FILE"):
            overrides["PERSONAL_CORRECTIONS_FILE"] = str(self.root / "personal_corrections.json")
        patched = patch.multiple(storage, **overrides)
        patched.start()
        self.addCleanup(patched.stop)
        corrections = patch.object(full_backup, "_corrections", return_value={"version": 1, "corrections": []})
        corrections.start()
        self.addCleanup(corrections.stop)
        storage.ensure_dirs()
        self.destination = self.root / "export"
        self.destination.mkdir()
        self.game = self.root / "game"
        self.game.mkdir()
        settings = storage.load_settings()
        settings["mods_path"] = str(self.game)
        settings["pending_background_audio_changes"] = [{"example": True}]
        settings["bypass_game_running_lock"] = True
        storage.save_settings(settings)
        full_backup._PLANS.clear()
        self.addCleanup(full_backup._PLANS.clear)
        self.mod = {"id": "example", "name": "Exemplo", "character": "Hela", "skin": "Default",
                    "storage_folder": "Hela/example", "folder": "Hela/example", "enabled": True,
                    "files": [{"name": "Components/a/same.pak", "size": 7}],
                    "components": [{"id": "a", "name": "Variante", "enabled": True,
                                    "files": [{"name": "Components/a/same.pak", "size": 7}]},
                                   {"id": "b", "name": "Outra", "enabled": False,
                                    "files": [{"name": "Components/b/same.pak", "size": 7}]}],
                    "images": ["image.png"], "archives": ["Archive/mod.zip"], "tags": ["favorito"]}
        storage.save_mods([self.mod])
        self.payloads = {"Hela/example/Components/a/same.pak": b"first!!",
                         "Hela/example/Components/b/same.pak": b"second!",
                         "Hela/example/image.png": b"image", "Hela/example/Archive/mod.zip": b"archive",
                         "Removed/preserved.zip": b"preserved archive"}
        for name, data in self.payloads.items():
            target = pathlib.Path(storage.STORAGE_DIR) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def preview(self):
        result = full_backup.preview_backup(str(self.destination))
        self.assertTrue(result["ok"], result)
        return result

    def export(self):
        preview = self.preview()
        result = full_backup.create_backup(preview["token"])
        self.assertTrue(result["ok"], result)
        return pathlib.Path(result["path"])

    def assert_clean_destination(self):
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_estimate_is_read_only_and_covers_all_private_files_and_orphans(self):
        before = pathlib.Path(storage.MODS_JSON).read_bytes(), pathlib.Path(storage.SETTINGS_FILE).read_bytes()
        preview = self.preview()
        self.assertTrue(preview["can_create"])
        self.assertTrue(preview["complete"])
        self.assertEqual(preview["file_count"], 5)
        self.assertGreater(preview["total_bytes"], sum(map(len, self.payloads.values())))
        self.assertGreater(preview["required_bytes"], preview["total_bytes"])
        self.assert_clean_destination()
        self.assertEqual(before, (pathlib.Path(storage.MODS_JSON).read_bytes(), pathlib.Path(storage.SETTINGS_FILE).read_bytes()))

    def test_zip64_hash_manifest_portable_catalog_and_originals(self):
        preview = self.preview()
        result = full_backup.create_backup(preview["token"])
        self.assertTrue(result["ok"], result)
        archive_path = pathlib.Path(result["path"])
        self.assertLess(archive_path.stat().st_size, preview["required_bytes"])
        with zipfile.ZipFile(archive_path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            for entry in manifest["files"]:
                data = archive.read(entry["name"])
                self.assertEqual(len(data), entry["size"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
            self.assertEqual(archive.read("mods_storage/Hela/example/Components/a/same.pak"), b"first!!")
            self.assertEqual(archive.read("mods_storage/Hela/example/Components/b/same.pak"), b"second!")
            info = archive.getinfo("mods_storage/Hela/example/Components/a/same.pak")
            self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
            self.assertGreaterEqual(info.extract_version, 45)
            original = json.loads(archive.read("catalog/mods.json"))
            self.assertTrue(original[0]["enabled"])
            portable = json.loads(archive.read("mods.json"))
            self.assertFalse(portable[0]["enabled"])
            self.assertTrue(all(not item["enabled"] for item in portable[0]["components"]))
            settings = json.loads(archive.read("settings.json"))
            self.assertEqual(settings["mods_path"], "")
            self.assertEqual(settings["pending_background_audio_changes"], [])
            self.assertFalse(settings["bypass_game_running_lock"])
            self.assertIn("personal_corrections.json", archive.namelist())
        self.assertFalse(full_backup.create_backup(preview["token"])["ok"])

    def test_missing_files_require_explicit_incomplete_export(self):
        (pathlib.Path(storage.STORAGE_DIR) / "Hela/example/image.png").unlink()
        preview = self.preview()
        self.assertFalse(preview["complete"])
        self.assertTrue(preview["warnings"])
        self.assertFalse(full_backup.create_backup(preview["token"])["ok"])
        self.assert_clean_destination()
        preview = self.preview()
        exported = full_backup.create_backup(preview["token"], allow_incomplete=True)
        self.assertTrue(exported["ok"])
        self.assertFalse(exported["complete"])
        with zipfile.ZipFile(exported["path"]) as archive:
            self.assertFalse(json.loads(archive.read("manifest.json"))["complete"])

    def test_external_and_component_only_entries_use_available_game_files(self):
        name = "Hela/example/Components/b/same.pak"
        (pathlib.Path(storage.STORAGE_DIR) / name).unlink()
        active = self.game / name
        active.parent.mkdir(parents=True)
        active.write_bytes(b"active!")
        mods = storage.load_mods()
        mods[0]["external"] = True
        storage.save_mods(mods)
        preview = self.preview()
        self.assertTrue(preview["complete"])
        self.assertTrue(any("cópia ativa" in warning for warning in preview["warnings"]))
        result = full_backup.create_backup(preview["token"])
        self.assertTrue(result["ok"], result)
        with zipfile.ZipFile(result["path"]) as archive:
            self.assertEqual(archive.read("mods_storage/" + name), b"active!")
        self.assertEqual(active.read_bytes(), b"active!")

    def test_original_moviesbink_is_preserved_without_other_backups(self):
        originals = pathlib.Path(storage.BACKUPS_DIR) / "original_moviesbink"
        originals.mkdir()
        (originals / "Movie.bk2").write_bytes(b"original")
        (pathlib.Path(storage.BACKUPS_DIR) / "old-export.json").write_text("ignored")
        exported = self.export()
        with zipfile.ZipFile(exported) as archive:
            self.assertEqual(archive.read("backups/original_moviesbink/Movie.bk2"), b"original")
            self.assertNotIn("backups/old-export.json", archive.namelist())
        self.assertFalse(full_backup.preview_backup(str(originals))["ok"])

    def test_space_is_checked_at_preview_and_again_before_writing(self):
        with patch.object(shutil, "disk_usage", return_value=shutil._ntuple_diskusage(10, 9, 1)):
            preview = self.preview()
            self.assertFalse(preview["can_create"])
            result = full_backup.create_backup(preview["token"])
        self.assertFalse(result["ok"])
        self.assertIn("espaço", result["error"])
        self.assert_clean_destination()

    def test_changed_file_or_added_file_rejects_stale_plan(self):
        preview = self.preview()
        path = pathlib.Path(storage.STORAGE_DIR) / "Hela/example/image.png"
        path.write_bytes(b"another image")
        result = full_backup.create_backup(preview["token"])
        self.assertFalse(result["ok"])
        self.assert_clean_destination()
        preview = self.preview()
        (path.parent / "new.png").write_bytes(b"new")
        self.assertFalse(full_backup.create_backup(preview["token"])["ok"])
        self.assert_clean_destination()

    def test_changed_catalog_or_corrections_rejects_stale_plan(self):
        preview = self.preview()
        mods = storage.load_mods()
        mods[0]["name"] = "Alterado"
        storage.save_mods(mods)
        self.assertFalse(full_backup.create_backup(preview["token"])["ok"])
        preview = self.preview()
        with patch.object(full_backup, "_corrections", return_value={"new": "correction"}):
            self.assertFalse(full_backup.create_backup(preview["token"])["ok"])
        self.assert_clean_destination()

    def test_personal_corrections_storage_helper_is_included_and_roundtrips(self):
        corrections = {"version": 1, "records": [{"id": "remembered", "character": "Hela"}]}
        storage.save_personal_corrections(corrections)
        with patch.object(full_backup, "_corrections", side_effect=lambda: copy.deepcopy(storage.load_personal_corrections())):
            exported = self.export()
        preview = full_backup.preview_restore(str(exported), str(self.destination))
        result = full_backup.restore_backup(preview["token"])
        self.assertTrue(result["ok"], result)
        restored = pathlib.Path(result["path"]) / "personal_corrections.json"
        self.assertEqual(json.loads(restored.read_text(encoding="utf-8")), corrections)
        self.assertEqual(storage.load_personal_corrections(), corrections)

    def test_change_during_streaming_discards_partial_only(self):
        preview = self.preview()
        path = pathlib.Path(storage.STORAGE_DIR) / "Hela/example/image.png"

        def progress(stage, *args):
            if stage == "backup":
                path.write_bytes(b"concurrent edit")

        with patch.object(operation_jobs, "progress", side_effect=progress):
            result = full_backup.create_backup(preview["token"])
        self.assertFalse(result["ok"])
        self.assert_clean_destination()
        self.assertEqual(path.read_bytes(), b"concurrent edit")

    def test_cancellation_discards_only_own_partial_and_preserves_sources(self):
        preview = self.preview()
        marker = self.destination / "keep.txt"
        marker.write_text("untouched")

        def progress(stage, *args):
            if stage == "backup":
                raise operation_jobs.OperationCancelled()

        with patch.object(operation_jobs, "progress", side_effect=progress):
            with self.assertRaises(operation_jobs.OperationCancelled):
                full_backup.create_backup(preview["token"])
        self.assertEqual(list(self.destination.iterdir()), [marker])
        for name, data in self.payloads.items():
            self.assertEqual((pathlib.Path(storage.STORAGE_DIR) / name).read_bytes(), data)

    def test_existing_export_is_never_overwritten(self):
        preview = self.preview()
        target = self.destination / preview["filename"]
        target.write_bytes(b"keep")
        self.assertFalse(full_backup.create_backup(preview["token"])["ok"])
        self.assertEqual(target.read_bytes(), b"keep")

    def test_disallows_destination_inside_library_or_game(self):
        for target in (pathlib.Path(storage.STORAGE_DIR), pathlib.Path(storage.STORAGE_DIR) / "Hela", self.game):
            self.assertFalse(full_backup.preview_backup(str(target))["ok"])

    def test_disallows_traversal_and_windows_ads_in_catalog(self):
        for name in ("../other.pak", "C:/file.pak", "folder/name:stream", "foo/../x", "CON.pak"):
            mods = storage.load_mods()
            mods[0]["files"][0]["name"] = name
            storage.save_mods(mods)
            self.assertFalse(full_backup.preview_backup(str(self.destination))["ok"], name)
        self.assert_clean_destination()

    def test_symlink_in_library_is_rejected(self):
        target = pathlib.Path(storage.STORAGE_DIR) / "link.pak"
        try:
            target.symlink_to(self.root / "mods.json")
        except OSError:
            self.skipTest("Symlinks unavailable without OS privilege")
        self.assertFalse(full_backup.preview_backup(str(self.destination))["ok"])

    def test_windows_reparse_point_is_rejected_without_following_it(self):
        original = pathlib.Path.lstat
        linked = pathlib.Path(storage.STORAGE_DIR) / "Hela/example/image.png"

        def lstat(path):
            if path == linked:
                return types.SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400)
            return original(path)

        with patch.object(pathlib.Path, "lstat", lstat):
            preview = full_backup.preview_backup(str(self.destination))
        self.assertFalse(preview["ok"])
        self.assertIn("junction", preview["error"])
        self.assert_clean_destination()

    def test_roundtrip_extracts_separate_disabled_library_without_touching_current(self):
        exported = self.export()
        current = pathlib.Path(storage.MODS_JSON).read_bytes(), pathlib.Path(storage.SETTINGS_FILE).read_bytes()
        preview = full_backup.preview_restore(str(exported), str(self.destination))
        self.assertTrue(preview["ok"], preview)
        self.assertFalse(pathlib.Path(preview["destination"]).exists())
        restored = full_backup.restore_backup(preview["token"])
        self.assertTrue(restored["ok"], restored)
        target = pathlib.Path(restored["path"])
        for name, data in self.payloads.items():
            self.assertEqual((target / "mods_storage" / name).read_bytes(), data)
        self.assertFalse(json.loads((target / "mods.json").read_text(encoding="utf-8"))[0]["enabled"])
        self.assertEqual(json.loads((target / "settings.json").read_text(encoding="utf-8"))["mods_path"], "")
        self.assertTrue(json.loads((target / "catalog/mods.json").read_text(encoding="utf-8"))[0]["enabled"])
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            self.assertEqual(hashlib.sha256((target / entry["name"]).read_bytes()).hexdigest(), entry["sha256"])
        self.assertEqual(current, (pathlib.Path(storage.MODS_JSON).read_bytes(), pathlib.Path(storage.SETTINGS_FILE).read_bytes()))
        self.assertFalse(list(self.game.iterdir()))
        self.assertFalse(full_backup.restore_backup(preview["token"])["ok"])

    def test_cancel_restore_removes_only_owned_new_directory(self):
        exported = self.export()
        preview = full_backup.preview_restore(str(exported), str(self.destination))

        def progress(stage, *args):
            if stage == "restore_backup":
                raise operation_jobs.OperationCancelled()

        with patch.object(operation_jobs, "progress", side_effect=progress):
            with self.assertRaises(operation_jobs.OperationCancelled):
                full_backup.restore_backup(preview["token"])
        self.assertEqual(list(self.destination.iterdir()), [exported])

    def test_restore_refuses_existing_destination_and_modified_archive(self):
        exported = self.export()
        preview = full_backup.preview_restore(str(exported), str(self.destination))
        pathlib.Path(preview["destination"]).mkdir()
        self.assertFalse(full_backup.restore_backup(preview["token"])["ok"])
        preview = full_backup.preview_restore(str(exported), str(self.destination))
        with open(exported, "ab") as stream:
            stream.write(b"changed")
        self.assertFalse(full_backup.restore_backup(preview["token"])["ok"])

    def rewrite_zip(self, exported, change):
        with zipfile.ZipFile(exported) as archive:
            contents = {info.filename: archive.read(info.filename) for info in archive.infolist()}
        change(contents)
        with zipfile.ZipFile(exported, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, data in contents.items():
                archive.writestr(name, data)

    def test_restore_hash_mismatch_cleans_partial(self):
        exported = self.export()
        self.rewrite_zip(exported, lambda contents: contents.__setitem__("mods_storage/Hela/example/image.png", b"other"))
        preview = full_backup.preview_restore(str(exported), str(self.destination))
        self.assertTrue(preview["ok"], preview)
        result = full_backup.restore_backup(preview["token"])
        self.assertFalse(result["ok"])
        self.assertIn("hash", result["error"])
        self.assertEqual(list(self.destination.iterdir()), [exported])

    def test_restore_space_and_publication_failure_preserve_existing_files(self):
        exported = self.export()
        with patch.object(shutil, "disk_usage", return_value=shutil._ntuple_diskusage(10, 9, 1)):
            preview = full_backup.preview_restore(str(exported), str(self.destination))
            self.assertTrue(preview["ok"])
            self.assertFalse(preview["can_restore"])
            self.assertFalse(full_backup.restore_backup(preview["token"])["ok"])
        self.assertEqual(list(self.destination.iterdir()), [exported])
        preview = full_backup.preview_restore(str(exported), str(self.destination))
        original = os.rename

        def rename(source, target):
            if pathlib.Path(source).name == "mods_storage":
                raise OSError("Disco indisponível")
            return original(source, target)

        with patch.object(os, "rename", side_effect=rename):
            result = full_backup.restore_backup(preview["token"])
        self.assertFalse(result["ok"])
        self.assertEqual(list(self.destination.iterdir()), [exported])

    def test_restore_rejects_symlink_entries_in_zip(self):
        exported = self.export()
        with zipfile.ZipFile(exported, "a") as archive:
            link = zipfile.ZipInfo("mods_storage/evil-link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "../../outside")
        result = full_backup.preview_restore(str(exported), str(self.destination))
        self.assertFalse(result["ok"])
        self.assertIn("links", result["error"])

    def test_restore_rejects_edited_active_catalog_even_with_updated_hash(self):
        exported = self.export()

        def activate(contents):
            mods = json.loads(contents["mods.json"])
            mods[0]["enabled"] = True
            contents["mods.json"] = full_backup._json_bytes(mods)
            manifest = json.loads(contents["manifest.json"])
            entry = next(item for item in manifest["files"] if item["name"] == "mods.json")
            entry.update(size=len(contents["mods.json"]), sha256=hashlib.sha256(contents["mods.json"]).hexdigest())
            contents["manifest.json"] = full_backup._json_bytes(manifest)

        self.rewrite_zip(exported, activate)
        preview = full_backup.preview_restore(str(exported), str(self.destination))
        self.assertTrue(preview["ok"], preview)
        result = full_backup.restore_backup(preview["token"])
        self.assertFalse(result["ok"])
        self.assertIn("desativado", result["error"])
        self.assertEqual(list(self.destination.iterdir()), [exported])

    def test_restore_rejects_traversal_unlisted_files_and_duplicate_names(self):
        exported = self.export()
        self.rewrite_zip(exported, lambda contents: contents.__setitem__("../escape.txt", b"bad"))
        self.assertFalse(full_backup.preview_restore(str(exported), str(self.destination))["ok"])
        self.assertFalse((self.root / "escape.txt").exists())
        exported = self.export()
        self.rewrite_zip(exported, lambda contents: contents.__setitem__("unlisted.txt", b"bad"))
        self.assertFalse(full_backup.preview_restore(str(exported), str(self.destination))["ok"])
        with zipfile.ZipFile(exported, "a") as archive:
            archive.writestr("MODS.JSON", b"[]")
        self.assertFalse(full_backup.preview_restore(str(exported), str(self.destination))["ok"])

    def test_expired_plan_and_wrong_kind_rejected(self):
        preview = self.preview()
        full_backup._PLANS[preview["token"]]["created"] -= full_backup._PLAN_SECONDS + 1
        self.assertFalse(full_backup.create_backup(preview["token"])["ok"])
        preview = self.preview()
        self.assertFalse(full_backup.restore_backup(preview["token"])["ok"])
        self.assert_clean_destination()


if __name__ == "__main__":
    unittest.main()
