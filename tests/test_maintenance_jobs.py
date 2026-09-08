import copy
import hashlib
import pathlib
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import main
from backend import library_maintenance, mod_ops, operation_jobs, storage


class MaintenanceJobsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        patches = patch.multiple(storage, MODS_JSON=str(self.root / "mods.json"), SETTINGS_FILE=str(self.root / "settings.json"),
                                 STORAGE_DIR=str(self.root / "library"), BACKUPS_DIR=str(self.root / "backups"))
        patches.start()
        self.addCleanup(patches.stop)
        jobs = patch.object(operation_jobs, "_jobs", {})
        jobs.start()
        self.addCleanup(jobs.stop)
        storage.ensure_dirs()
        settings = storage.load_settings()
        settings["mods_path"] = str(self.root / "game")
        storage.save_settings(settings)
        self.assets = [f"Marvel/Content/Meshes/SK_Shared{index}.uasset" for index in range(3)]
        assets = patch.object(mod_ops, "_paths_from_bundle", return_value=self.assets)
        self.assets_tool = assets.start()
        self.addCleanup(assets.stop)
        self.api = main.Api()
        self.mods = [self.make_mod("first"), self.make_mod("second")]
        storage.save_mods(self.mods)

    def make_mod(self, identifier, character="Hela", skin="Default", physics=False):
        data = (identifier.encode() + b"-package-") * 250000
        relative = identifier + ".pak"
        private = pathlib.Path(storage.STORAGE_DIR) / identifier / relative
        active = self.root / "game" / identifier / relative
        for destination in (private, active):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        entry = {"name": relative, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        types = ["Mesh", "Physics"] if physics else ["Mesh"]
        return {"id": identifier, "name": identifier, "storage_folder": identifier, "folder": identifier,
                "character": character, "skin": skin, "priority": 1, "enabled": True,
                "type": types[0], "types": types, "files": [entry], "images": [],
                "components": [{"id": identifier + "c", "name": identifier + (" Physics" if physics else ""),
                                "enabled": True, "type": types[0], "types": types, "files": [entry]}]}

    def wait(self, job_id):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            result = self.api.get_operation_status(job_id)
            if result.get("state") in {"completed", "failed", "cancelled"}:
                return result
            time.sleep(0.01)
        self.fail("maintenance worker did not finish")

    def pause_at(self, target, minimum=0):
        reached, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = operation_jobs.OperationJob.progress
        def progress(job, stage, message, current=0, total=0, unit="items"):
            original(job, stage, message, current, total, unit)
            if stage == target and current >= minimum and not reached.is_set():
                reached.set()
                release.wait(5)
        return progress, reached, release

    def catalog_bytes(self):
        return pathlib.Path(storage.MODS_JSON).read_bytes(), pathlib.Path(storage.SETTINGS_FILE).read_bytes()

    def files_bytes(self):
        return {str(path.relative_to(self.root)): path.read_bytes() for directory in (self.root / "game", self.root / "library")
                for path in directory.rglob("*") if path.is_file()}

    def test_hash_cancellation_returns_no_partial_report_and_changes_no_data(self):
        before_catalog, before_files = self.catalog_bytes(), self.files_bytes()
        progress, reached, release = self.pause_at("hash", minimum=1)
        with patch.object(operation_jobs.OperationJob, "progress", new=progress):
            started = self.api.start_library_health(True, "cancel-health-hash")
            self.assertTrue(reached.wait(3))
            status = self.api.find_operation("cancel-health-hash")
            self.assertEqual(status["context"], {"kind": "health"})
            self.assertEqual(status["unit"], "bytes")
            self.assertGreater(status["current"], 0)
            self.assertTrue(self.api.cancel_operation(started["job_id"])["ok"])
            release.set()
            result = self.wait(started["job_id"])
        self.assertEqual(result["state"], "cancelled")
        self.assertTrue(result["result"]["cancelled"])
        self.assertNotIn("issues", result["result"])
        self.assertNotIn("hashed_files", result["result"])
        self.assertEqual(self.catalog_bytes(), before_catalog)
        self.assertEqual(self.files_bytes(), before_files)

    def test_fast_health_cancellation_is_available_between_mods_without_hashing(self):
        before = self.catalog_bytes()
        progress, reached, release = self.pause_at("checking", minimum=1)
        with patch.object(operation_jobs.OperationJob, "progress", new=progress), patch.object(
                library_maintenance, "_hash_file", side_effect=AssertionError("fast check must not hash")):
            started = self.api.start_library_health(False, "cancel-fast-health")
            self.assertTrue(reached.wait(3))
            self.assertTrue(self.api.cancel_operation(started["job_id"])["ok"])
            release.set()
            result = self.wait(started["job_id"])
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(self.catalog_bytes(), before)

    def test_orphan_scan_can_be_cancelled_without_cleaning_anything(self):
        orphan = pathlib.Path(storage.STORAGE_DIR) / "Saved package [unregistered]" / "Preserved.zip"
        orphan.parent.mkdir()
        orphan.write_bytes(b"user preserved archive")
        progress, reached, release = self.pause_at("orphans")
        before = self.files_bytes()
        with patch.object(operation_jobs.OperationJob, "progress", new=progress):
            started = self.api.start_library_health(False, "cancel-orphans")
            self.assertTrue(reached.wait(3))
            self.assertTrue(self.api.cancel_operation(started["job_id"])["ok"])
            release.set()
            result = self.wait(started["job_id"])
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(self.files_bytes(), before)

    def test_finished_health_result_is_findable_and_read_only(self):
        before = self.catalog_bytes()
        started = self.api.start_library_health(True, "finished-health")
        status = self.wait(started["job_id"])
        self.assertEqual(status["state"], "completed")
        found = self.api.find_operation("finished-health")
        self.assertTrue(found["result"]["hashes_checked"])
        self.assertEqual(found["result"]["checked"], 2)
        self.assertEqual(found["result"]["issues"], [])
        self.assertGreaterEqual(found["result"]["hashed_files"], 2)
        self.assertEqual(self.catalog_bytes(), before)

    def test_conflict_analysis_cancel_does_not_save_partly_populated_cache(self):
        before = self.catalog_bytes()
        progress, reached, release = self.pause_at("analyzing", minimum=1)
        with patch.object(operation_jobs.OperationJob, "progress", new=progress), patch.object(storage, "save_mods", wraps=storage.save_mods) as save:
            started = self.api.start_conflict_check("cancel-conflict-analysis")
            self.assertTrue(reached.wait(3))
            self.assertGreater(self.assets_tool.call_count, 0)
            self.assertTrue(self.api.cancel_operation(started["job_id"])["ok"])
            release.set()
            result = self.wait(started["job_id"])
            save.assert_not_called()
        self.assertEqual(result["state"], "cancelled")
        self.assertNotIn("conflicts", result["result"])
        self.assertEqual(self.catalog_bytes(), before)

    def test_conflict_comparison_cancel_does_not_return_partial_conflicts_or_cache(self):
        before = self.catalog_bytes()
        progress, reached, release = self.pause_at("comparing", minimum=1)
        with patch.object(operation_jobs.OperationJob, "progress", new=progress), patch.object(storage, "save_mods", wraps=storage.save_mods) as save:
            started = self.api.start_conflict_check("cancel-conflict-comparison")
            self.assertTrue(reached.wait(3))
            self.assertEqual(self.assets_tool.call_count, 2)
            self.assertTrue(self.api.cancel_operation(started["job_id"])["ok"])
            release.set()
            result = self.wait(started["job_id"])
            save.assert_not_called()
        self.assertEqual(result["state"], "cancelled")
        self.assertNotIn("conflicts", result["result"])
        self.assertNotIn("unreadable", result["result"])
        self.assertEqual(self.catalog_bytes(), before)

    def test_cache_commit_is_not_cancelled_and_completed_cache_is_reused(self):
        reached, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = storage.save_mods
        def save(mods):
            reached.set()
            release.wait(5)
            return original(mods)
        with patch.object(storage, "save_mods", side_effect=save):
            started = self.api.start_conflict_check("save-conflict-cache")
            self.assertTrue(reached.wait(3))
            status = self.api.get_operation_status(started["job_id"])
            self.assertFalse(status["can_cancel"])
            self.assertFalse(self.api.cancel_operation(started["job_id"])["ok"])
            release.set()
            result = self.wait(started["job_id"])
        self.assertEqual(result["state"], "completed")
        self.assertEqual(len(result["result"]["conflicts"]), 3)
        self.assertTrue(all(mod.get("asset_path_cache") for mod in storage.load_mods()))
        self.assets_tool.reset_mock()
        again = self.wait(self.api.start_conflict_check("reuse-complete-cache")["job_id"])
        self.assertEqual(again["state"], "completed")
        self.assertEqual(len(again["result"]["conflicts"]), 3)
        self.assets_tool.assert_not_called()

    def test_background_conflict_job_keeps_old_identity_and_physics_policy(self):
        other_identity = self.make_mod("storm", character="Storm")
        other_skin = self.make_mod("other_skin", skin="Other")
        physics = self.make_mod("support", physics=True)
        storage.save_mods([*self.mods, other_identity, other_skin, physics])
        result = self.wait(self.api.start_conflict_check("legacy-policy")["job_id"])
        self.assertEqual(result["state"], "completed")
        report = result["result"]
        self.assertEqual(report["ignored_physics_components"], 1)
        for conflict in report["conflicts"]:
            self.assertEqual({owner["mod_id"] for owner in conflict["owners"]}, {"first", "second"})
        self.assertEqual(len(report["conflicts"]), 3)
        self.assertEqual(self.assets_tool.call_count, 4)

    def test_async_same_mod_mesh_accompaniment_is_not_promoted_by_relations(self):
        record = copy.deepcopy(self.mods[0])
        extra = self.mods[1]["components"][0]
        # Fonte extra pertence ao mesmo diretório privado do primeiro mod.
        source = pathlib.Path(storage.STORAGE_DIR) / "second" / "second.pak"
        destination = pathlib.Path(storage.STORAGE_DIR) / "first" / "second.pak"
        destination.write_bytes(source.read_bytes())
        extra = {**extra, "requires": [record["components"][0]["id"]], "exclusive_group": "appearance"}
        record["components"].append(extra)
        record["files"].extend(extra["files"])
        storage.save_mods([record])
        result = self.wait(self.api.start_conflict_check("legacy-accompaniment")["job_id"])
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["result"]["conflicts"], [])
        self.assertEqual(result["result"]["checked_components"], 2)

    def test_async_manual_conflict_still_crosses_different_identities(self):
        self.mods[1]["character"] = "Storm"
        self.mods[0]["manual_conflicts"] = [self.mods[1]["id"]]
        storage.save_mods(self.mods)
        result = self.wait(self.api.start_conflict_check("legacy-manual")["job_id"])
        self.assertEqual(result["state"], "completed")
        self.assertEqual(len(result["result"]["conflicts"]), 1)
        self.assertEqual(result["result"]["conflicts"][0]["kind"], "manual")


if __name__ == "__main__":
    unittest.main()
