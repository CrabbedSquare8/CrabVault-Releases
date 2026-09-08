"""Journal durável de operações em arquivos; nenhum reparo ocorre ao abrir o app."""
import copy
import os
import shutil
import tempfile
import threading

from . import storage, operation_jobs


_live_lock = threading.RLock()
_live = set()
_leases = {}
_TERMINAL = {"completed", "cancelled", "recovered", "aborted"}


def _open_lease(operation_id):
    """Retorna um lock não bloqueante, liberado também se o processo encerrar."""
    path = os.path.join(storage.operation_dir(operation_id), "active.lock")
    stream = open(path, "a+b")
    try:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return stream
    except BaseException:
        stream.close()
        raise


def _claim(operation_id):
    with _live_lock:
        if operation_id in _live:
            return
        try:
            lease = _open_lease(operation_id)
        except OSError as error:
            raise ValueError("Esta operação ainda está em andamento em outra instância, ou seu registro está inacessível.") from error
        _leases[operation_id] = lease
        _live.add(operation_id)


def _inside(path, root, allow_root=False):
    absolute = os.path.realpath(path)
    base = os.path.realpath(root)
    try:
        valid = os.path.commonpath([os.path.normcase(absolute), os.path.normcase(base)]) == os.path.normcase(base)
    except ValueError:
        valid = False
    if not valid or (not allow_root and os.path.normcase(absolute) == os.path.normcase(base)):
        raise ValueError("Um caminho da operação está fora do diretório permitido.")
    return absolute


def _clean_tree(path, root):
    checked = _inside(path, root)
    if os.path.isdir(checked):
        shutil.rmtree(checked)


class Journal:
    def __init__(self, data):
        self.data = data
        self.id = data["id"]
        self.root = storage.operation_dir(self.id, create=True)

    @classmethod
    def create(cls, kind, title, before_records=None, after_records=None, mods_path=""):
        journal = cls({"id": storage.new_id(), "kind": kind, "title": title,
                       "created_at": storage.now_iso(), "phase": "preparing",
                       "mods_path": os.path.realpath(mods_path) if mods_path else "",
                       "storage_root": os.path.realpath(storage.STORAGE_DIR),
                       "before_records": copy.deepcopy(before_records or []),
                       "after_records": copy.deepcopy(after_records or []),
                       "files": [], "owned_dirs": [], "snapshot_ready": False,
                       "mutation_started": False})
        _claim(journal.id)
        try:
            journal.save()
        except BaseException:
            journal.release()
            raise
        return journal

    @classmethod
    def load(cls, operation_id, resume=False):
        data = storage.load_operation_journal(operation_id)
        if not data:
            raise ValueError("Registro de recuperação não encontrado.")
        journal = cls(data)
        if resume:
            _claim(journal.id)
            try:
                # Outra instância pode ter concluído a operação entre a
                # primeira leitura e a obtenção do lock.
                journal.data = storage.load_operation_journal(operation_id)
                if not journal.data:
                    raise ValueError("Registro de recuperação não encontrado.")
            except BaseException:
                journal.release()
                raise
        return journal

    def save(self):
        self.data["updated_at"] = storage.now_iso()
        storage.save_operation_journal(self.data)

    def mark(self, phase):
        self.data["phase"] = phase
        if phase == "applying":
            self.data["mutation_started"] = True
        self.save()

    def set_records(self, before_records, after_records):
        self.data["before_records"] = copy.deepcopy(before_records)
        self.data["after_records"] = copy.deepcopy(after_records)
        self.save()

    def set_settings(self, before_fields, after_fields):
        self.data["settings_before"] = copy.deepcopy(before_fields)
        self.data["settings_after"] = copy.deepcopy(after_fields)
        self.save()

    def stage_dir(self, name):
        if name not in {"payload", "extracted", "files"}:
            raise ValueError("Diretório temporário inválido.")
        path = _inside(os.path.join(self.root, name), self.root)
        os.makedirs(path, exist_ok=True)
        return path

    def own_storage_dir(self, path):
        target = _inside(path, storage.STORAGE_DIR)
        if os.path.exists(target):
            raise ValueError("A pasta reservada para a importação já existe.")
        if target not in self.data["owned_dirs"]:
            self.data["owned_dirs"].append(target)
            self.save()

    def capture_files(self, paths):
        """Guarda todos os estados anteriores antes de permitir qualquer mutação.

        `paths` contém pares (arquivo absoluto, raiz permitida). Hard links
        preservam os bytes sem duplicar GB: os instaladores sempre substituem
        o arquivo de destino, nunca editam seu conteúdo no lugar.
        """
        self.mark("snapshotting")
        entries, seen = [], set()
        backup_root = self.stage_dir("files")
        paths = list(paths)
        for index, (path, root) in enumerate(paths):
            job = operation_jobs.current()
            stage = "committing" if job and not job.snapshot()["can_cancel"] else "snapshotting"
            operation_jobs.progress(stage, "Preservando os arquivos que serão alterados…", index, len(paths))
            target = _inside(path, root)
            key = os.path.normcase(target)
            if key in seen:
                continue
            seen.add(key)
            if os.path.islink(path) or os.path.isdir(target):
                raise ValueError("O destino da operação não é um arquivo regular.")
            item = {"path": target, "root": os.path.realpath(root), "existed": os.path.isfile(target)}
            if item["existed"]:
                backup = os.path.join(backup_root, str(len(entries)))
                try:
                    os.link(target, backup)
                except OSError:
                    if stage == "committing":
                        shutil.copy2(target, backup)
                    else:
                        operation_jobs.copy_file(target, backup)
                item["backup"] = os.path.relpath(backup, self.root)
                item["size"] = os.path.getsize(target)
            entries.append(item)
        self.data["files"] = entries
        self.data["snapshot_ready"] = True
        self.mark("prepared")

    def release(self):
        with _live_lock:
            _live.discard(self.id)
            lease = _leases.pop(self.id, None)
            if lease:
                lease.close()

    def fail(self, error):
        self.data["error"] = str(error)
        try:
            self.save()
        finally:
            self.release()

    def finish(self, state="completed"):
        if state not in _TERMINAL:
            raise ValueError("Estado final da operação inválido.")
        # Primeiro registra o sucesso/rollback de forma durável. Se a limpeza
        # for interrompida, sobram apenas temporários reconhecíveis.
        try:
            self.mark(state)
        finally:
            # Uma falha no JSON final não pode deixar uma operação sem worker
            # presa como "em andamento". Sem a marca durável, conserva todos
            # os temporários/snapshots para a recuperação após liberar o lease.
            self.release()
        for name in ("payload", "extracted", "files"):
            try:
                _clean_tree(os.path.join(self.root, name), self.root)
            except (OSError, ValueError):
                pass


