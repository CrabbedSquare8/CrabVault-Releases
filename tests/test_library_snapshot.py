import copy
import json
import os
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend import mod_ops, storage


class LibrarySnapshotTests(unittest.TestCase):
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
        self.records = [
            {"id": "visual", "name": "Visual", "character": "Hela", "skin": "Default", "type": "Mesh",
             "types": ["Mesh"], "folder": "Hela/Default/Visual", "size_mb": 2, "tags": ["Minha tag"],
             "components": [{"id": "body", "name": "Corpo", "types": ["Mesh", "Texture"], "enabled": True,
                              "files": [{"name": "body.pak"}]}], "files": [{"name": "body.pak"}],
             "asset_path_cache": {"classification-v1:body": {"paths": ["Large/Asset/Path"] * 200}}},
            {"id": "background", "name": "Cenários", "character": "Backgrounds", "install_target": "marvel_content",
             "type": "Background", "size_mb": 10, "tags": [], "components": [
                 {"id": "cinematic", "name": "Entrada", "location": "Klyntar", "files": [], "enabled": True}]},
            {"id": "addon", "name": "Complemento", "character": "Backgrounds", "install_target": "marvel_content",
             "parent_background_id": "background", "type": "Background", "size_mb": 3, "tags": ["Minha tag"],
             "components": [], "files": []},
            {"id": "unknown", "name": "Sem identidade", "character": "Generic", "size_mb": 1, "tags": []},
        ]
        storage.save_mods(self.records)
        settings = storage.load_settings()
        settings["tag_catalog"] = ["Minha tag", "Sem uso"]
        storage.save_settings(settings)

    def legacy(self):
        return {"mods": mod_ops.list_mods(include_thumbnails=False), "characters": mod_ops.get_characters(),
                "types": mod_ops.get_types(), "tags": mod_ops.get_tags(), "folders": mod_ops.get_folders()}

    def test_snapshot_matches_legacy_except_cache_and_reads_each_catalog_once(self):
        expected = self.legacy()
        for mod in expected["mods"]:
            mod.pop("asset_path_cache", None)
        with patch.object(storage, "load_mods", wraps=storage.load_mods) as mods, \
             patch.object(storage, "load_settings", wraps=storage.load_settings) as settings:
            actual = mod_ops.get_library_snapshot()
        self.assertEqual(actual, expected)
        self.assertEqual(mods.call_count, 1)
        self.assertEqual(settings.call_count, 1)

    def test_catalog_and_caller_records_are_not_modified(self):
        before = pathlib.Path(storage.MODS_JSON).read_bytes()
        settings_before = pathlib.Path(storage.SETTINGS_FILE).read_bytes()
        raw = storage.load_mods()
        frozen = copy.deepcopy(raw)
        mod_ops.list_mods(include_thumbnails=False, _mods=raw, _include_asset_cache=False)
        mod_ops.get_library_snapshot()
        self.assertEqual(raw, frozen)
        self.assertEqual(pathlib.Path(storage.MODS_JSON).read_bytes(), before)
        self.assertEqual(pathlib.Path(storage.SETTINGS_FILE).read_bytes(), settings_before)

    def test_home_keeps_late_cover_and_detail_keeps_gallery_and_cache(self):
        records = storage.load_mods()
        record = records[0]
        record.update(image="cover.png", images=["cover.png", "movie.mp4", "missing.png"],
                      image_titles={"cover.png": "Minha capa", "movie.mp4": "Prévia"})
        storage.save_mods(records)
        private = pathlib.Path(mod_ops._storage_dir(record, create=True))
        (private / "cover.png").write_bytes(b"image fixture")
        (private / "movie.mp4").write_bytes(b"video fixture")
        with patch.object(mod_ops, "_thumbnail_data_url", return_value="data:image/jpeg;base64,fixture") as thumbnails:
            home = mod_ops.get_library_snapshot()["mods"][0]
            self.assertFalse(thumbnails.called)
            self.assertIsNone(home["image_url"])
            self.assertEqual(home["image"], "cover.png")
            self.assertEqual(home["images"], record["images"])
            self.assertEqual(home["gallery_images"], [])
            self.assertEqual(mod_ops.get_mod_thumbnail("visual")["image_url"], "data:image/jpeg;base64,fixture")
            detail = mod_ops.list_mods(include_gallery=True, only_mod_id="visual")[0]
        self.assertEqual([item["name"] for item in detail["gallery_images"]], ["cover.png", "movie.mp4"])
        self.assertEqual(detail["gallery_images"][0]["title"], "Minha capa")
        self.assertIsNone(detail["gallery_images"][1]["preview_url"])
        self.assertIn("asset_path_cache", detail)

    def test_background_addon_sizes_and_filter_counts_are_preserved(self):
        snapshot = mod_ops.get_library_snapshot()
        background = next(m for m in snapshot["mods"] if m["id"] == "background")
        self.assertEqual(background["catalog_size_mb"], 13)
        self.assertEqual(background["background_locations"], ["Klyntar"])
        self.assertEqual(mod_ops.list_mods(only_mod_id="background", include_thumbnails=False)[0]["catalog_size_mb"], 13)
        counts = {item["name"]: item["count"] for item in snapshot["characters"]}
        self.assertEqual(counts["Backgrounds"], 1)
        self.assertEqual(counts["Generic"], 1)
        self.assertIn({"name": "Sem uso", "count": 0}, snapshot["tags"])
        self.assertIn({"name": "Minha tag", "count": 2}, snapshot["tags"])

    def test_empty_catalog_does_not_trigger_fallback_reads(self):
        storage.save_mods([])
        with patch.object(storage, "load_mods", wraps=storage.load_mods) as mods:
            snapshot = mod_ops.get_library_snapshot()
        self.assertEqual(mods.call_count, 1)
        self.assertEqual(snapshot["mods"], [])
        self.assertEqual(snapshot["folders"][0]["count"], 0)
        self.assertNotIn("Generic", {item["name"] for item in snapshot["characters"]})

    def test_empty_folders_remain_visible_but_component_storage_is_pruned(self):
        game = self.root / "game"
        package = game / "Hela" / "Default" / "Visual"
        (package / "Components" / "body").mkdir(parents=True)
        (game / "Vazia").mkdir()
        (game / "Components" / "Avulso").mkdir(parents=True)
        settings = storage.load_settings()
        settings["mods_path"] = str(game)
        storage.save_settings(settings)
        mods = storage.load_mods()
        mods[0]["folder"] = os.path.join("Hela", "Default", "Visual")
        for index, mod in enumerate(mods[1:]):
            mod["folder"] = f"Outros{index}"
        storage.save_mods(mods)
        tree = mod_ops.get_library_snapshot()["folders"][0]
        children = {node["name"]: node for node in tree["children"]}
        self.assertEqual(children["Vazia"]["children"], [])
        self.assertEqual(children["Vazia"]["count"], 0)
        self.assertEqual(children["Components"]["children"][0]["name"], "Avulso")
        package_node = children["Hela"]["children"][0]["children"][0]
        self.assertEqual(package_node["count"], 1)
        self.assertEqual(package_node["children"], [])

    def test_folder_scan_does_not_follow_symlinks_or_junctions(self):
        link = Mock(name="link")
        link.name = "Symlink"
        link.is_symlink.return_value = True
        junction = Mock(name="junction")
        junction.name = "Junction"
        junction.is_symlink.return_value = False
        junction.is_dir.return_value = True
        junction.stat.return_value = SimpleNamespace(st_file_attributes=0x400)
        with patch.object(mod_ops.os, "name", "nt"), patch.object(mod_ops.os, "scandir") as scan:
            scan.return_value.__enter__.return_value = iter([link, junction])
            tree = mod_ops._scan_folder_tree(str(self.root), "", {})
        self.assertEqual(tree["children"], [])
        self.assertEqual(scan.call_count, 1)
        junction.is_dir.assert_called_once_with(follow_symlinks=False)

    def test_folder_access_error_keeps_root_and_count(self):
        with patch.object(mod_ops.os, "scandir", side_effect=PermissionError("blocked")):
            tree = mod_ops._scan_folder_tree(str(self.root), "", {"": 3})
        self.assertEqual(tree["count"], 3)
        self.assertEqual(tree["children"], [])

    def test_asset_cache_is_the_only_removed_record_field(self):
        legacy = mod_ops.list_mods(include_thumbnails=False)
        snapshot = mod_ops.get_library_snapshot()["mods"]
        for before, after in zip(legacy, snapshot):
            removed = set(before) - set(after)
            self.assertEqual(removed, {"asset_path_cache"} if "asset_path_cache" in before else set())
            self.assertEqual({k: v for k, v in before.items() if k != "asset_path_cache"}, after)
        self.assertLess(len(json.dumps(snapshot)), len(json.dumps(legacy)))


if __name__ == "__main__":
    unittest.main()
