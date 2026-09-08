import pathlib
import tempfile
import threading
import time
import unittest
import zipfile
from unittest.mock import Mock, patch

import main
from backend import mod_ops, operation_jobs, operation_recovery, storage


class OperationTrackingTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(operation_jobs, "_jobs", {})
        patcher.start()
        self.addCleanup(patcher.stop)

    def wait(self, job_id):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            result = operation_jobs.get_status(job_id)
            if result.get("state") in {"completed", "failed", "cancelled"}:
                return result
            time.sleep(0.01)
        self.fail("worker did not finish")

    def test_concurrent_starts_create_one_worker_and_all_find_its_result(self):
        callers = 8
        barrier, release = threading.Barrier(callers), threading.Event()
        self.addCleanup(release.set)
        replies, executed = [], []
        def request(index):
            barrier.wait(5)
            def run(job):
                executed.append(index)
                release.wait(5)
                return {"ok": True, "first": index}
            replies.append(operation_jobs.start("Shared operation", run, request_id="same-request", context={"first": index}))
        threads = [threading.Thread(target=request, args=(index,)) for index in range(callers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(6)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(replies), callers)
        self.assertEqual(len({item["job_id"] for item in replies}), 1)
        self.assertEqual(sum(bool(item.get("reused")) for item in replies), callers - 1)
        recovered = operation_jobs.find_request("same-request")
        self.assertTrue(recovered["found"])
        release.set()
        terminal = self.wait(recovered["job_id"])
        self.assertEqual(len(executed), 1)
        self.assertEqual(terminal["result"]["first"], executed[0])
        self.assertEqual(terminal["context"], {"first": executed[0]})

    def test_lost_start_response_can_be_found_while_running_and_after_completion(self):
        reached, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def run(job):
            job.progress("copying", "Controlled step", 3, 12)
            reached.set()
            release.wait(5)
            return {"ok": True, "saved": "first result"}
        operation_jobs.start("Lost response", run, request_id="lost-response", context={"kind": "import_commit"})
        self.assertTrue(reached.wait(3))
        found = operation_jobs.find_request("lost-response")
        self.assertEqual(found["state"], "running")
        self.assertEqual((found["stage"], found["current"], found["total"]), ("copying", 3, 12))
        release.set()
        self.wait(found["job_id"])
        result = operation_jobs.find_request("lost-response")
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["result"], {"ok": True, "saved": "first result"})
        forbidden = Mock(side_effect=AssertionError("a repeated request must not run"))
        again = operation_jobs.start("Repeat", forbidden, request_id="lost-response", context={"kind": "changed"})
        self.assertEqual(again["job_id"], result["job_id"])
        self.assertTrue(again["reused"])
        forbidden.assert_not_called()

    def test_cancelled_and_failed_requests_remain_terminal_when_retried(self):
        for request_id, work, state in (
            ("cancelled", lambda _: {"ok": False, "cancelled": True}, "cancelled"),
            ("failed", lambda _: {"ok": False, "error": "read failed"}, "failed"),
        ):
            with self.subTest(request_id=request_id):
                first = operation_jobs.start("Test", work, request_id=request_id)
                self.assertEqual(self.wait(first["job_id"])["state"], state)
                repeat = operation_jobs.start("Repeat", lambda _: self.fail("must not execute"), request_id=request_id)
                self.assertTrue(repeat["reused"])
                self.assertEqual(operation_jobs.find_request(request_id)["state"], state)
                self.assertFalse(operation_jobs.find_request(request_id)["can_cancel"])

    def test_request_without_id_still_starts_independent_jobs(self):
        first = operation_jobs.start("First", lambda _: {"ok": True})
        second = operation_jobs.start("Second", lambda _: {"ok": True})
        self.assertNotEqual(first["job_id"], second["job_id"])
        self.wait(first["job_id"])
        self.wait(second["job_id"])

    def test_thread_start_failure_with_request_id_is_findable_and_cleanup_runs_once(self):
        cleanup, work = Mock(), Mock()
        with patch.object(operation_jobs.threading.Thread, "start", side_effect=RuntimeError("thread unavailable")):
            first = operation_jobs.start("Failure", work, on_cancel=cleanup, request_id="not-started")
        self.assertFalse(first["ok"])
        failed = operation_jobs.find_request("not-started")
        self.assertTrue(failed["found"])
        self.assertEqual(failed["job_id"], first["job_id"])
        self.assertEqual(failed["state"], "failed")
        self.assertFalse(failed["can_cancel"])
        self.assertIn("thread unavailable", failed["result"]["error"])
        again = operation_jobs.start("Retry", work, on_cancel=cleanup, request_id="not-started")
        self.assertTrue(again["reused"])
        cleanup.assert_called_once()
        work.assert_not_called()

    def test_find_missing_or_invalid_request_does_not_create_work(self):
        self.assertEqual(operation_jobs.find_request("missing"), {"ok": True, "found": False})
        for value in (None, 3, "", "../secret", "x" * 129):
            with self.subTest(value=value):
                self.assertFalse(operation_jobs.find_request(value)["ok"])
                self.assertFalse(operation_jobs.start("Invalid", Mock(), request_id=value if value is not None else "")["ok"])
        self.assertEqual(operation_jobs._jobs, {})

    def test_returned_context_and_result_are_detached_from_stored_status(self):
        context = {"kind": "import_prepare", "selection": ["original"]}
        started = operation_jobs.start("Test", lambda _: {"ok": True, "files": ["one"]}, request_id="snapshot", context=context)
        self.wait(started["job_id"])
        context["selection"].append("changed")
        found = operation_jobs.find_request("snapshot")
        found["result"]["files"].append("changed")
        found["context"]["selection"].append("also changed")
        again = operation_jobs.find_request("snapshot")
        self.assertEqual(again["result"]["files"], ["one"])
        self.assertEqual(again["context"]["selection"], ["original"])


