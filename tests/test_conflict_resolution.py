import copy
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from backend import conflict_resolution, mod_ops, operation_recovery, storage


class ConflictResolutionTests(unittest.TestCase):
    asset = "Marvel/Content/Meshes/SK_Hero.uasset"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.game = self.root / "game"
        self.game.mkdir()
        patched = patch.multiple(storage, MODS_JSON=str(self.root / "mods.json"),
                                 SETTINGS_FILE=str(self.root / "settings.json"),
                                 STORAGE_DIR=str(self.root / "library"), BACKUPS_DIR=str(self.root / "backups"))
        patched.start()
        self.addCleanup(patched.stop)
        storage.ensure_dirs()
        settings = storage.load_settings()
        settings["mods_path"] = str(self.game)
        storage.save_settings(settings)
        guard = patch.object(mod_ops, "_ensure_game_operation_allowed")
        self.guard = guard.start()
        self.addCleanup(guard.stop)
        self.paths = {}
        reader = patch.object(mod_ops, "_paths_from_bundle", side_effect=self.read_assets)
        reader.start()
        self.addCleanup(reader.stop)
        with conflict_resolution._PREVIEW_LOCK:
            conflict_resolution._PREVIEWS.clear()

    def read_assets(self, files):
        for file in files:
            key = pathlib.Path(file).stem
            if key in self.paths:
                return self.paths[key]
        return [self.asset]

    def mod(self, ident, character="Hela", components=None, external=False, priority=1):
        components = components or [(ident + "c", {})]
        mod = {"id": ident, "name": ident, "character": character, "skin": "Default", "priority": priority,
               "folder": ident, "storage_folder": ident, "enabled": True, "external": external, "files": [], "components": []}
        for cid, extra in components:
            component = {"id": cid, "name": cid, "enabled": True, "type": "Mesh", "types": ["Mesh"], "files": [], **extra}
            for extension in (".pak", ".utoc", ".ucas"):
                entry = {"name": f"Components/{cid}/{cid}{extension}"}
                component["files"].append(entry)
                mod["files"].append(entry)
                content = (ident + cid + extension).encode()
                active = self.game / ident / entry["name"]
                active.parent.mkdir(parents=True, exist_ok=True)
                if component["enabled"]:
                    active.write_bytes(content)
                if not external:
                    private = pathlib.Path(storage.STORAGE_DIR) / ident / entry["name"]
                    private.parent.mkdir(parents=True, exist_ok=True)
                    private.write_bytes(content)
            mod["components"].append(component)
        return mod

    def save(self, *mods):
        storage.save_mods(list(mods))

    def snapshot(self):
        return {path.relative_to(self.game).as_posix(): path.read_bytes() for path in self.game.rglob("*") if path.is_file()}

    def preview(self, mod_id="a", component_id="ac"):
        result = conflict_resolution.preview_resolution(mod_id, component_id)
        self.assertTrue(result["ok"], result)
        return result

    def test_preview_is_read_only_even_when_cache_is_cold(self):
        self.save(self.mod("a"), self.mod("b"))
        before = pathlib.Path(storage.MODS_JSON).read_bytes()
        settings = pathlib.Path(storage.SETTINGS_FILE).read_bytes()
        files = self.snapshot()
        result = self.preview()
        self.assertEqual([(c["mod_id"], c["component_id"]) for c in result["changes"]], [("b", "bc")])
        self.assertEqual(pathlib.Path(storage.MODS_JSON).read_bytes(), before)
        self.assertEqual(pathlib.Path(storage.SETTINGS_FILE).read_bytes(), settings)
        self.assertEqual(self.snapshot(), files)
        self.assertEqual(storage.list_operation_journals(), [])

    def test_choice_disables_rival_and_dependents_but_preserves_priorities_and_backups(self):
        a = self.mod("a", priority=1)
        b = self.mod("b", priority=10, components=[("bc", {}), ("bd", {"requires": ["bc"]})])
        self.paths["bd"] = ["Marvel/Content/Textures/T_OnlyAddon.uasset"]
        self.save(a, b)
        kept = {name: data for name, data in self.snapshot().items() if name.startswith("a/")}
        preview = self.preview()
        self.assertEqual({row["reason"] for row in preview["changes"]}, {"conflict", "dependency"})
        result = conflict_resolution.apply_resolution(preview["token"])
        self.assertTrue(result["ok"], result)
        by_id = {m["id"]: m for m in storage.load_mods()}
        self.assertEqual([c["enabled"] for c in by_id["b"]["components"]], [False, False])
        self.assertTrue(by_id["a"]["components"][0]["enabled"])
        self.assertEqual([by_id["a"]["priority"], by_id["b"]["priority"]], [1, 10])
        self.assertEqual(self.snapshot(), kept)
        self.assertTrue(all((pathlib.Path(mod_ops._storage_dir(b)) / e["name"]).is_file() for e in b["files"]))
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_dependency_of_selected_component_cannot_be_disabled(self):
        a = self.mod("a", components=[("ac", {"requires": ["base"]}), ("base", {"description": "Principal"})])
        self.save(a)
        before = self.snapshot()
        result = conflict_resolution.preview_resolution("a", "ac")
        self.assertFalse(result["ok"])
        self.assertIn("permanecer", result["error"])
        self.assertEqual(self.snapshot(), before)

    def test_explicit_principal_choice_disables_only_its_rival_in_the_same_mod(self):
        a = self.mod("a", components=[("ac", {}), ("alternate", {"description": "Principal"}),
                                      ("addon", {"types": ["Texture"], "type": "Texture"})])
        self.paths["addon"] = ["Marvel/Content/Textures/T_OnlyAddon.uasset"]
        self.save(a)
        before = self.snapshot()
        preview = self.preview()
        self.assertEqual([(row["mod_id"], row["component_id"]) for row in preview["changes"]], [("a", "alternate")])
        result = conflict_resolution.apply_resolution(preview["token"])
        self.assertTrue(result["ok"], result)
        saved = storage.load_mods()[0]
        self.assertTrue(saved["enabled"])
        self.assertEqual([component["enabled"] for component in saved["components"]], [True, False, True])
        expected = {name: content for name, content in before.items() if "/alternate/" not in name}
        self.assertEqual(self.snapshot(), expected)

    def test_same_asset_in_an_unrelated_identity_is_not_disabled(self):
        self.save(self.mod("a"), self.mod("b"), self.mod("c", "Storm"), self.mod("d", "Storm"))
        preview = self.preview()
        self.assertEqual({row["mod_id"] for row in preview["changes"]}, {"b"})
        result = conflict_resolution.apply_resolution(preview["token"])
        self.assertTrue(result["ok"], result)
        self.assertTrue(all(c["enabled"] for m in storage.load_mods() if m["id"] in {"c", "d"} for c in m["components"]))

    def test_manual_choice_does_not_sweep_up_unrelated_automatic_rivals(self):
        a, b = self.mod("a"), self.mod("b")
        c, d = self.mod("c", "Storm"), self.mod("d", "Storm")
        a["manual_conflicts"] = ["c"]
        self.save(a, b, c, d)
        preview = self.preview("a", "manual-conflict")
        self.assertEqual({row["mod_id"] for row in preview["changes"]}, {"b", "c"})
        self.assertTrue(conflict_resolution.apply_resolution(preview["token"])["ok"])
        by_id = {mod["id"]: mod for mod in storage.load_mods()}
        self.assertTrue(by_id["a"]["enabled"])
        self.assertFalse(by_id["b"]["components"][0]["enabled"])
        self.assertFalse(by_id["c"]["enabled"])
        self.assertTrue(by_id["d"]["components"][0]["enabled"])

    def test_manual_conflict_disables_whole_mod_and_preserves_its_variant_choices(self):
        a = self.mod("a")
        b = self.mod("b", "Storm", components=[("bc", {}), ("bd", {"enabled": False})])
        a["manual_conflicts"] = ["b"]
        self.save(a, b)
        preview = self.preview("a", "manual-conflict")
        self.assertEqual(preview["changes"][0]["component_id"], "whole-mod")
        self.assertEqual(preview["changes"][0]["reason"], "manual_conflict")
        self.assertTrue(conflict_resolution.apply_resolution(preview["token"])["ok"])
        saved = next(m for m in storage.load_mods() if m["id"] == "b")
        self.assertFalse(saved["enabled"])
        self.assertEqual([c["enabled"] for c in saved["components"]], [True, False])
        self.assertFalse(any(name.startswith("b/") for name in self.snapshot()))

    def test_new_competitor_invalidates_the_preview(self):
        self.save(self.mod("a"), self.mod("b"))
        preview = self.preview()
        mods = storage.load_mods()
        mods.append(self.mod("c"))
        storage.save_mods(mods)
        before = self.snapshot()
        result = conflict_resolution.apply_resolution(preview["token"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["stale"])
        self.assertEqual(self.snapshot(), before)

    def test_file_change_invalidates_the_preview(self):
        a, b = self.mod("a"), self.mod("b")
        self.save(a, b)
        preview = self.preview()
        changed_file = self.game / b["folder"] / b["files"][0]["name"]
        changed_file.write_bytes(b"changed since preview")
        result = conflict_resolution.apply_resolution(preview["token"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["stale"])
        self.assertEqual(changed_file.read_bytes(), b"changed since preview")

    def test_game_lock_blocks_the_application_before_any_mutation(self):
        self.save(self.mod("a"), self.mod("b"))
        preview = self.preview()
        before = self.snapshot()
        self.guard.side_effect = OSError("Jogo em execução")
        result = conflict_resolution.apply_resolution(preview["token"])
        self.assertFalse(result["ok"])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(storage.list_operation_journals())

    def test_failed_save_restores_files_and_catalog(self):
        self.save(self.mod("a"), self.mod("b"))
        preview = self.preview()
        before_files, before_mods = self.snapshot(), storage.load_mods()
        save = storage.save_mods
        calls = 0
        def fail_once(mods):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("disco indisponível")
            return save(mods)
        with patch.object(storage, "save_mods", side_effect=fail_once):
            result = conflict_resolution.apply_resolution(preview["token"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["rolled_back"])
        self.assertEqual(storage.load_mods(), before_mods)
        self.assertEqual(self.snapshot(), before_files)
        self.assertFalse(operation_recovery.list_pending())

    def test_failure_after_first_mod_restores_every_file(self):
        self.save(self.mod("a"), self.mod("b"), self.mod("c"))
        preview = self.preview()
        before_files, before_mods = self.snapshot(), storage.load_mods()
        apply = mod_ops._apply_component_states
        calls = 0
        def fail_second(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("arquivo em uso")
            return apply(*args)
        with patch.object(mod_ops, "_apply_component_states", side_effect=fail_second):
            result = conflict_resolution.apply_resolution(preview["token"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["rolled_back"])
        self.assertEqual(storage.load_mods(), before_mods)
        self.assertEqual(self.snapshot(), before_files)

    def test_failed_rollback_stays_available_for_recovery(self):
        self.save(self.mod("a"), self.mod("b"))
        preview = self.preview()
        before = self.snapshot()
        with patch.object(storage, "save_mods", side_effect=OSError("disco indisponível")), patch.object(
            operation_recovery, "restore_files", side_effect=OSError("arquivo em uso")
        ):
            result = conflict_resolution.apply_resolution(preview["token"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["recovery_pending"])
        pending = operation_recovery.list_pending()
        self.assertEqual(len(pending), 1)
        journal = operation_recovery.Journal.load(pending[0]["id"])
        operation_recovery.rollback(journal)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(operation_recovery.list_pending())

    def test_external_mod_is_backed_up_before_disabling(self):
        a, b = self.mod("a"), self.mod("b", external=True)
        self.save(a, b)
        expected = {(pathlib.Path(storage.STORAGE_DIR) / b["storage_folder"] / e["name"]):
                    (self.game / b["folder"] / e["name"]).read_bytes() for e in b["files"]}
        result = conflict_resolution.apply_resolution(self.preview()["token"])
        self.assertTrue(result["ok"], result)
        self.assertTrue(all(path.read_bytes() == contents for path, contents in expected.items()))
        saved = next(m for m in storage.load_mods() if m["id"] == "b")
        self.assertFalse(saved["external"])

    def test_missing_private_copy_blocks_deactivation(self):
        a, b = self.mod("a"), self.mod("b")
        self.save(a, b)
        (pathlib.Path(mod_ops._storage_dir(b)) / b["files"][0]["name"]).unlink()
        result = conflict_resolution.preview_resolution("a", "ac")
        self.assertFalse(result["ok"])
        self.assertIn("Backup privado ausente", result["error"])

    def test_failed_external_operation_restores_preexisting_private_bytes(self):
        a, b = self.mod("a"), self.mod("b", external=True)
        self.save(a, b)
        private = pathlib.Path(mod_ops._storage_dir(b)) / b["files"][0]["name"]
        private.parent.mkdir(parents=True, exist_ok=True)
        private.write_bytes(b"previous private copy")
        preview = self.preview()
        before_files, before_mods = self.snapshot(), storage.load_mods()
        save = storage.save_mods
        calls = 0
        def fail_once(mods):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("falha depois do backup externo")
            return save(mods)
        with patch.object(storage, "save_mods", side_effect=fail_once):
            result = conflict_resolution.apply_resolution(preview["token"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["rolled_back"])
        self.assertEqual(private.read_bytes(), b"previous private copy")
        self.assertEqual(self.snapshot(), before_files)
        self.assertEqual(storage.load_mods(), before_mods)

    def test_activity_log_failure_does_not_undo_a_successful_resolution(self):
        self.save(self.mod("a"), self.mod("b"))
        token = self.preview()["token"]
        with patch.object(mod_ops, "_record_activity", side_effect=OSError("histórico indisponível")):
            result = conflict_resolution.apply_resolution(token)
        self.assertTrue(result["ok"])
        self.assertTrue(result["warnings"])
        self.assertFalse(next(m for m in storage.load_mods() if m["id"] == "b")["components"][0]["enabled"])
        self.assertFalse(any(name.startswith("b/") for name in self.snapshot()))

    def test_game_starting_mid_operation_keeps_recovery_pending(self):
        self.save(self.mod("a"), self.mod("b"), self.mod("c"))
        token = self.preview()["token"]
        before = self.snapshot()
        checks = 0
        def starts_during_second_mod():
            nonlocal checks
            checks += 1
            if checks >= 3:
                raise OSError("o jogo foi aberto")
        self.guard.side_effect = starts_during_second_mod
        result = conflict_resolution.apply_resolution(token)
        self.assertFalse(result["ok"])
        self.assertTrue(result["recovery_pending"])
        self.assertNotEqual(self.snapshot(), before)
        self.guard.side_effect = None
        pending = operation_recovery.list_pending()
        self.assertEqual(len(pending), 1)
        operation_recovery.rollback(operation_recovery.Journal.load(pending[0]["id"]))
        self.assertEqual(self.snapshot(), before)

    def test_missing_active_file_of_selected_mod_blocks_resolution(self):
        a, b = self.mod("a"), self.mod("b")
        self.save(a, b)
        (self.game / a["folder"] / a["files"][0]["name"]).unlink()
        result = conflict_resolution.preview_resolution("a", "ac")
        self.assertFalse(result["ok"])
        self.assertIn("escolhido", result["error"])

    def test_missing_components_in_legacy_root_files_are_still_disabled_for_manual_conflicts(self):
        a = self.mod("a")
        b = self.mod("b", "Storm", components=[("bc", {}), ("bd", {})])
        b["files"] = b["components"][0]["files"]
        a["manual_conflicts"] = ["b"]
        self.save(a, b)
        result = conflict_resolution.apply_resolution(self.preview("a", "manual-conflict")["token"])
        self.assertTrue(result["ok"], result)
        self.assertFalse(any(name.startswith("b/") for name in self.snapshot()))

    def test_physical_filename_collision_cannot_remove_the_chosen_file(self):
        a, b = self.mod("a"), self.mod("b")
        b["folder"] = a["folder"]
        b["files"] = copy.deepcopy(a["files"])
        b["components"][0]["files"] = copy.deepcopy(a["files"])
        self.save(a, b)
        before = self.snapshot()
        result = conflict_resolution.preview_resolution("a", "ac")
        self.assertFalse(result["ok"])
        self.assertIn("mesmo arquivo", result["error"])
        self.assertEqual(self.snapshot(), before)

    def test_unrelated_special_mod_does_not_block_pak_resolution(self):
        special = {"id": "background", "name": "Background", "enabled": False, "install_target": "marvel_content"}
        self.save(self.mod("a"), self.mod("b"), special)
        self.preview()

    def test_legacy_mod_without_components_can_be_selected(self):
        a, b = self.mod("a"), self.mod("b")
        a.pop("components")
        self.save(a, b)
        result = conflict_resolution.apply_resolution(self.preview("a", "whole-mod")["token"])
        self.assertTrue(result["ok"], result)
        self.assertTrue(storage.load_mods()[0]["enabled"])

    def test_expired_preview_cannot_mutate_the_library(self):
        self.save(self.mod("a"), self.mod("b"))
        preview = self.preview()
        before = self.snapshot()
        with patch.object(conflict_resolution.time, "monotonic", return_value=float("inf")):
            result = conflict_resolution.apply_resolution(preview["token"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["stale"])
        self.assertEqual(self.snapshot(), before)

    def test_same_token_cannot_apply_twice(self):
        self.save(self.mod("a"), self.mod("b"))
        token = self.preview()["token"]
        self.assertTrue(conflict_resolution.apply_resolution(token)["ok"])
        result = conflict_resolution.apply_resolution(token)
        self.assertFalse(result["ok"])
        self.assertTrue(result["stale"])


if __name__ == "__main__":
    unittest.main()
