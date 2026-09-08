import copy
import hashlib
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from backend import library_maintenance as maintenance
from backend import mod_ops, storage


class LibraryMaintenanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        patches = patch.multiple(storage, MODS_JSON=str(self.root / "mods.json"),
            SETTINGS_FILE=str(self.root / "settings.json"), STORAGE_DIR=str(self.root / "library"),
            BACKUPS_DIR=str(self.root / "backups"))
        patches.start()
        self.addCleanup(patches.stop)
        storage.ensure_dirs()
        settings = storage.load_settings()
        settings["mods_path"] = str(self.root / "game")
        storage.save_settings(settings)
        for name in ("_ensure_game_operation_allowed", "_record_activity"):
            guard = patch.object(mod_ops, name)
            guard.start()
            self.addCleanup(guard.stop)
        maintenance._REPAIR_PLANS.clear()
        maintenance._RELATION_PLANS.clear()
        mod_ops._COMPONENT_ANALYSIS_RETRY.clear()
        self.addCleanup(maintenance._REPAIR_PLANS.clear)
        self.addCleanup(maintenance._RELATION_PLANS.clear)
        self.addCleanup(mod_ops._COMPONENT_ANALYSIS_RETRY.clear)

    def fixture(self, names=("Hero_Mask_On_9999999_P", "Hero_Mask_Off_9999999_P"), hashed=True):
        components, entries = [], []
        for index, name in enumerate(names):
            payload = ("component " + str(index)).encode()
            entry = {"name": f"Components/c{index}/{name}.pak", "size": len(payload)}
            if hashed:
                entry["sha256"] = hashlib.sha256(payload).hexdigest()
            component = {"id": f"c{index}", "name": name, "files": [copy.deepcopy(entry)],
                         "types": ["Unknown"], "type": "Unknown", "enabled": True,
                         "description": "Etiqueta manual"}
            components.append(component)
            entries.append(entry)
            for base in (self.root / "library" / "example", self.root / "game" / "Hela"):
                target = base / entry["name"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
        mod = {"id": "m1", "name": "Exemplo", "character": "Hela", "skin": "Default",
               "storage_folder": "example", "folder": "Hela", "enabled": True, "external": False,
               "files": entries, "components": components, "types": ["Unknown"], "type": "Unknown",
               "identity_override": {"character": "Hela", "skin": "Correção manual"}, "tags": ["favorito"]}
        storage.save_mods([mod])
        return mod

    def private(self, mod, index=0):
        return self.root / "library" / "example" / mod["files"][index]["name"]

    def active(self, mod, index=0):
        return self.root / "game" / "Hela" / mod["files"][index]["name"]

    def test_health_finds_missing_same_size_corruption_and_preserved_orphans_read_only(self):
        mod = self.fixture()
        self.active(mod).write_bytes(b"X" * self.active(mod).stat().st_size)
        self.private(mod, 1).unlink()
        preserved = self.root / "library" / "Hela" / "Removed [old]" / "Archive" / "saved.zip"
        preserved.parent.mkdir(parents=True)
        preserved.write_bytes(b"must remain")
        before = pathlib.Path(storage.MODS_JSON).read_bytes()
        with patch.object(mod_ops, "_paths_from_bundle", side_effect=AssertionError("No extractor")):
            health = maintenance.inspect_library_health()
        self.assertTrue(health["ok"])
        self.assertEqual(health["checked"], 1)
        self.assertTrue(health["mods_path_configured"])
        issue = health["issues"][0]
        self.assertEqual(issue["missing_backup"], [mod["files"][1]["name"]])
        self.assertTrue(any(item["location"] == "game" for item in issue["hash_mismatches"]))
        self.assertEqual(health["orphans"][0]["kind"], "unregistered_storage")
        self.assertIn("Remover mod", health["orphans"][0]["message"])
        self.assertEqual(preserved.read_bytes(), b"must remain")
        self.assertEqual(pathlib.Path(storage.MODS_JSON).read_bytes(), before)
        mod_ops._record_activity.assert_not_called()

    def test_legacy_health_does_not_invent_hashes_and_reports_divergent_copies(self):
        mod = self.fixture(hashed=False)
        self.active(mod).write_bytes(b"Z" * self.active(mod).stat().st_size)
        before = pathlib.Path(storage.MODS_JSON).read_bytes()
        health = maintenance.inspect_library_health()
        self.assertEqual(len(health["issues"][0]["unverifiable"]), 2)
        self.assertEqual(health["issues"][0]["hash_mismatches"][0]["location"], "copies")
        self.assertEqual(pathlib.Path(storage.MODS_JSON).read_bytes(), before)

    def test_health_external_disabled_and_invalid_paths_do_not_escape_library(self):
        mod = self.fixture()
        mods = storage.load_mods()
        mods[0].update(external=True, enabled=False)
        self.private(mod).unlink()
        storage.save_mods(mods)
        self.assertTrue(maintenance.inspect_library_health(False)["issues"][0]["external_disabled"])
        mods = storage.load_mods()
        mods[0]["storage_folder"] = "../../outside"
        storage.save_mods(mods)
        outside = self.root / "outside"
        self.assertTrue(maintenance.inspect_library_health()["issues"][0]["unreadable"])
        self.assertFalse(maintenance.preview_library_repair("m1")["ok"])
        self.assertFalse(outside.exists())

    def test_repair_preview_and_selected_apply_preserve_sources_and_existing_files(self):
        mod = self.fixture()
        self.private(mod).unlink()
        self.active(mod, 1).unlink()
        before = pathlib.Path(storage.MODS_JSON).read_bytes()
        preview = maintenance.preview_library_repair("m1")
        self.assertEqual(len(preview["actions"]), 2)
        self.assertFalse(self.private(mod).exists())
        self.assertFalse(self.active(mod, 1).exists())
        self.assertFalse(any("source" in item or "destination" in item for item in preview["actions"]))
        action = next(item for item in preview["actions"] if item["direction"] == "backup")
        result = maintenance.apply_library_repair(preview["token"], [action["id"]])
        self.assertTrue(result["ok"])
        self.assertEqual(self.private(mod).read_bytes(), self.active(mod).read_bytes())
        self.assertFalse(self.active(mod, 1).exists())
        self.assertEqual(result["repaired_backup"], [mod["files"][0]["name"]])
        self.assertEqual(pathlib.Path(storage.MODS_JSON).read_bytes(), before)
        self.assertFalse(maintenance.apply_library_repair(preview["token"])["ok"])

    def test_repair_rejects_bad_origin_and_warns_for_unhashed_legacy(self):
        mod = self.fixture()
        self.private(mod).unlink()
        self.active(mod).write_bytes(b"bad origin")
        preview = maintenance.preview_library_repair("m1")
        self.assertEqual(preview["actions"], [])
        self.assertTrue(preview["blocked"])
        mod = self.fixture(hashed=False)
        self.private(mod).unlink()
        preview = maintenance.preview_library_repair("m1")
        self.assertEqual(preview["actions"][0]["verification"], "size")
        self.assertTrue(preview["warnings"])
        self.assertTrue(maintenance.apply_library_repair(preview["token"])["ok"])
        self.assertNotIn("sha256", storage.load_mods()[0]["files"][0])

    def test_repair_rejects_modified_source_before_any_copy(self):
        mod = self.fixture()
        self.private(mod).unlink()
        self.private(mod, 1).unlink()
        preview = maintenance.preview_library_repair("m1")
        self.active(mod, 1).write_bytes(b"changed source")
        result = maintenance.apply_library_repair(preview["token"])
        self.assertFalse(result["ok"])
        self.assertFalse(self.private(mod).exists())
        self.assertFalse(self.private(mod, 1).exists())

    def test_repair_revalidates_catalog_and_disallows_forged_actions(self):
        mod = self.fixture()
        self.private(mod).unlink()
        preview = maintenance.preview_library_repair("m1")
        self.assertFalse(maintenance.apply_library_repair(preview["token"], ["../../outside"])["ok"])
        preview = maintenance.preview_library_repair("m1")
        mods = storage.load_mods()
        mods[0]["folder"] = "Other"
        storage.save_mods(mods)
        self.assertFalse(maintenance.apply_library_repair(preview["token"])["ok"])
        self.assertFalse(self.private(mod).exists())

    def test_repair_destination_race_never_overwrites_new_file(self):
        mod = self.fixture()
        destination = self.private(mod)
        destination.unlink()
        preview = maintenance.preview_library_repair("m1")
        link = os.link

        def create_competing_file(source, target):
            pathlib.Path(target).write_bytes(b"someone else's file")
            return link(source, target)

        with patch.object(maintenance.os, "link", side_effect=create_competing_file):
            result = maintenance.apply_library_repair(preview["token"])
        self.assertFalse(result["ok"])
        self.assertEqual(destination.read_bytes(), b"someone else's file")
        self.assertFalse(list(destination.parent.glob(".repair-*.tmp")))

    def test_game_lock_and_copy_failure_leave_active_destination_absent(self):
        mod = self.fixture()
        self.active(mod).unlink()
        preview = maintenance.preview_library_repair("m1")
        with patch.object(mod_ops, "_ensure_game_operation_allowed", side_effect=OSError("Jogo em execução")):
            result = maintenance.apply_library_repair(preview["token"])
        self.assertFalse(result["ok"])
        self.assertFalse(self.active(mod).exists())
        preview = maintenance.preview_library_repair("m1")
        with patch.object(maintenance.os, "fsync", side_effect=OSError("Disk full")):
            result = maintenance.apply_library_repair(preview["token"])
        self.assertFalse(result["ok"])
        self.assertFalse(self.active(mod).exists())
        self.assertFalse(list(self.active(mod).parent.glob(".repair-*.tmp")))

    def test_expired_repair_is_not_applied(self):
        mod = self.fixture()
        self.private(mod).unlink()
        preview = maintenance.preview_library_repair("m1")
        maintenance._REPAIR_PLANS[preview["token"]]["created"] -= maintenance._PLAN_LIFETIME + 1
        self.assertFalse(maintenance.apply_library_repair(preview["token"])["ok"])
        self.assertFalse(self.private(mod).exists())

    def test_pending_list_reads_no_packages_and_includes_disabled_components(self):
        mod = self.fixture(names=("First", "Second", "Third"))
        mods = storage.load_mods()
        mods[0]["components"][1]["enabled"] = False
        files = [str(self.private(mod))]
        mods[0]["asset_path_cache"] = {"classification-v1:c0": {
            "signature": mod_ops._component_analysis_signature(files),
            "paths": ["Marvel/Content/Meshes/SK_Hero.uasset"]}}
        storage.save_mods(mods)
        self.private(mod, 2).unlink()
        self.active(mod, 2).unlink()
        before = pathlib.Path(storage.MODS_JSON).read_bytes()
        with patch.object(mod_ops, "_paths_from_bundle", side_effect=AssertionError("No extraction")):
            pending = maintenance.list_pending_classifications()
        self.assertEqual([item["component_id"] for item in pending["components"]], ["c1", "c2"])
        self.assertEqual(pending["counts"]["pending"], 1)
        self.assertEqual(pending["counts"]["missing"], 1)
        self.assertEqual(pathlib.Path(storage.MODS_JSON).read_bytes(), before)

    def test_selected_reanalysis_preserves_manual_fields_and_does_not_read_siblings(self):
        mod = self.fixture(names=("First", "Second"))
        before = storage.load_mods()[0]
        with patch.object(mod_ops, "_paths_from_bundle", return_value=["Marvel/Content/Meshes/SK_Hero.uasset"]) as reader:
            result = maintenance.reanalyze_selected_components([{"mod_id": "m1", "component_id": "c0"}])
        reader.assert_called_once_with([str(self.private(mod))])
        self.assertEqual(result["changed"], 1)
        current = storage.load_mods()[0]
        for key in ("identity_override", "character", "skin", "tags", "enabled", "folder"):
            self.assertEqual(current[key], before[key])
        self.assertEqual(current["components"][1], before["components"][1])
        self.assertEqual(current["components"][0]["description"], "Etiqueta manual")
        self.assertEqual(current["components"][0]["types"], ["Mesh"])

    def test_reanalysis_preserves_concurrent_identity_names_and_switches(self):
        self.fixture(names=("First", "Second"))

        def edit_during_read(files):
            mods = storage.load_mods()
            mods[0]["identity_override"]["skin"] = "New manual skin"
            mods[0]["components"][0].update(name="Renamed", enabled=False)
            storage.save_mods(mods)
            return ["Marvel/Content/Textures/T_Hero.uasset"]

        with patch.object(mod_ops, "_paths_from_bundle", side_effect=edit_during_read):
            result = maintenance.reanalyze_selected_components([{"mod_id": "m1", "component_id": "c0"}])
        self.assertEqual(result["changed"], 1)
        current = storage.load_mods()[0]
        self.assertEqual(current["identity_override"]["skin"], "New manual skin")
        self.assertEqual(current["components"][0]["name"], "Renamed")
        self.assertFalse(current["components"][0]["enabled"])

    def test_reanalysis_error_persists_and_does_not_replace_previous_types(self):
        self.fixture(names=("First", "Second"))
        mods = storage.load_mods()
        mods[0]["components"][0].update(types=["Mesh"], type="Mesh")
        storage.save_mods(mods)
        with patch.object(mod_ops, "_paths_from_bundle", return_value=[]):
            result = maintenance.reanalyze_selected_components([{"mod_id": "m1", "component_id": "c0"}])
        self.assertEqual(result["failed"], 1)
        self.assertEqual(storage.load_mods()[0]["components"][0]["types"], ["Mesh"])
        mod_ops._COMPONENT_ANALYSIS_RETRY.clear()
        pending = maintenance.list_pending_classifications()
        self.assertEqual(pending["components"][0]["status"], "read_error")

    def test_reanalysis_does_not_overwrite_a_concurrent_type_correction(self):
        self.fixture(names=("First",))

        def manual_correction(files):
            mods = storage.load_mods()
            mods[0]["components"][0].update(types=["UI"], type="UI")
            storage.save_mods(mods)
            return ["Marvel/Content/Meshes/SK_Hero.uasset"]

        with patch.object(mod_ops, "_paths_from_bundle", side_effect=manual_correction):
            result = maintenance.reanalyze_selected_components([{"mod_id": "m1", "component_id": "c0"}])
        self.assertEqual(result["changed"], 0)
        self.assertEqual(storage.load_mods()[0]["components"][0]["types"], ["UI"])

    def test_reanalysis_does_not_apply_assets_if_package_changes_during_read(self):
        mod = self.fixture(names=("First",))
        before = storage.load_mods()

        def changed_package(files):
            pathlib.Path(files[0]).write_bytes(b"new package arrived")
            return ["Marvel/Content/Meshes/SK_Old.uasset"]

        with patch.object(mod_ops, "_paths_from_bundle", side_effect=changed_package):
            result = maintenance.reanalyze_selected_components([{"mod_id": "m1", "component_id": "c0"}])
        self.assertEqual(result["changed"], 0)
        self.assertEqual(storage.load_mods(), before)
        self.assertEqual(self.private(mod).read_bytes(), b"new package arrived")

    def test_pending_status_invalidates_old_read_error_after_package_changes(self):
        mod = self.fixture(names=("First",))
        signature = mod_ops._component_analysis_signature([str(self.private(mod))])
        mod_ops._COMPONENT_ANALYSIS_RETRY[("m1", "c0")] = (signature, 100)
        self.assertEqual(maintenance.list_pending_classifications()["components"][0]["status"], "read_error")
        self.private(mod).write_bytes(b"updated package")
        self.assertEqual(maintenance.list_pending_classifications()["components"][0]["status"], "pending")

    def test_relation_suggestions_are_read_only_and_mask_families_stay_separate(self):
        self.fixture(names=("Hero_Mask_On", "Hero_Mask_Off", "Other_Mask_Off"))
        before = pathlib.Path(storage.MODS_JSON).read_bytes()
        with patch.object(mod_ops, "_paths_from_bundle", side_effect=AssertionError("No extraction")):
            result = maintenance.suggest_component_relations("m1")
        self.assertEqual(len(result["suggestions"]), 1)
        self.assertEqual(result["suggestions"][0]["component_ids"], ["c0", "c1"])
        self.assertEqual(result["suggestions"][0]["kind"], "alternative_group")
        self.assertEqual(pathlib.Path(storage.MODS_JSON).read_bytes(), before)

    def test_separate_mask_families_do_not_share_an_exclusive_group(self):
        self.fixture(names=("Hero_Mask_On", "Hero_Mask_Off", "Other_Mask_On", "Other_Mask_Off"))
        suggestions = maintenance.suggest_component_relations("m1")["suggestions"]
        self.assertEqual(len(suggestions), 2)
        self.assertNotEqual(suggestions[0]["proposed_group"], suggestions[1]["proposed_group"])
        for preferred in ("c0", "c2"):
            suggestion = next(item for item in maintenance.suggest_component_relations("m1")["suggestions"]
                              if preferred in item["component_ids"])
            preview = maintenance.preview_relation_suggestion("m1", suggestion["id"], preferred)
            self.assertTrue(preview["ok"], preview)
            self.assertTrue(maintenance.apply_relation_suggestion(preview["token"])["ok"])
        current = storage.load_mods()[0]
        self.assertEqual([item["id"] for item in current["components"] if item["enabled"]], ["c0", "c2"])

    def test_alternative_suggestions_do_not_break_transitive_dependencies(self):
        self.fixture(names=("Hero_Mask_On", "Hero_Mask_Off", "Support"))
        mods = storage.load_mods()
        mods[0]["components"][0]["requires"] = ["c2"]
        mods[0]["components"][2]["requires"] = ["c1"]
        storage.save_mods(mods)
        result = maintenance.suggest_component_relations("m1")
        self.assertTrue(result["ok"])
        self.assertEqual(result["suggestions"], [])

    def test_physics_dependency_is_only_a_review_candidate_for_a_matching_base(self):
        self.fixture(names=("Hero", "Alien", "Hero_Physics", "Unrelated_Physics"))
        mods = storage.load_mods()
        for index, component in enumerate(mods[0]["components"]):
            types = ["Mesh"] if index < 2 else ["Physics"]
            component.update(types=types, type=types[0])
        storage.save_mods(mods)
        before = pathlib.Path(storage.MODS_JSON).read_bytes()
        suggestions = maintenance.suggest_component_relations("m1")["suggestions"]
        self.assertEqual(len(suggestions), 1)
        suggestion = suggestions[0]
        self.assertEqual(suggestion["component_id"], "c2")
        self.assertEqual(suggestion["requires"], ["c0"])
        self.assertEqual(suggestion["confidence"], "review_required")
        self.assertIn("não comprovam", suggestion["warnings"][0])
        self.assertEqual(pathlib.Path(storage.MODS_JSON).read_bytes(), before)

    def test_physics_suggestions_do_not_introduce_a_transitive_cycle(self):
        self.fixture(names=("Hero", "Support", "Hero_Physics"))
        mods = storage.load_mods()
        for index, component in enumerate(mods[0]["components"]):
            value = ("Mesh", "UI", "Physics")[index]
            component.update(types=[value], type=value)
        mods[0]["components"][0]["requires"] = ["c1"]
        mods[0]["components"][1]["requires"] = ["c2"]
        storage.save_mods(mods)
        self.assertEqual(maintenance.suggest_component_relations("m1")["suggestions"], [])

    def test_relation_preview_applies_whole_group_once_with_reviewed_state_changes(self):
        mod = self.fixture()
        suggestion = maintenance.suggest_component_relations("m1")["suggestions"][0]
        preview = maintenance.preview_relation_suggestion("m1", suggestion["id"], "c1")
        self.assertTrue(preview["ok"])
        self.assertEqual(len(preview["rule_changes"]), 2)
        self.assertEqual(preview["state_changes"], [{"component_id": "c0", "name": mod["components"][0]["name"],
                                                    "before": True, "after": False}])
        self.assertTrue(self.active(mod).exists())
        mods = storage.load_mods()
        mods[0]["components"][0]["description"] = "Editada durante a revisão"
        storage.save_mods(mods)
        with patch.object(storage, "save_mods", wraps=storage.save_mods) as save:
            result = maintenance.apply_relation_suggestion(preview["token"])
        self.assertTrue(result["ok"])
        self.assertEqual(save.call_count, 1)
        current = storage.load_mods()[0]
        self.assertEqual([item["exclusive_group"] for item in current["components"]], ["Máscara", "Máscara"])
        self.assertEqual(current["components"][0]["description"], "Editada durante a revisão")
        self.assertFalse(self.active(mod).exists())
        self.assertTrue(self.active(mod, 1).exists())
        self.assertTrue(self.private(mod).exists())
        self.assertFalse(maintenance.apply_relation_suggestion(preview["token"])["ok"])

    def test_relation_save_failure_rolls_back_game_and_catalog(self):
        mod = self.fixture()
        before = storage.load_mods()
        suggestion = maintenance.suggest_component_relations("m1")["suggestions"][0]
        preview = maintenance.preview_relation_suggestion("m1", suggestion["id"], "c1")
        with patch.object(storage, "save_mods", side_effect=OSError("Disk full")):
            result = maintenance.apply_relation_suggestion(preview["token"])
        self.assertFalse(result["ok"])
        self.assertEqual(storage.load_mods(), before)
        self.assertEqual(self.active(mod).read_bytes(), self.private(mod).read_bytes())
        self.assertEqual(self.active(mod, 1).read_bytes(), self.private(mod, 1).read_bytes())

    def test_relation_preview_rejects_wrong_preference_and_stale_metadata(self):
        mod = self.fixture()
        suggestion = maintenance.suggest_component_relations("m1")["suggestions"][0]
        self.assertFalse(maintenance.preview_relation_suggestion("m1", suggestion["id"], "other-mod")["ok"])
        preview = maintenance.preview_relation_suggestion("m1", suggestion["id"])
        mods = storage.load_mods()
        mods[0]["components"][0]["enabled"] = False
        storage.save_mods(mods)
        self.assertFalse(maintenance.apply_relation_suggestion(preview["token"])["ok"])
        self.assertTrue(self.active(mod).exists())

    def test_relation_preview_rejects_paths_outside_both_roots(self):
        self.fixture()
        outside = self.root / "outside.pak"
        outside.write_bytes(b"do not touch")
        mods = storage.load_mods()
        mods[0]["components"][0]["files"][0]["name"] = "../../outside.pak"
        storage.save_mods(mods)
        before = pathlib.Path(storage.MODS_JSON).read_bytes()
        suggestion = maintenance.suggest_component_relations("m1")["suggestions"][0]
        preview = maintenance.preview_relation_suggestion("m1", suggestion["id"], "c1")
        self.assertFalse(preview["ok"])
        self.assertEqual(outside.read_bytes(), b"do not touch")
        self.assertEqual(pathlib.Path(storage.MODS_JSON).read_bytes(), before)

    def test_relation_apply_rejects_changed_asset_evidence(self):
        mod = self.fixture()
        suggestion = maintenance.suggest_component_relations("m1")["suggestions"][0]
        preview = maintenance.preview_relation_suggestion("m1", suggestion["id"], "c1")
        mods = storage.load_mods()
        mods[0]["asset_path_cache"] = {"classification-v1:c0": {
            "paths": ["Marvel/Content/Textures/T_New.uasset"]}}
        storage.save_mods(mods)
        current = storage.load_mods()
        self.assertFalse(maintenance.apply_relation_suggestion(preview["token"])["ok"])
        self.assertEqual(storage.load_mods(), current)
        self.assertTrue(self.active(mod).exists())


if __name__ == "__main__":
    unittest.main()
