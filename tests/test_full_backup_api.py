"""Integração dos diálogos e jobs de backup, somente com uma biblioteca temporária."""
import hashlib
import json
import pathlib
import threading
import time
import unittest
import uuid
from unittest.mock import Mock, patch

import main
from backend import operation_jobs, storage
from tests import test_full_backup as backup_cases


class FullBackupApiTests(unittest.TestCase):
    def setUp(self):
        backup_cases.FullBackupTests.setUp(self)
        self.api = main.Api()
        self.source_zip = None
        self.jobs = []
        self.window = Mock()
        self.window.create_file_dialog.side_effect = self.dialog
        window_patch = patch.object(main, "window", self.window)
        window_patch.start()
        self.addCleanup(window_patch.stop)
        self.addCleanup(self.cleanup_jobs)
        active = self.game / self.mod["folder"] / self.mod["files"][0]["name"]
        active.parent.mkdir(parents=True)
        active.write_bytes(b"active original untouched")
        self.before = self.current_snapshot()

    def current_snapshot(self):
        files = [pathlib.Path(storage.MODS_JSON), pathlib.Path(storage.SETTINGS_FILE)]
        files.extend(path for root in (pathlib.Path(storage.STORAGE_DIR), self.game)
                     for path in root.rglob("*") if path.is_file())
        return {str(path): path.read_bytes() for path in files}

    def dialog(self, kind, **options):
        if kind == main.webview.FileDialog.FOLDER:
            return [str(self.destination)]
        if kind == main.webview.FileDialog.OPEN:
            self.assertIsNotNone(self.source_zip)
            self.assertIn("*.zip", options["file_types"][0])
            return [str(self.source_zip)]
        self.fail(f"Unexpected dialog: {kind}")

    def request(self):
        return "backup-api:" + uuid.uuid4().hex

    def started(self, result):
        self.assertTrue(result["ok"], result)
        self.jobs.append(result["job_id"])
        return result

    def wait(self, started):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status = self.api.get_operation_status(started["job_id"])
            self.assertTrue(status["ok"], status)
            if status.get("state") in {"completed", "cancelled", "failed"}:
                return status
            time.sleep(0.01)
        self.fail("O job de backup não terminou.")

    def successful(self, started):
        result = self.wait(self.started(started))
        self.assertEqual(result["state"], "completed", result)
        self.assertTrue(result["result"]["ok"], result)
        return result["result"]

    def cleanup_jobs(self):
        for job_id in dict.fromkeys(self.jobs):
            self.api.cancel_operation(job_id)
            with operation_jobs._lock:
                job = operation_jobs._jobs.get(job_id)
            if job and job.snapshot()["state"] not in {"completed", "cancelled", "failed"}:
                self.wait({"job_id": job_id})
            with operation_jobs._lock:
                operation_jobs._jobs.pop(job_id, None)

    def prepare_export(self):
        return self.successful(self.api.start_full_backup_preview(request_id=self.request()))

    def export(self):
        preview = self.prepare_export()
        result = self.successful(self.api.start_full_backup(preview["token"]))
        self.source_zip = pathlib.Path(result["path"])
        return preview, result

    def pause_at_stage(self, stage):
        reached, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = operation_jobs.OperationJob.progress

        def progress(job, current_stage, message, current=0, total=0, unit="items"):
            original(job, current_stage, message, current, total, unit)
            if current_stage == stage and current > 0 and not reached.is_set():
                reached.set()
                release.wait(5)

        return patch.object(operation_jobs.OperationJob, "progress", new=progress), reached, release

    def test_real_api_roundtrip_is_idempotent_and_preserves_current_library_and_game(self):
        preview = self.prepare_export()
        self.assertTrue(preview["can_create"])
        self.assertGreater(preview["required_bytes"], preview["total_bytes"])
        self.assertEqual(list(self.destination.iterdir()), [])
        paused, reached, release = self.pause_at_stage("backup")
        with paused:
            started = self.started(self.api.start_full_backup(preview["token"]))
            self.assertTrue(reached.wait(5))
            duplicate = self.api.start_full_backup(preview["token"])
            self.assertEqual(duplicate["job_id"], started["job_id"])
            self.assertTrue(duplicate["reused"])
            self.assertEqual(self.api.find_operation("backup:" + preview["token"])["job_id"], started["job_id"])
            release.set()
            status = self.wait(started)
        self.assertEqual(status["state"], "completed", status)
        self.source_zip = pathlib.Path(status["result"]["path"])
        self.assertEqual(list(self.destination.iterdir()), [self.source_zip])
        duplicate = self.api.start_full_backup(preview["token"])
        self.assertEqual(duplicate["job_id"], started["job_id"])
        self.assertEqual(self.wait(duplicate)["result"]["path"], str(self.source_zip))

        restore_preview = self.successful(self.api.start_full_restore_preview(request_id=self.request()))
        self.assertTrue(restore_preview["can_restore"])
        self.assertFalse(pathlib.Path(restore_preview["destination"]).exists())
        paused, reached, release = self.pause_at_stage("restore_backup")
        with paused:
            started = self.started(self.api.start_full_restore(restore_preview["token"]))
            self.assertTrue(reached.wait(5))
            duplicate = self.api.start_full_restore(restore_preview["token"])
            self.assertEqual(duplicate["job_id"], started["job_id"])
            self.assertTrue(duplicate["reused"])
            release.set()
            restored_status = self.wait(started)
        self.assertEqual(restored_status["state"], "completed", restored_status)
        restored = pathlib.Path(restored_status["result"]["path"])
        self.assertEqual(set(self.destination.iterdir()), {self.source_zip, restored})
        duplicate = self.api.start_full_restore(restore_preview["token"])
        self.assertEqual(duplicate["job_id"], started["job_id"])
        self.assertEqual(self.wait(duplicate)["result"]["path"], str(restored))
        self.assertFalse(json.loads((restored / "mods.json").read_text(encoding="utf-8"))[0]["enabled"])
        self.assertEqual(json.loads((restored / "settings.json").read_text(encoding="utf-8"))["mods_path"], "")
        manifest = json.loads((restored / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            self.assertEqual(hashlib.sha256((restored / entry["name"]).read_bytes()).hexdigest(), entry["sha256"])
        self.assertEqual(self.current_snapshot(), self.before)
        self.assertEqual([call.args[0] for call in self.window.create_file_dialog.call_args_list],
                         [main.webview.FileDialog.FOLDER, main.webview.FileDialog.OPEN, main.webview.FileDialog.FOLDER])

    def test_cancel_export_folder_picker_does_not_create_backup(self):
        self.window.create_file_dialog.return_value = None
        self.window.create_file_dialog.side_effect = None
        result = self.wait(self.started(self.api.start_full_backup_preview(request_id=self.request())))
        self.assertEqual(result["state"], "cancelled", result)
        self.assertEqual(list(self.destination.iterdir()), [])
        self.assertEqual(self.current_snapshot(), self.before)

    def test_cancel_restore_open_picker_does_not_open_destination_picker(self):
        self.window.create_file_dialog.side_effect = None
        self.window.create_file_dialog.return_value = None
        result = self.wait(self.started(self.api.start_full_restore_preview(request_id=self.request())))
        self.assertEqual(result["state"], "cancelled", result)
        self.window.create_file_dialog.assert_called_once()
        self.assertEqual(self.window.create_file_dialog.call_args.args[0], main.webview.FileDialog.OPEN)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_cancel_restore_destination_picker_preserves_archive_and_library(self):
        self.export()
        self.window.create_file_dialog.reset_mock()

        def dialog(kind, **options):
            return [str(self.source_zip)] if kind == main.webview.FileDialog.OPEN else None

        self.window.create_file_dialog.side_effect = dialog
        result = self.wait(self.started(self.api.start_full_restore_preview(request_id=self.request())))
        self.assertEqual(result["state"], "cancelled", result)
        self.assertEqual(self.window.create_file_dialog.call_count, 2)
        self.assertEqual(list(self.destination.iterdir()), [self.source_zip])
        self.assertEqual(self.current_snapshot(), self.before)

    def test_same_preview_request_does_not_open_duplicate_native_dialog(self):
        reached, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def dialog(kind, **options):
            reached.set()
            release.wait(5)
            return self.dialog(kind, **options)

        self.window.create_file_dialog.side_effect = dialog
        request_id = self.request()
        started = self.started(self.api.start_full_backup_preview(request_id=request_id))
        try:
            self.assertTrue(reached.wait(5))
            duplicate = self.api.start_full_backup_preview(request_id=request_id)
            self.assertEqual(duplicate["job_id"], started["job_id"])
            self.assertTrue(duplicate["reused"])
        finally:
            release.set()
        self.assertEqual(self.wait(started)["state"], "completed")
        self.window.create_file_dialog.assert_called_once()
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_job_cancellation_during_backup_cleans_partial_without_touching_sources(self):
        preview = self.prepare_export()
        paused, reached, release = self.pause_at_stage("backup")
        with paused:
            started = self.started(self.api.start_full_backup(preview["token"]))
            self.assertTrue(reached.wait(5))
            self.assertTrue(self.api.cancel_operation(started["job_id"])["ok"])
            release.set()
            result = self.wait(started)
        self.assertEqual(result["state"], "cancelled", result)
        self.assertEqual(list(self.destination.iterdir()), [])
        self.assertEqual(self.current_snapshot(), self.before)

    def test_job_cancellation_during_restore_cleans_owned_directory(self):
        self.export()
        preview = self.successful(self.api.start_full_restore_preview(request_id=self.request()))
        paused, reached, release = self.pause_at_stage("restore_backup")
        with paused:
            started = self.started(self.api.start_full_restore(preview["token"]))
            self.assertTrue(reached.wait(5))
            self.assertTrue(self.api.cancel_operation(started["job_id"])["ok"])
            release.set()
            result = self.wait(started)
        self.assertEqual(result["state"], "cancelled", result)
        self.assertEqual(list(self.destination.iterdir()), [self.source_zip])
        self.assertEqual(self.current_snapshot(), self.before)

    def test_missing_files_require_explicit_incomplete_choice_through_api(self):
        (pathlib.Path(storage.STORAGE_DIR) / "Hela/example/image.png").unlink()
        preview = self.prepare_export()
        self.assertFalse(preview["complete"])
        failed = self.wait(self.started(self.api.start_full_backup(preview["token"])))
        self.assertEqual(failed["state"], "failed", failed)
        self.assertEqual(list(self.destination.iterdir()), [])
        preview = self.prepare_export()
        result = self.successful(self.api.start_full_backup(preview["token"], allow_incomplete=True))
        self.assertFalse(result["complete"])
        self.assertTrue(result["warnings"])
        self.assertTrue(pathlib.Path(result["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
