"""Trabalhos locais com progresso, cancelamento e pedidos idempotentes."""
import copy
import hashlib
import os
import re
import shutil
import subprocess
import threading
import time
import uuid


class OperationCancelled(Exception):
    def __init__(self):
        super().__init__("Operação cancelada. Os arquivos originais foram preservados.")


_lock = threading.RLock()
_jobs = {}
_local = threading.local()
_CHUNK_SIZE = 2 * 1024 * 1024


class OperationJob:
    def __init__(self, label, request_id=None, context=None):
        self.id = uuid.uuid4().hex
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._process = None
        self.request_id = request_id
        self._status = {"job_id": self.id, "state": "queued", "stage": "queued",
                        "message": label, "current": 0, "total": 0, "unit": "items",
                        "can_cancel": True, "result": None,
                        "request_id": request_id, "context": copy.deepcopy(context or {})}

    def check(self):
        if self._cancel.is_set():
            raise OperationCancelled()

    def progress(self, stage, message, current=0, total=0, unit="items"):
        self.check()
        with self._lock:
            self._status.update(stage=stage, message=message, current=max(0, current),
                                total=max(0, total), unit=unit)

    def begin_commit(self, message="Concluindo a instalação…"):
        # O clique em cancelar e esta transição compartilham o mesmo lock.
        # Depois daqui a operação precisa terminar ou restaurar o snapshot.
        with self._lock:
            self.check()
            self._status.update(stage="committing", message=message, can_cancel=False,
                                current=0, total=0, unit="items")

    def cancel(self):
        with self._lock:
            if self._status["state"] in {"completed", "failed", "cancelled"}:
                return {"ok": False, "error": "Esta operação já terminou."}
            if not self._status["can_cancel"]:
                return {"ok": False, "error": "A operação está sendo concluída. Aguarde para manter os arquivos consistentes."}
            self._cancel.set()
            process = self._process
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
        return {"ok": True}

    def run(self, command, timeout=120, *, env=None):
        with self._lock:
            self.check()
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace",
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self._process = process
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=min(0.2, max(0.01, deadline - time.monotonic())))
                    self.check()
                    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    self.check()
                    if time.monotonic() >= deadline:
                        raise
        except BaseException:
            if process.poll() is None:
                process.kill()
            process.communicate()
            raise
        finally:
            with self._lock:
                self._process = None

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._status)


def current():
    return getattr(_local, "job", None)


def check():
    job = current()
    if job:
        job.check()


def progress(stage, message, completed=0, total=0, unit="items"):
    job = current()
    if job:
        job.progress(stage, message, completed, total, unit)


def begin_commit(message="Concluindo a instalação…"):
    job = current()
    if job:
        job.begin_commit(message)


def hash_file(path, *, completed=0, total=0):
    digest = hashlib.sha256()
    done = 0
    with open(path, "rb") as stream:
        while True:
            check()
            chunk = stream.read(_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            done += len(chunk)
            progress("hash", f"Verificando {os.path.basename(path)}", completed + done, total, "bytes")
    return digest.hexdigest()


def copy_file(source, destination, *, completed=0, total=0, expected_hash=None):
    """Copia apenas para staging; uma falha nunca remove o arquivo de origem."""
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    digest = hashlib.sha256()
    done = 0
    with open(source, "rb") as incoming, open(destination, "wb") as outgoing:
        while True:
            check()
            chunk = incoming.read(_CHUNK_SIZE)
            if not chunk:
                break
            outgoing.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            progress("copying", f"Copiando {os.path.basename(source)}", completed + done, total, "bytes")
        outgoing.flush()
        os.fsync(outgoing.fileno())
    if expected_hash and digest.hexdigest() != expected_hash:
        raise ValueError("Um arquivo mudou desde a seleção. Selecione os compactados novamente.")
    shutil.copystat(source, destination)
    return done


def _request_job(request_id):
    return next((job for job in _jobs.values() if job.request_id == request_id), None)


def find_request(request_id):
    if not isinstance(request_id, str) or not re.fullmatch(r"[a-zA-Z0-9:_-]{1,128}", request_id):
        return {"ok": False, "error": "Identificador do pedido inválido."}
    with _lock:
        job = _request_job(request_id)
        return {"ok": True, "found": bool(job), **(job.snapshot() if job else {})}


def start(label, work, on_cancel=None, *, request_id=None, context=None):
    if request_id is not None and (not isinstance(request_id, str)
                                  or not re.fullmatch(r"[a-zA-Z0-9:_-]{1,128}", request_id)):
        return {"ok": False, "error": "Identificador do pedido inválido."}
    with _lock:
        existing = _request_job(request_id) if request_id else None
        if existing:
            return {"ok": True, "job_id": existing.id, "request_id": request_id, "reused": True}
        job = OperationJob(label, request_id, context)
        # Resultados recentes ficam disponíveis para o polling sem crescer
        # indefinidamente em sessões com muitas importações.
        for old_id, old in list(_jobs.items()):
            if len(_jobs) < 64:
                break
            if old.snapshot()["state"] in {"completed", "cancelled", "failed"}:
                _jobs.pop(old_id, None)
        _jobs[job.id] = job

    def worker():
        _local.job = job
        with job._lock:
            job._status["state"] = "running"
        try:
            job.check()
            result = work(job)
            state = "cancelled" if isinstance(result, dict) and result.get("cancelled") else (
                "failed" if isinstance(result, dict) and result.get("ok") is False else "completed")
            with job._lock:
                job._status.update(state=state, can_cancel=False, result=result)
                if state == "failed":
                    job._status["error"] = result.get("error", "Não foi possível concluir a operação.")
        except OperationCancelled as exc:
            cleanup_error = None
            if on_cancel:
                try:
                    on_cancel()
                except Exception as error:
                    cleanup_error = str(error)
            with job._lock:
                job._status.update(state="failed" if cleanup_error else "cancelled", can_cancel=False,
                                   result={"ok": False, "cancelled": not cleanup_error,
                                           "error": cleanup_error or str(exc)})
                if cleanup_error:
                    job._status["error"] = cleanup_error
        except Exception as exc:
            with job._lock:
                job._status.update(state="failed", can_cancel=False, error=str(exc),
                                   result={"ok": False, "error": str(exc)})
        finally:
            _local.job = None

    try:
        threading.Thread(target=worker, name="mod-import-" + job.id[:8], daemon=True).start()
    except Exception as exc:
        # A seleção já pode ter sido transferida para este trabalho. Se o
        # sistema não conseguir iniciar a thread, não deixa staging/lease
        # reservados para um worker que nunca vai executar.
        with _lock:
            if not request_id:
                _jobs.pop(job.id, None)
        error = str(exc)
        if on_cancel:
            try:
                on_cancel()
            except Exception as cleanup_error:
                error += f" — Não foi possível descartar a preparação: {cleanup_error}"
        with job._lock:
            job._status.update(state="failed", can_cancel=False, error=error,
                               result={"ok": False, "error": error})
        return {"ok": False, "error": error, **({"job_id": job.id} if request_id else {})}
    return {"ok": True, "job_id": job.id, "request_id": request_id}


def get_status(job_id):
    with _lock:
        job = _jobs.get(str(job_id))
    return {"ok": True, **job.snapshot()} if job else {"ok": False, "error": "Operação não encontrada."}


def cancel(job_id):
    with _lock:
        job = _jobs.get(str(job_id))
    return job.cancel() if job else {"ok": False, "error": "Operação não encontrada."}