def is_live(operation_id):
    with _live_lock:
        if str(operation_id) in _live:
            return True
        if not os.path.isdir(storage.operation_dir(operation_id)):
            return False
        try:
            lease = _open_lease(operation_id)
        except OSError:
            return True
        lease.close()
        return False


def list_pending():
    return [{"id": data["id"], "kind": data.get("kind", "operation"),
             "title": data.get("title", "Operação interrompida"),
             "created_at": data.get("created_at"), "phase": data.get("phase"),
             "error": data.get("error", ""), "can_restore": True,
             "message": ("Restaurar os arquivos e o catálogo anteriores."
                         if data.get("mutation_started") else
                         "Descartar somente a preparação incompleta; os originais foram preservados.")}
            for data in storage.list_operation_journals()
            if data.get("phase") not in _TERMINAL and not is_live(data["id"])]


def prepare_catalog_restore(journal):
    """Valida a reversão antes de tocar no disco e preserva edições independentes."""
    mods = storage.load_mods()
    before = {str(item["id"]): item for item in journal.data.get("before_records", [])}
    after = {str(item["id"]): item for item in journal.data.get("after_records", [])}
    current = {str(item["id"]): item for item in mods}
    restored = {}
    for mod_id in before.keys() | after.keys():
        restored[mod_id] = storage._merge(
            after.get(mod_id, storage._MISSING), before.get(mod_id, storage._MISSING),
            current.get(mod_id, storage._MISSING), f"recuperação[{mod_id}]",
        )
    mods[:] = [restored.pop(str(item["id"]), item) for item in mods]
    mods[:] = [item for item in mods if item is not storage._MISSING]
    mods.extend(item for item in restored.values() if item is not storage._MISSING)
    _prepare_settings_restore(journal)
    return mods


def restore_catalog(journal):
    mods = prepare_catalog_restore(journal)
    storage.save_mods(mods)
    settings = _prepare_settings_restore(journal)
    if settings is not None:
        storage.save_settings(settings)


