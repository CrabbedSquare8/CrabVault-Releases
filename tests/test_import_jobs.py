import pathlib
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from unittest.mock import Mock, patch

import main
from backend import mod_ops, operation_jobs, operation_recovery, storage


class ImportJobsTests(unittest.TestCase):
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
        main.pending_imports.clear()
        self.addCleanup(main.pending_imports.clear)
        self.archive = self.root / "Hero.zip"
        with zipfile.ZipFile(self.archive, "w") as stream:
            stream.writestr("normal/Hero.pak", b"pak bytes" * 100)
            stream.writestr("normal/Hero.utoc", b"utoc bytes" * 100)
            stream.writestr("normal/Hero.ucas", b"ucas bytes" * 100)
        window = Mock()
        window.create_file_dialog.return_value = [str(self.archive)]
        window_patch = patch.object(main, "window", window)
        window_patch.start()
        self.addCleanup(window_patch.stop)
        self.api = main.Api()

    def wait(self, job_id):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = self.api.get_operation_status(job_id)
            if status.get("state") in {"completed", "cancelled", "failed"}:
                return status
            time.sleep(0.01)
        self.fail("operation did not finish")

    def prepare(self):
        started = self.api.start_mod_import()
        self.assertTrue(started["ok"])
        status = self.wait(started["job_id"])
        self.assertEqual(status["state"], "completed", status)
        return status["result"]

    def blocking_progress(self, stage):
        reached, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = operation_jobs.OperationJob.progress
        def progress(job, current_stage, message, current=0, total=0, unit="items"):
            original(job, current_stage, message, current, total, unit)
            if current_stage == stage and current > 0 and not reached.is_set():
                reached.set()
                release.wait(5)
        return progress, reached, release

    def test_preparation_returns_metadata_without_import_preview_and_cancel_keeps_archive(self):
        result = self.prepare()
        self.assertEqual(result["file_count"], 3)
        self.assertNotIn("preview", result)
        self.assertTrue(result["token"] in main.pending_imports)
        self.assertEqual(self.api.get_operation_recoveries()["operations"], [])
        self.assertTrue(self.api.cancel_mod_install(result["token"])["ok"])
        self.assertTrue(self.archive.exists())
        self.assertEqual(storage.load_mods(), [])
        journal = storage.list_operation_journals()[0]
        self.assertEqual(journal["phase"], "cancelled")
        self.assertFalse((pathlib.Path(storage.operation_dir(journal["id"])) / "extracted").exists())

    def test_detail_action_appends_archive_as_disabled_component_in_one_job(self):
        original_dir = self.root / "original"
        original_dir.mkdir()
        originals = []
        for extension in (".pak", ".utoc", ".ucas"):
            path = original_dir / ("Original" + extension)
            path.write_bytes(("original" + extension).encode())
            originals.append(str(path))
        mod = mod_ops.add_mod(originals, {"name": "Hero", "character": "Hela", "skin": "Default"})
        started = self.api.start_add_mod_components(mod["id"], "component-append:test")
        self.assertTrue(started["ok"])
        status = self.wait(started["job_id"])
        self.assertEqual(status["state"], "completed", status)
        result = status["result"]
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["record"]["added_components"], 1)
        saved = storage.load_mods()[0]
        self.assertEqual(len(saved["components"]), 2)
        self.assertFalse(saved["components"][-1]["enabled"])
        self.assertFalse(self.archive.exists(), "a origem só é removida após o anexo concluir")
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_cancel_during_extraction_cleans_partial_data_and_never_removes_source(self):
        progress, reached, release = self.blocking_progress("extracting")
        with patch.object(operation_jobs.OperationJob, "progress", new=progress):
            started = self.api.start_mod_import()
            self.assertTrue(reached.wait(5))
            status = self.api.get_operation_status(started["job_id"])
            self.assertTrue(status["can_cancel"])
            self.assertEqual(status["unit"], "bytes")
            self.assertTrue(self.api.cancel_operation(started["job_id"])["ok"])
            release.set()
            result = self.wait(started["job_id"])
        self.assertEqual(result["state"], "cancelled", result)
        self.assertTrue(self.archive.exists())
        self.assertFalse(main.pending_imports)
        self.assertEqual(storage.load_mods(), [])
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_cancel_during_copy_does_not_install_or_delete_original_archive(self):
        prepared = self.prepare()
        progress, reached, release = self.blocking_progress("copying")
        with patch.object(operation_jobs.OperationJob, "progress", new=progress):
            started = self.api.start_complete_mod_install(prepared["token"], {"name": "Hero", "character": "Hela"})
            self.assertTrue(reached.wait(5))
            self.assertTrue(self.api.cancel_operation(started["job_id"])["ok"])
            release.set()
            result = self.wait(started["job_id"])
        self.assertEqual(result["state"], "cancelled", result)
        self.assertTrue(self.archive.exists())
        self.assertEqual(storage.load_mods(), [])
        self.assertFalse(list((self.root / "game").rglob("*.pak")))
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_commit_cannot_be_interrupted_and_source_is_removed_only_after_success(self):
        prepared = self.prepare()
        reached, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original_save = storage.save_mods
        def save(mods):
            reached.set()
            release.wait(5)
            return original_save(mods)
        with patch.object(storage, "save_mods", side_effect=save):
            started = self.api.start_complete_mod_install(prepared["token"], {"name": "Hero", "character": "Hela"})
            self.assertTrue(reached.wait(5))
            self.assertTrue(self.archive.exists())
            status = self.api.get_operation_status(started["job_id"])
            self.assertFalse(status["can_cancel"])
            self.assertEqual(status["stage"], "committing")
            self.assertFalse(self.api.cancel_operation(started["job_id"])["ok"])
            release.set()
            result = self.wait(started["job_id"])
        self.assertEqual(result["state"], "completed", result)
        self.assertTrue(result["result"]["ok"])
        self.assertFalse(self.archive.exists())
        record = storage.load_mods()[0]
        private_archive = pathlib.Path(mod_ops._storage_dir(record)) / record["archives"][0]
        self.assertTrue(private_archive.exists())
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_setting_keeps_original_archive_and_image_after_success(self):
        settings = storage.load_settings()
        settings["delete_import_sources_after_success"] = False
        storage.save_settings(settings)
        prepared = self.prepare()
        cover = self.root / "cover.png"
        cover.write_bytes(b"image bytes")
        main.window.create_file_dialog.return_value = [str(cover)]
        selected = self.api.choose_install_image(prepared["token"])
        self.assertTrue(selected["ok"])
        result = self.wait(self.api.start_complete_mod_install(
            prepared["token"], {"name": "Hero", "character": "Hela"})["job_id"])
        self.assertEqual(result["state"], "completed", result)
        self.assertTrue(self.archive.exists())
        self.assertTrue(cover.exists())
        self.assertEqual(result["result"]["source_cleanup"]["removed"], [])
        self.assertCountEqual(result["result"]["source_cleanup"]["preserved"], [str(self.archive), str(cover)])
        record = storage.load_mods()[0]
        self.assertEqual(len(record["archives"]), 1)
        self.assertTrue((pathlib.Path(mod_ops._storage_dir(record)) / record["archives"][0]).is_file())

    def test_setting_skips_private_archive_backup_but_keeps_installed_payload(self):
        settings = storage.load_settings()
        settings["preserve_import_archives"] = False
        storage.save_settings(settings)
        prepared = self.prepare()
        result = self.wait(self.api.start_complete_mod_install(
            prepared["token"], {"name": "Hero", "character": "Hela"})["job_id"])
        self.assertEqual(result["state"], "completed", result)
        self.assertFalse(self.archive.exists())
        record = storage.load_mods()[0]
        self.assertEqual(record["archives"], [])
        self.assertEqual(record["components"][0]["source_archive"], "Hero.zip")
        private = pathlib.Path(mod_ops._storage_dir(record))
        self.assertTrue(all((private / entry["name"]).is_file() for entry in record["files"]))

    def test_loose_package_sources_follow_delete_setting(self):
        sources = []
        for extension in (".pak", ".utoc", ".ucas"):
            path = self.root / ("Loose" + extension)
            path.write_bytes(("loose" + extension).encode())
            sources.append(path)
        main.window.create_file_dialog.return_value = [str(path) for path in sources]
        prepared = self.prepare()
        result = self.wait(self.api.start_complete_mod_install(
            prepared["token"], {"name": "Loose", "character": "Hela"})["job_id"])
        self.assertEqual(result["state"], "completed", result)
        self.assertTrue(all(not path.exists() for path in sources))
        record = storage.load_mods()[0]
        private = pathlib.Path(mod_ops._storage_dir(record))
        self.assertTrue(all((private / entry["name"]).is_file() for entry in record["files"]))
        self.assertEqual(len(record["archives"]), 1)
        private_archive = private / record["archives"][0]
        self.assertTrue(private_archive.is_file())
        with zipfile.ZipFile(private_archive) as archive:
            self.assertCountEqual(archive.namelist(), ["Loose.pak", "Loose.utoc", "Loose.ucas"])

    def test_loose_packages_skip_zip_when_archive_backup_is_disabled(self):
        settings = storage.load_settings()
        settings["preserve_import_archives"] = False
        storage.save_settings(settings)
        sources = []
        for extension in (".pak", ".utoc", ".ucas"):
            path = self.root / ("LooseNoArchive" + extension)
            path.write_bytes(("loose" + extension).encode())
            sources.append(path)
        main.window.create_file_dialog.return_value = [str(path) for path in sources]
        prepared = self.prepare()
        result = self.wait(self.api.start_complete_mod_install(
            prepared["token"], {"name": "Loose", "character": "Hela"})["job_id"])
        self.assertEqual(result["state"], "completed", result)
        self.assertEqual(storage.load_mods()[0]["archives"], [])

    def test_cancel_stops_only_the_subprocess_owned_by_the_job(self):
        process_started = threading.Event()
        process_holder = []
        def run(job):
            # Registrar o processo real pelo polling evita depender da rapidez
            # de inicialização do Python no Windows.
            return job.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=40)
        started = operation_jobs.start("Ferramenta de teste", run)
        self.addCleanup(operation_jobs.cancel, started["job_id"])
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = operation_jobs._jobs[started["job_id"]]
            if job._process is not None:
                process_holder.append(job._process)
                process_started.set()
                break
            time.sleep(0.01)
        self.assertTrue(process_started.is_set())
        self.assertTrue(self.api.cancel_operation(started["job_id"])["ok"])
        result = self.wait(started["job_id"])
        self.assertEqual(result["state"], "cancelled", result)
        self.assertIsNotNone(process_holder[0].poll())

    def test_waiting_for_another_file_operation_can_be_cancelled(self):
        prepared = self.prepare()
        mod_ops._FILE_OPERATION_LOCK.acquire()
        try:
            started = self.api.start_complete_mod_install(prepared["token"], {"name": "Hero", "character": "Hela"})
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if self.api.get_operation_status(started["job_id"]).get("stage") == "waiting":
                    break
                time.sleep(0.01)
            self.assertTrue(self.api.cancel_operation(started["job_id"])["ok"])
            result = self.wait(started["job_id"])
            self.assertEqual(result["state"], "cancelled", result)
        finally:
            mod_ops._FILE_OPERATION_LOCK.release()
        self.assertTrue(self.archive.exists())
        self.assertEqual(storage.load_mods(), [])

    def test_source_modified_after_selection_is_rejected_without_deleting_it(self):
        prepared = self.prepare()
        with self.archive.open("ab") as stream:
            stream.write(b"new download data")
        with patch.object(main.traceback, "print_exc"):
            result = self.wait(self.api.start_complete_mod_install(
                prepared["token"], {"name": "Hero", "character": "Hela"})["job_id"])
        self.assertEqual(result["state"], "failed", result)
        self.assertTrue(self.archive.exists())
        self.assertIn("mudou", result["result"]["error"])
        self.assertEqual(storage.load_mods(), [])
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_source_already_in_private_storage_is_not_removed(self):
        source = pathlib.Path(storage.STORAGE_DIR) / "old-library-archive.zip"
        source.write_bytes(b"saved library archive")
        removed, errors = main._remove_import_sources([str(source)], expected=main._source_snapshots([str(source)]))
        self.assertEqual(removed, [])
        self.assertEqual(errors, [])
        self.assertEqual(source.read_bytes(), b"saved library archive")

    def test_install_failure_restores_files_and_keeps_original_archive(self):
        prepared = self.prepare()
        with patch.object(mod_ops, "_install_file_fast", side_effect=OSError("simulated disk failure")), patch.object(
                main.traceback, "print_exc"):
            result = self.wait(self.api.start_complete_mod_install(
                prepared["token"], {"name": "Hero", "character": "Hela"})["job_id"])
        self.assertEqual(result["state"], "failed", result)
        self.assertTrue(self.archive.exists())
        self.assertEqual(storage.load_mods(), [])
        self.assertFalse(list((self.root / "game").rglob("*.pak")))
        self.assertFalse(list(pathlib.Path(storage.STORAGE_DIR).rglob("*.pak")))
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_duplicate_confirmation_reuses_job_and_keeps_first_request_metadata(self):
        prepared = self.prepare()
        progress, reached, release = self.blocking_progress("copying")
        with patch.object(operation_jobs.OperationJob, "progress", new=progress):
            started = self.api.start_complete_mod_install(prepared["token"], {"name": "Hero", "character": "Hela"})
            self.assertTrue(reached.wait(5))
            duplicate = self.api.start_complete_mod_install(prepared["token"], {"name": "Duplicate", "character": "Hela"})
            self.assertTrue(duplicate["ok"])
            self.assertTrue(duplicate["reused"])
            self.assertEqual(duplicate["job_id"], started["job_id"])
            found = self.api.find_operation("install:" + prepared["token"])
            self.assertTrue(found["found"])
            self.assertEqual(found["job_id"], started["job_id"])
            release.set()
            result = self.wait(started["job_id"])
        self.assertEqual(result["state"], "completed", result)
        self.assertEqual(len(storage.load_mods()), 1)
        self.assertEqual(storage.load_mods()[0]["name"], "Hero")
        retried = self.api.start_complete_mod_install(prepared["token"], {"name": "Still duplicate"})
        self.assertEqual(retried["job_id"], started["job_id"])
        self.assertEqual(self.api.find_operation("install:" + prepared["token"])["result"]["record"]["name"], "Hero")

    def test_cancel_before_worker_enters_install_discards_the_claimed_selection(self):
        prepared = self.prepare()
        reached, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original_check = operation_jobs.OperationJob.check
        def wait_before_work(job):
            if not reached.is_set():
                reached.set()
                release.wait(5)
            return original_check(job)
        with patch.object(operation_jobs.OperationJob, "check", new=wait_before_work):
            started = self.api.start_complete_mod_install(prepared["token"], {"name": "Hero", "character": "Hela"})
            self.assertTrue(reached.wait(5))
            self.assertNotIn(prepared["token"], main.pending_imports)
            self.assertTrue(self.api.cancel_operation(started["job_id"])["ok"])
            release.set()
            result = self.wait(started["job_id"])
        self.assertEqual(result["state"], "cancelled", result)
        self.assertTrue(self.archive.exists())
        self.assertEqual(storage.load_mods(), [])
        self.assertEqual(operation_recovery.list_pending(), [])
        journal = storage.list_operation_journals()[0]
        self.assertEqual(journal["phase"], "cancelled")
        self.assertFalse((pathlib.Path(storage.operation_dir(journal["id"])) / "extracted").exists())

    def test_unavailable_operation_ids_are_reported(self):
        self.assertFalse(self.api.get_operation_status("missing")["ok"])
        self.assertFalse(self.api.cancel_operation("missing")["ok"])
        self.assertFalse(self.api.start_complete_mod_install("missing", {})["ok"])

    def test_worker_start_failure_discards_claimed_selection_without_touching_source(self):
        prepared = self.prepare()
        previous_jobs = set(operation_jobs._jobs)
        with patch.object(operation_jobs.threading.Thread, "start", side_effect=RuntimeError("cannot start thread")):
            result = self.api.start_complete_mod_install(prepared["token"], {"name": "Hero", "character": "Hela"})
        self.assertFalse(result["ok"], result)
        self.assertIn("job_id", result)
        self.assertEqual(set(operation_jobs._jobs) - previous_jobs, {result["job_id"]})
        found = self.api.find_operation("install:" + prepared["token"])
        self.assertTrue(found["found"])
        self.assertEqual(found["job_id"], result["job_id"])
        self.assertEqual(found["state"], "failed")
        self.assertFalse(found["can_cancel"])
        retried = self.api.start_complete_mod_install(prepared["token"], {"name": "Retry"})
        self.assertTrue(retried["reused"])
        self.assertEqual(retried["job_id"], result["job_id"])
        self.assertNotIn(prepared["token"], main.pending_imports)
        self.assertTrue(self.archive.exists())
        self.assertEqual(storage.load_mods(), [])
        self.assertEqual(operation_recovery.list_pending(), [])
        journal = storage.list_operation_journals()[0]
        self.assertEqual(journal["phase"], "cancelled")
        self.assertFalse(operation_recovery.is_live(journal["id"]))
        self.assertFalse((pathlib.Path(storage.operation_dir(journal["id"])) / "extracted").exists())


if __name__ == "__main__":
    unittest.main()
