import copy
import os
import pathlib
import shutil
import tempfile
import unittest
from unittest.mock import patch

from backend import mod_ops, storage


class ComponentClassificationTests(unittest.TestCase):
    def fixture(self):
        files = [{"name": "example.pak"}, {"name": "example.utoc"}, {"name": "example.ucas"}]
        component = {"id": "c1", "name": "example", "files": files,
                     "types": ["Physics"], "type": "Physics", "enabled": True}
        mod = {"files": copy.deepcopy(files), "components": [component],
               "types": ["Mesh", "Texture", "Physics"]}
        return mod, component

    def test_installed_scan_deeply_classifies_new_external_mods(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            package = root / "Luna Snow" / "Default" / "Example"
            package.mkdir(parents=True)
            (package / "Example.pak").write_bytes(b"pak")
            settings = {"mods_path": str(root), "installed_scan_completed": False}
            mods = []
            saved = {}

            def save_mods(value):
                saved["mods"] = copy.deepcopy(value)

            def save_settings(value):
                saved["settings"] = dict(value)

            with patch.object(storage, "load_settings", return_value=settings), \
                 patch.object(storage, "load_mods", return_value=mods), \
                 patch.object(storage, "save_mods", side_effect=save_mods), \
                 patch.object(storage, "save_settings", side_effect=save_settings), \
                 patch.object(mod_ops, "_paths_from_bundle", return_value=[
                     "Marvel/Content/Characters/1031/1031303/Meshes/SK_Luna.uasset"
                 ]):
                result = mod_ops.scan_installed_mods()

            self.assertTrue(result["ok"])
            self.assertTrue(result["first_scan"])
            self.assertEqual(result["classified"], 1)
            self.assertEqual(result["identified"], 1)
            self.assertEqual(result["analyzed_components"], 1)
            self.assertEqual(saved["mods"][0]["types"], ["Mesh"])
            self.assertEqual(saved["mods"][0]["character"], "Luna Snow")
            self.assertEqual(saved["mods"][0]["skin"], "Cool Summer")
            self.assertTrue(saved["settings"]["installed_scan_completed"])

    def test_single_complete_component_inherits_all_confirmed_types(self):
        mod, component = self.fixture()
        self.assertEqual(mod_ops._component_types_from_metadata(mod, component),
                         ["Mesh", "Texture", "Physics"])

    def test_conflict_cache_classifies_each_variant_without_inheriting_mesh(self):
        mod, component = self.fixture()
        component.update(type="Unknown", types=["Unknown"])
        other = dict(component, id="c2", files=[{"name": "other.pak"}])
        mod["components"].append(other)
        mod["asset_path_cache"] = {
            "conflict_component:c1": {"paths": ["Marvel/Content/Textures/T_Eyes_D.uasset"]},
            "conflict_component:c2": {"paths": ["Marvel/Content/Meshes/SK_Hero.uasset"]},
        }
        with patch.object(mod_ops, "_paths_from_bundle", side_effect=AssertionError("No scan")):
            self.assertEqual(mod_ops._component_types_from_metadata(mod, component), ["Texture"])
            self.assertEqual(mod_ops._component_types_from_metadata(mod, other), ["Mesh"])

    def test_legacy_cache_recognizes_mixed_assets_without_disk_scan(self):
        mod, component = self.fixture()
        mod["asset_path_cache"] = {"component_c1": {"paths": [
            "Marvel/Content/Meshes/SK_Hero.uasset",
            "Marvel/Content/Textures/T_Hero_D.uasset",
            "Marvel/Content/SK_Hero_Skeleton_AnimBlueprint.uasset",
        ]}}
        before = copy.deepcopy(mod)
        with patch.object(mod_ops, "_paths_from_bundle", side_effect=AssertionError("No scan")):
            self.assertEqual(mod_ops._component_types_from_metadata(mod, component),
                             ["Mesh", "Texture", "Physics"])
        self.assertEqual(mod, before)

    def test_animblueprint_alone_is_not_mesh_even_with_sk_prefix(self):
        mod, component = self.fixture()
        mod["asset_path_cache"] = {"component-files-v1:c1": {"paths": [
            r"Marvel\Content\SK_Hero_Skeleton_AnimBlueprint.uasset",
        ]}}
        self.assertEqual(mod_ops._component_types_from_metadata(mod, component), ["Physics"])

    def test_separate_physics_component_does_not_inherit_mod_mesh(self):
        mod, component = self.fixture()
        mod["components"].append({"id": "c2", "types": ["Mesh"]})
        self.assertEqual(mod_ops._component_types_from_metadata(mod, component), ["Physics"])

    def test_single_component_not_covering_all_files_does_not_inherit(self):
        mod, component = self.fixture()
        mod["files"].append({"name": "other.pak"})
        self.assertEqual(mod_ops._component_types_from_metadata(mod, component), ["Physics"])

    def test_single_component_uses_all_files_cache(self):
        mod, component = self.fixture()
        mod["asset_path_cache"] = {"all_files": {"paths": [
            "Marvel/Content/Meshes/CustomHero.uasset",
            "Marvel/Content/Textures/T_Hero_D.uasset",
        ]}}
        self.assertEqual(mod_ops._component_types_from_metadata(mod, component),
                         ["Mesh", "Texture", "Physics"])

    def test_background_audio_bank_uses_structural_metadata_without_scan(self):
        component = {"id": "bank", "name": "Cinematic", "files": [{"name": "bank.pak"}],
                     "type": "Unknown", "types": ["Unknown"], "audio_bank": "scene.bnk"}
        mod = {"background_audio": True, "components": [component],
               "type": "Unknown", "types": ["Unknown"]}
        with patch.object(mod_ops, "_paths_from_bundle", side_effect=AssertionError("No scan")):
            self.assertEqual(mod_ops._component_types_from_metadata(mod, component), ["Audio"])

    def test_audio_bank_marker_is_not_inferred_without_background_audio_record(self):
        component = {"id": "bank", "name": "Cinematic", "files": [{"name": "bank.pak"}],
                     "type": "Unknown", "types": ["Unknown"], "audio_bank": "scene.bnk"}
        mod = {"components": [component], "type": "Unknown", "types": ["Unknown"]}
        self.assertEqual(mod_ops._component_types_from_metadata(mod, component), ["Unknown"])


class AutomaticComponentClassificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.sources = []
        for name in ("alpha.pak", "beta.pak", "addon.pak"):
            path = self.root / name
            path.write_bytes(b"fixture")
            self.sources.append(str(path))
        self.mod = {"id": "fixture", "files": [{"name": pathlib.Path(p).name} for p in self.sources],
                    "types": ["Unknown"], "components": [
                        {"id": str(i), "name": pathlib.Path(p).stem, "files": [{"name": pathlib.Path(p).name}],
                         "type": "Unknown", "types": ["Unknown"], "enabled": i == 0}
                        for i, p in enumerate(self.sources)]}
        mod_ops._COMPONENT_ANALYSIS_RETRY.clear()
        self.addCleanup(mod_ops._COMPONENT_ANALYSIS_RETRY.clear)

    def paths(self, files):
        if pathlib.Path(files[0]).name == "addon.pak":
            return ["Marvel/Content/Textures/T_Eyes_D.uasset"]
        return ["Marvel/Content/Meshes/SK_Hero.uasset", "Marvel/Content/Textures/T_Body_D.uasset"]

    def test_analyzes_disabled_variants_and_keeps_texture_addon_separate(self):
        before = copy.deepcopy(self.mod)
        with patch.object(mod_ops, "_paths_from_bundle", side_effect=self.paths) as reader:
            mod_ops._analyze_mod_components(self.mod, self.sources)
        self.assertEqual(reader.call_count, 3)
        self.assertEqual([c["types"] for c in self.mod["components"]],
                         [["Mesh", "Texture"], ["Mesh", "Texture"], ["Texture"]])
        self.assertEqual(self.mod["types"], ["Mesh", "Texture"])
        self.assertEqual([c["enabled"] for c in self.mod["components"]],
                         [c["enabled"] for c in before["components"]])

    def test_reopening_or_switching_storage_location_does_not_scan_again(self):
        with patch.object(mod_ops, "_paths_from_bundle", side_effect=self.paths):
            mod_ops._analyze_mod_components(self.mod, self.sources)
        active = self.root / "active"
        active.mkdir()
        copies = [shutil.copy2(p, active) for p in self.sources]
        with patch.object(mod_ops, "_paths_from_bundle", side_effect=AssertionError("No rescan")):
            mod_ops._analyze_mod_components(self.mod, copies)
        self.assertFalse(any(mod_ops._component_analysis_pending(
            self.mod, c, [copies[i]]) for i, c in enumerate(self.mod["components"])))

    def test_changed_package_invalidates_only_its_classification(self):
        with patch.object(mod_ops, "_paths_from_bundle", side_effect=self.paths):
            mod_ops._analyze_mod_components(self.mod, self.sources)
        pathlib.Path(self.sources[0]).write_bytes(b"changed package")
        with patch.object(mod_ops, "_paths_from_bundle", return_value=["Marvel/Content/Textures/T_New.uasset"]) as reader:
            mod_ops._analyze_mod_components(self.mod, self.sources)
        reader.assert_called_once_with([self.sources[0]])
        self.assertEqual(self.mod["components"][0]["types"], ["Texture"])

    def test_content_button_reuses_automatic_analysis(self):
        with patch.object(mod_ops, "_paths_from_bundle", side_effect=self.paths):
            mod_ops._analyze_mod_components(self.mod, self.sources)
        with patch.object(mod_ops, "list_mods", return_value=[self.mod]), patch.object(
                mod_ops, "_mod_source_files", return_value=self.sources), patch.object(
                mod_ops, "_paths_from_bundle", side_effect=AssertionError("No rescan")):
            result = mod_ops.get_component_file_contents(self.mod["id"], "0")
        self.assertEqual(result["asset_count"], 2)

    def test_existing_component_cache_is_reused_without_reading_package(self):
        self.mod["asset_path_cache"] = {f"conflict_component:{c['id']}": {"paths": self.paths([self.sources[i]])}
                                        for i, c in enumerate(self.mod["components"])}
        with patch.object(mod_ops, "_paths_from_bundle", side_effect=AssertionError("No scan")):
            mod_ops._analyze_mod_components(self.mod, self.sources)
        self.assertEqual(self.mod["components"][2]["types"], ["Texture"])

    def test_unreadable_package_retries_later_without_guessing_types(self):
        with patch.object(mod_ops.time, "monotonic", return_value=100), patch.object(
                mod_ops, "_paths_from_bundle", return_value=[]) as reader:
            mod_ops._analyze_mod_components(self.mod, self.sources)
            mod_ops._analyze_mod_components(self.mod, self.sources)
        self.assertEqual(reader.call_count, 3)
        self.assertTrue(all(c["types"] == ["Unknown"] for c in self.mod["components"]))
        with patch.object(mod_ops.time, "monotonic", return_value=161), patch.object(
                mod_ops, "_paths_from_bundle", side_effect=self.paths) as reader:
            mod_ops._analyze_mod_components(self.mod, self.sources)
        self.assertEqual(reader.call_count, 3)
        self.assertEqual(self.mod["components"][0]["types"], ["Mesh", "Texture"])

    def test_legible_but_unrecognized_assets_are_not_repeatedly_scanned(self):
        with patch.object(mod_ops, "_paths_from_bundle", return_value=["Marvel/Content/Other/Data.uasset"]) as reader:
            mod_ops._analyze_mod_components(self.mod, self.sources)
            mod_ops._analyze_mod_components(self.mod, self.sources)
        self.assertEqual(reader.call_count, 3)
        self.assertEqual(self.mod["types"], ["Unknown"])

    def test_import_persists_individual_types_and_cache(self):
        with patch.multiple(storage, STORAGE_DIR=str(self.root / "library"),
                            BACKUPS_DIR=str(self.root / "backups"), MODS_JSON=str(self.root / "mods.json"),
                            SETTINGS_FILE=str(self.root / "settings.json")), patch.object(
                                mod_ops, "_paths_from_bundle", side_effect=self.paths) as reader:
            record = mod_ops.add_mod(self.sources, {"name": "Imported", "character": "Hela",
                "component_labels": {os.path.normcase(p): pathlib.Path(p).stem for p in self.sources}})
            saved = storage.load_mods()[0]
        self.assertEqual(reader.call_count, 3)
        self.assertEqual(record, saved)
        self.assertEqual(len(saved["asset_path_cache"]), 3)
        self.assertTrue(all(c["type"] != "Unknown" for c in saved["components"]))
        self.assertEqual(sum(c["enabled"] for c in saved["components"]), 1)

    def test_background_result_preserves_concurrent_edits(self):
        latest = copy.deepcopy(self.mod)
        latest["components"].reverse()
        latest["components"][0].update(name="Renamed", enabled=True, description="My label")
        latest["tags"] = ["new tag"]
        with patch.object(storage, "load_mods", side_effect=[[copy.deepcopy(self.mod)], [latest]]), patch.object(
                mod_ops, "_mod_source_files", return_value=self.sources), patch.object(
                mod_ops, "_paths_from_bundle", side_effect=self.paths), patch.object(storage, "save_mods") as save:
            result = mod_ops.classify_mod_components(self.mod["id"])
        self.assertTrue(result["changed"])
        saved = save.call_args.args[0][0]
        self.assertEqual(saved["components"][0]["name"], "Renamed")
        self.assertTrue(saved["components"][0]["enabled"])
        self.assertEqual(saved["components"][0]["description"], "My label")
        self.assertEqual(saved["tags"], ["new tag"])
        self.assertEqual(saved["components"][0]["types"], ["Texture"])

    def test_deleted_mod_is_not_restored_by_background_result(self):
        with patch.object(storage, "load_mods", side_effect=[[self.mod], []]), patch.object(
                mod_ops, "_mod_source_files", return_value=self.sources), patch.object(
                mod_ops, "_paths_from_bundle", side_effect=self.paths), patch.object(storage, "save_mods") as save:
            self.assertFalse(mod_ops.classify_mod_components(self.mod["id"])["changed"])
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
