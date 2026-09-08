import copy
import hashlib
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from backend import component_rules, mod_ops, personal_corrections as corrections, storage


class PersonalCorrectionTests(unittest.TestCase):
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
        corrections._OFFERS.clear()

    def component(self, cid, content, name=None, **extra):
        return {"id": cid, "name": name or cid, "files": [
            {"name": f"Components/{cid}/{cid}{ext}", "original_name": f"{cid}{ext}",
             "sha256": hashlib.sha256((content + ext).encode()).hexdigest(), "size": len(content + ext)}
            for ext in (".pak", ".utoc", ".ucas")], "enabled": True, "types": ["Mesh", "Texture"], **extra}

    def mod(self, components, mid="old", **extra):
        return {"id": mid, "name": "Minhas escolhas", "character": "Hela", "skin": "Default",
                "identity_override": {"character": "Hela", "skin": "Default"}, "components": components, **extra}

    def plan(self, components):
        return {"components": components, "sources": {e["name"]: str(self.root / e["name"])
                                                       for c in components for e in c["files"]}}

    def offer(self, plan):
        offers = corrections.suggest_for_import(plan)["offers"]
        self.assertEqual(len(offers), 1, offers)
        return offers[0]

    def apply(self, plan, offer, **meta):
        return corrections.apply_import_choice(plan, {"personal_correction_choice": offer["id"],
            **(offer["identity"] or {"character": "Storm", "skin": "Default"}), **meta})

    def test_all_files_identify_renamed_component_and_preserve_detected_types(self):
        old = self.component("old_id", "A", "Meu nome", description="Principal")
        storage.save_mods([self.mod([old])])
        new = self.component("new_id", "A", "Novo arquivo", types=["Unknown"], asset_paths=["Current"])
        plan = self.plan([new])
        before = copy.deepcopy(plan)
        offer = self.offer(plan)
        restored, meta = self.apply(plan, offer)
        self.assertTrue(offer["exact_match"])
        self.assertEqual(meta["character"], "Hela")
        self.assertEqual(restored["components"][0]["name"], "Meu nome")
        self.assertEqual(restored["components"][0]["description"], "Principal")
        self.assertEqual(restored["components"][0]["id"], "new_id")
        self.assertEqual(restored["components"][0]["types"], ["Unknown"])
        self.assertEqual(restored["components"][0]["asset_paths"], ["Current"])
        self.assertEqual(plan, before)

    def test_matching_one_file_of_trio_is_insufficient(self):
        old = self.component("a", "A", "Guardado")
        storage.save_mods([self.mod([old])])
        changed = self.component("b", "A")
        changed["files"][2]["sha256"] = "1" * 64
        self.assertEqual(corrections.suggest_for_import(self.plan([changed]))["offers"], [])

    def test_partial_import_recovers_only_matching_metadata_not_identity(self):
        storage.save_mods([self.mod([self.component("a", "A", "Minha variante"), self.component("b", "B")])])
        plan = self.plan([self.component("c", "A")])
        offer = self.offer(plan)
        self.assertFalse(offer["exact_match"])
        self.assertIsNone(offer["identity"])
        restored, meta = self.apply(plan, offer)
        self.assertEqual(meta["character"], "Storm")
        self.assertEqual(restored["components"][0]["name"], "Minha variante")

    def test_component_duplicate_content_never_guesses_names_or_relations(self):
        storage.save_mods([self.mod([self.component("a", "A", "Um"), self.component("b", "A", "Dois")])])
        plan = self.plan([self.component("x", "A"), self.component("y", "A")])
        offer = self.offer(plan)
        self.assertEqual(offer["matched_components"], 0)
        self.assertEqual(offer["changes"], [])
        self.assertTrue(offer["exact_match"])
        self.assertTrue(offer["warnings"])
        restored, _ = self.apply(plan, offer)
        self.assertEqual([c["name"] for c in restored["components"]], ["x", "y"])

    def test_conflicting_saved_choices_are_separate_explicit_offers(self):
        storage.save_mods([self.mod([self.component("a", "A", "Nome A")], mid="one"),
                           self.mod([self.component("b", "A", "Nome B")], mid="two", character="Storm")])
        plan = self.plan([self.component("x", "A")])
        offers = corrections.suggest_for_import(plan)["offers"]
        self.assertEqual(len(offers), 2)
        unchanged, meta = corrections.apply_import_choice(plan, {"character": "Generic"})
        self.assertIs(unchanged, plan)
        self.assertEqual(meta["character"], "Generic")

    def test_rules_remap_dependency_ids_and_preview_switch_adjustments(self):
        a = self.component("a", "A", exclusive_group="Roupa")
        b = self.component("b", "B", exclusive_group="Roupa")
        physics = self.component("physics", "P", requires=["a"], types=["Physics"])
        storage.save_mods([self.mod([a, b, physics])])
        plan = self.plan([self.component("new_a", "A"), self.component("new_b", "B"),
                          self.component("new_p", "P", types=["Physics"])])
        offer = self.offer(plan)
        self.assertTrue(offer["state_changes"])
        restored, _ = self.apply(plan, offer)
        component_rules.assert_valid_state(restored["components"])
        self.assertEqual(restored["components"][2]["requires"], ["new_a"])
        self.assertEqual(restored["components"][2]["types"], ["Physics"])
        differences = {c["id"]: c["enabled"] for c in restored["components"] if not c["enabled"]}
        self.assertEqual(differences, {item["component_id"]: item["after"] for item in offer["state_changes"]})

    def test_partial_dependencies_and_groups_are_not_applied(self):
        a = self.component("a", "A", "Minha versão", exclusive_group="Roupa", requires=["physics"])
        b = self.component("b", "B", exclusive_group="Roupa")
        p = self.component("physics", "P")
        storage.save_mods([self.mod([a, b, p])])
        plan = self.plan([self.component("new_a", "A")])
        offer = self.offer(plan)
        restored, _ = self.apply(plan, offer)
        self.assertNotIn("requires", restored["components"][0])
        self.assertNotIn("exclusive_group", restored["components"][0])
        self.assertEqual(restored["components"][0]["name"], "Minha versão")
        self.assertGreaterEqual(len(offer["warnings"]), 2)

    def test_cycles_do_not_enter_import_plan(self):
        storage.save_mods([self.mod([self.component("a", "A", requires=["b"]),
                                     self.component("b", "B", requires=["a"])])])
        plan = self.plan([self.component("x", "A"), self.component("y", "B")])
        offer = self.offer(plan)
        restored, _ = self.apply(plan, offer)
        self.assertTrue(any("ciclo" in message for message in offer["warnings"]))
        self.assertTrue(all(not c.get("requires") for c in restored["components"]))
        component_rules.assert_valid_state(restored["components"])

    def test_changes_after_offer_reject_without_mutating_plan(self):
        storage.save_mods([self.mod([self.component("a", "A", "Antes")])])
        plan = self.plan([self.component("x", "A")])
        offer = self.offer(plan)
        mods = storage.load_mods()
        mods[0]["components"][0]["name"] = "Depois"
        storage.save_mods(mods)
        with self.assertRaisesRegex(ValueError, "mudaram"):
            self.apply(plan, offer)
        self.assertEqual(plan["components"][0]["name"], "x")

    def test_plan_or_identity_changes_and_replayed_token_are_rejected(self):
        storage.save_mods([self.mod([self.component("a", "A")])])
        plan = self.plan([self.component("x", "A")])
        offer = self.offer(plan)
        with self.assertRaisesRegex(ValueError, "identidade foi editada"):
            self.apply(plan, offer, character="Storm")
        with self.assertRaisesRegex(ValueError, "expirou"):
            self.apply(plan, offer)
        offer = self.offer(plan)
        plan["components"][0]["enabled"] = False
        with self.assertRaisesRegex(ValueError, "seleção.*mudou"):
            self.apply(plan, offer)

    def test_legacy_hashes_are_used_without_reading_assets_or_hashing_library(self):
        storage.save_mods([self.mod([self.component("a", "A", "Nome legado")])])
        with patch.object(mod_ops, "_mod_source_files", side_effect=AssertionError("Não abrir arquivos")), \
             patch.object(mod_ops.operation_jobs, "hash_file", side_effect=AssertionError("Não hashear biblioteca")):
            self.offer(self.plan([self.component("x", "A")]))
        self.assertFalse(pathlib.Path(storage.personal_corrections_path()).exists())

    def test_missing_hash_does_not_offer_identity_even_when_other_component_matches(self):
        old = self.mod([self.component("a", "A", "Minha versão"), self.component("b", "B")])
        old["components"][1]["files"][0].pop("sha256")
        storage.save_mods([old])
        offer = self.offer(self.plan([self.component("x", "A"), self.component("y", "B")]))
        self.assertIsNone(offer["identity"])
        self.assertEqual(offer["matched_components"], 1)

    def test_legacy_hashes_do_not_require_saved_sizes(self):
        old = self.mod([self.component("a", "A", "Meu nome")])
        for entry in old["components"][0]["files"]:
            entry.pop("size")
        storage.save_mods([old])
        plan = self.plan([self.component("x", "A")])
        offer = self.offer(plan)
        self.assertTrue(offer["exact_match"])
        restored, _ = self.apply(plan, offer)
        self.assertEqual(restored["components"][0]["name"], "Meu nome")

    def test_manual_hooks_persist_names_labels_rules_after_record_removal(self):
        storage.save_mods([self.mod([self.component("a", "A"), self.component("b", "B")], enabled=False)])
        self.assertTrue(mod_ops.rename_component("old", "a", "Guardado")["ok"])
        self.assertTrue(mod_ops.set_component_description("old", "a", "Principal")["ok"])
        self.assertTrue(mod_ops.set_components_description("old", ["b"], "Extra")["ok"])
        self.assertTrue(mod_ops.set_component_rules("old", "b", "", ["a"])["ok"])
        ledger = storage.load_personal_corrections()
        self.assertEqual(len(ledger["records"]), 1)
        storage.save_mods([])
        plan = self.plan([self.component("x", "A"), self.component("y", "B")])
        offer = self.offer(plan)
        restored, _ = self.apply(plan, offer)
        self.assertEqual(restored["components"][0]["name"], "Guardado")
        self.assertEqual(restored["components"][0]["description"], "Principal")
        self.assertEqual(restored["components"][1]["description"], "Extra")
        self.assertEqual(restored["components"][1]["requires"], ["x"])

    def test_empty_label_and_removed_rules_replace_old_saved_values(self):
        storage.save_mods([self.mod([self.component("a", "A", description="Antes", exclusive_group="Roupa")], enabled=False)])
        mod_ops.set_component_description("old", "a", "")
        mod_ops.set_component_rules("old", "a", "", [])
        storage.save_mods([])
        plan = self.plan([self.component("x", "A", description="Automático", exclusive_group="Novo")])
        offer = self.offer(plan)
        restored, _ = self.apply(plan, offer)
        self.assertEqual(restored["components"][0]["description"], "")
        self.assertEqual(restored["components"][0]["exclusive_group"], "")

    def test_history_write_failure_does_not_report_primary_edit_as_failed(self):
        storage.save_mods([self.mod([self.component("a", "A")])])
        with patch.object(storage, "save_personal_corrections", side_effect=OSError("disk full")):
            result = mod_ops.rename_component("old", "a", "Nome salvo")
        self.assertTrue(result["ok"])
        self.assertTrue(result["warnings"])
        self.assertEqual(storage.load_mods()[0]["components"][0]["name"], "Nome salvo")

    def test_generic_identity_is_remembered_explicitly_after_removal(self):
        storage.save_mods([self.mod([self.component("a", "A")], enabled=False, folder="Hela/Default/Package")])
        with patch.object(mod_ops, "_sync_storage_location"):
            result = mod_ops.set_mod_identity("old", "Generic", "")
        self.assertTrue(result["ok"])
        storage.save_mods([])
        plan = self.plan([self.component("x", "A")])
        offer = self.offer(plan)
        self.assertEqual(offer["identity"], {"character": "Generic", "skin": ""})
        _, meta = self.apply(plan, offer)
        self.assertEqual(meta["character"], "Generic")

    def test_valid_switch_state_does_not_restore_previous_enabled_values(self):
        storage.save_mods([self.mod([self.component("a", "A", exclusive_group="Roupa", enabled=False),
                                    self.component("b", "B", exclusive_group="Roupa", enabled=True)])])
        plan = self.plan([self.component("x", "A", enabled=True), self.component("y", "B", enabled=False)])
        offer = self.offer(plan)
        self.assertEqual(offer["state_changes"], [])
        restored, _ = self.apply(plan, offer)
        self.assertEqual([c["enabled"] for c in restored["components"]], [True, False])

    def test_malformed_history_rows_cannot_break_import_preparation(self):
        storage.save_personal_corrections({"version": 1, "records": [
            "bad", {"id": "broken", "components": [{"id": "a"}]},
            {"id": "other", "components": "invalid"}]})
        result = corrections.suggest_for_import(self.plan([self.component("x", "A")]))
        self.assertTrue(result["ok"])
        self.assertEqual(result["offers"], [])

    def test_primary_save_failure_does_not_remember_failed_edit(self):
        storage.save_mods([self.mod([self.component("a", "A")])])
        with patch.object(storage, "save_mods", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                mod_ops.rename_component("old", "a", "Não salvo")
        self.assertFalse(pathlib.Path(storage.personal_corrections_path()).exists())

    def test_add_mod_applies_explicit_choice_before_paths_and_preserves_bytes(self):
        settings = storage.load_settings()
        settings["mods_path"] = str(self.root / "game")
        storage.save_settings(settings)
        files = []
        for name in ("A", "B"):
            for ext in (".pak", ".utoc", ".ucas"):
                path = self.root / (name + ext)
                path.write_bytes((name + ext).encode())
                files.append(str(path))
        storage.save_mods([self.mod([self.component("old_a", "A", "Roupinha", exclusive_group="Roupa"),
                                    self.component("old_b", "B", "Alternativa", exclusive_group="Roupa")])])
        with patch.object(mod_ops, "_ensure_game_operation_allowed"), \
             patch.object(mod_ops, "_paths_from_bundle", return_value=["Marvel/Content/Meshes/SK_Hero.uasset"]):
            plan = mod_ops.prepare_mod_import(files)
            offer = self.offer(plan)
            result = mod_ops.add_mod(files, {"name": "Nova importação", "character": "Hela", "skin": "Default",
                                             "_import_plan": plan, "personal_correction_choice": offer["id"]})
        self.assertEqual(result["types"], ["Mesh"])
        self.assertEqual([c["name"] for c in result["components"]], ["Roupinha", "Alternativa"])
        self.assertEqual([c["enabled"] for c in result["components"]], [True, False])
        self.assertIn("Hela", result["folder"])
        component_rules.assert_valid_state(result["components"])
        private = pathlib.Path(mod_ops._storage_dir(result))
        for entry, source in zip(result["files"], files):
            self.assertEqual((private / entry["name"]).read_bytes(), pathlib.Path(source).read_bytes())
        self.assertTrue(any(r["id"] == result["id"] for r in storage.load_personal_corrections()["records"]))


if __name__ == "__main__":
    unittest.main()