class ImportPreparationTrackingTests(unittest.TestCase):
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
        storage.save_mods([])
        window_patch = patch.object(main, "window", Mock())
        self.window = window_patch.start()
        self.addCleanup(window_patch.stop)
        pending = patch.object(main, "pending_imports", {})
        pending.start()
        self.addCleanup(pending.stop)
        self.addCleanup(self.cleanup_pending)
        bundles = patch.object(mod_ops, "_paths_from_bundle", return_value=["Marvel/Content/Meshes/SK_Hero.uasset"])
        bundles.start()
        self.addCleanup(bundles.stop)
        self.api = main.Api()
        self.archive = self.root / "Hero.zip"
        with zipfile.ZipFile(self.archive, "w") as stream:
            stream.writestr("Hero.pak", b"pak")

    def cleanup_pending(self):
        for token in list(main.pending_imports):
            self.api.cancel_mod_install(token)
        for item in storage.list_operation_journals():
            operation_recovery.Journal.load(item["id"]).release()

    def wait(self, job_id):
        return OperationTrackingTests.wait(self, job_id)

    def test_repeated_prepare_request_opens_native_picker_once_and_recovers_token(self):
        reached, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def choose(*args, **kwargs):
            reached.set()
            release.wait(4)
            return [str(self.archive)]
        self.window.create_file_dialog.side_effect = choose
        self.api.start_mod_import("picker-response-lost")  # Cliente não recebeu a resposta.
        self.assertTrue(reached.wait(3))
        found = self.api.find_operation("picker-response-lost")
        self.assertTrue(found["found"])
        self.assertEqual(found["context"]["kind"], "import_prepare")
        retry = self.api.start_mod_import("picker-response-lost")
        self.assertTrue(retry["reused"])
        self.assertEqual(retry["job_id"], found["job_id"])
        release.set()
        self.assertEqual(self.wait(found["job_id"])["state"], "completed")
        terminal = self.api.find_operation("picker-response-lost")
        token = terminal["result"]["token"]
        self.assertIn(token, main.pending_imports)
        self.assertNotIn("preview", terminal["result"])
        self.window.create_file_dialog.assert_called_once()
        self.assertEqual(self.api.start_mod_import("picker-response-lost")["job_id"], found["job_id"])
        self.assertEqual(storage.load_mods(), [])

    def test_native_picker_cancel_finishes_journal_and_repeat_does_not_reopen_it(self):
        for kind in ("pak", "reshade", "background", "background_audio"):
            with self.subTest(kind=kind):
                self.window.create_file_dialog.return_value = None
                started = self.api.start_mod_import("picker-cancel:" + kind, kind=kind)
                self.assertEqual(self.wait(started["job_id"])["state"], "cancelled")
                again = self.api.start_mod_import("picker-cancel:" + kind, kind=kind)
                self.assertTrue(again["reused"])
        self.assertEqual(self.window.create_file_dialog.call_count, 4)
        self.assertEqual(main.pending_imports, {})
        for journal in storage.list_operation_journals():
            self.assertEqual(journal["phase"], "cancelled")
            self.assertFalse(operation_recovery.is_live(journal["id"]))

    def test_prepare_thread_failure_is_terminal_without_opening_picker_or_journal(self):
        with patch.object(operation_jobs.threading.Thread, "start", side_effect=RuntimeError("no worker")):
            started = self.api.start_mod_import("prepare-worker-failed")
        self.assertFalse(started["ok"])
        found = self.api.find_operation("prepare-worker-failed")
        self.assertEqual(found["state"], "failed")
        self.assertFalse(found["can_cancel"])
        self.window.create_file_dialog.assert_not_called()
        self.assertEqual(storage.list_operation_journals(), [])
        self.assertEqual(main.pending_imports, {})

    def test_failed_terminal_journal_write_releases_lease_and_preserves_recovery_files(self):
        journal = operation_recovery.Journal.create("import", "Test interrupted finalization")
        payload = pathlib.Path(journal.stage_dir("payload")) / "copied.pak"
        payload.write_bytes(b"private staged bytes")
        target = self.root / "affected.pak"
        target.write_bytes(b"old bytes")
        journal.capture_files([(str(target), str(self.root))])
        journal.mark("applying")
        with patch.object(storage, "save_operation_journal", side_effect=OSError("journal disk unavailable")):
            started = operation_jobs.start("Finalize journal", lambda _: journal.finish(), request_id="finish-failed")
            result = self.wait(started["job_id"])
        self.assertEqual(result["state"], "failed")
        self.assertFalse(operation_recovery.is_live(journal.id))
        durable = storage.load_operation_journal(journal.id)
        self.assertEqual(durable["phase"], "applying")
        self.assertEqual(payload.read_bytes(), b"private staged bytes")
        snapshot = pathlib.Path(journal.root) / durable["files"][0]["backup"]
        self.assertEqual(snapshot.read_bytes(), b"old bytes")
        self.assertEqual(operation_recovery.list_pending()[0]["id"], journal.id)


if __name__ == "__main__":
    unittest.main()
