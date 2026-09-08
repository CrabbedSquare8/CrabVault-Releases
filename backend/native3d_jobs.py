"""Cancellable, bounded native preview jobs. Never stops unrelated processes."""
import contextlib
import subprocess
import threading
import time
import uuid


class PreviewCancelled(Exception):
    pass


class PreviewJob:
    def __init__(self):
        self.cancelled = threading.Event()
        self._lock = threading.Lock()
        self._process = None

    def check(self):
        if self.cancelled.is_set():
            raise PreviewCancelled()

    def cancel(self):
        self.cancelled.set()
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                try:
                    self._process.terminate()
                except OSError:
                    pass

    def run(self, command, timeout=120):
        with self._lock:
            self.check()
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self._process = process
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            self.check()
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise
        finally:
            with self._lock:
                self._process = None


_lock = threading.Lock()
_jobs = {}
_early_cancellations = {}


def cancel(request_id):
    token = str(request_id or "")[:128]
    if not token:
        return {"ok": True}
    with _lock:
        job = _jobs.get(token)
        if job is None:
            # Esc can reach Python before the corresponding prepare call.
            now = time.monotonic()
            for old, at in list(_early_cancellations.items()):
                if now - at > 120 or len(_early_cancellations) >= 128:
                    _early_cancellations.pop(old, None)
            _early_cancellations[token] = now
    if job is not None:
        job.cancel()
    return {"ok": True}


@contextlib.contextmanager
def request(request_id=None):
    token = str(request_id or uuid.uuid4().hex)[:128]
    job = PreviewJob()
    with _lock:
        previous = _jobs.get(token)
        _jobs[token] = job
        cancelled_at = _early_cancellations.pop(token, None)
        if cancelled_at is not None and time.monotonic() - cancelled_at < 120:
            job.cancelled.set()
    if previous is not None:
        previous.cancel()
    try:
        job.check()
        yield job
    finally:
        job.cancel()
        with _lock:
            if _jobs.get(token) is job:
                _jobs.pop(token, None)