def _prepare_settings_restore(journal):
    if "settings_before" not in journal.data:
        return None
    settings = storage.load_settings()
    before, after = journal.data["settings_before"], journal.data["settings_after"]
    for key in before.keys() | after.keys():
        value = storage._merge(after.get(key, storage._MISSING), before.get(key, storage._MISSING),
                               settings.get(key, storage._MISSING), f"recuperação.configurações.{key}")
        if value is storage._MISSING:
            settings.pop(key, None)
        else:
            settings[key] = value
    return settings


def restore_files(journal):
    """Idempotente; mantém snapshots até que o catálogo também seja restaurado."""
    if not journal.data.get("mutation_started"):
        return
    if not journal.data.get("snapshot_ready"):
        raise ValueError("A operação não possui um snapshot completo dos arquivos.")
    entries = journal.data.get("files", [])
    for item in entries:
        _inside(item["path"], item["root"])
        if item["existed"]:
            backup = _inside(os.path.join(journal.root, item["backup"]), journal.root)
            if not os.path.isfile(backup) or os.path.getsize(backup) != item.get("size"):
                raise OSError("Um arquivo do snapshot está ausente ou incompleto. A recuperação foi interrompida.")
    for item in entries:
        target = _inside(item["path"], item["root"])
        if item["existed"]:
            backup = _inside(os.path.join(journal.root, item["backup"]), journal.root)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".mod-restore-", dir=os.path.dirname(target))
            os.close(descriptor)
            try:
                os.remove(temporary)
                try:
                    os.link(backup, temporary)
                except OSError:
                    shutil.copy2(backup, temporary)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.remove(temporary)
        elif os.path.isfile(target):
            os.remove(target)


def validate_workspace(journal):
    """Valida a biblioteca antes de restaurar arquivos ou alterar o catálogo."""
    if os.path.normcase(os.path.realpath(storage.STORAGE_DIR)) != os.path.normcase(journal.data["storage_root"]):
        raise ValueError("O diretório da biblioteca mudou. Restaure o caminho anterior antes de recuperar esta operação.")


def _owned_dirs_for_cleanup(journal, current):
    validate_workspace(journal)
    referenced = {os.path.normcase(_inside(os.path.join(storage.STORAGE_DIR, item.get("storage_folder") or str(item["id"])),
                                          storage.STORAGE_DIR))
                  for item in current}
    before_ids = {str(item["id"]) for item in journal.data.get("before_records", [])}
    newly_created = {os.path.normcase(_inside(os.path.join(storage.STORAGE_DIR, item["storage_folder"]), storage.STORAGE_DIR))
                     for item in journal.data.get("after_records", [])
                     if str(item["id"]) not in before_ids and item.get("storage_folder")}
    result = []
    for path in journal.data.get("owned_dirs", []):
        checked = _inside(path, storage.STORAGE_DIR)
        if not journal.data.get("mutation_started"):
            # O destino definitivo só é criado após a fase "applying".
            # Uma pasta surgida antes disso não pertence à preparação.
            if os.path.lexists(checked):
                raise ValueError("A pasta reservada para a importação foi ocupada; seu conteúdo foi preservado.")
            continue
        key = os.path.normcase(checked)
        if key not in newly_created:
            raise ValueError("A pasta do snapshot não pertence a um mod criado nesta operação.")
        if any(os.path.commonpath([key, ref]) in {key, ref} for ref in referenced):
            raise ValueError("A pasta da importação ainda é usada pelo catálogo; ela não foi removida.")
        result.append(checked)
    return result


def cleanup_owned_dirs(journal):
    for checked in _owned_dirs_for_cleanup(journal, storage.load_mods()):
        _clean_tree(checked, storage.STORAGE_DIR)


def rollback(journal):
    """O chamador deve manter o lock operacional e respeitar o bloqueio do jogo."""
    # Evita uma edição de metadados da mesma instância entre a pré-validação
    # e a restauração. A gravação mantém a mesclagem entre processos.
    with storage._WRITE_LOCK:
        validate_workspace(journal)
        current = prepare_catalog_restore(journal) if journal.data.get("mutation_started") else storage.load_mods()
        _owned_dirs_for_cleanup(journal, current)
        if journal.data.get("mutation_started"):
            restore_files(journal)
            restore_catalog(journal)
        cleanup_owned_dirs(journal)
        journal.finish("recovered")
