"""
storage.py — leitura/escrita dos arquivos de dados (mods.json, settings.json)
e definição de onde tudo fica salvo em disco.
"""
import os
import json
import uuid
import datetime
import copy
import tempfile
import threading
import sys
from contextlib import contextmanager

IS_PACKAGED = bool(getattr(sys, "frozen", False) or "__compiled__" in globals())
RESOURCE_DIR = (getattr(sys, "_MEIPASS", None)
                or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE_DIR = (os.path.dirname(os.path.abspath(sys.argv[0]))
            if IS_PACKAGED else RESOURCE_DIR)
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
MODS_JSON = os.path.join(BASE_DIR, "mods.json")
STORAGE_DIR = os.path.join(BASE_DIR, "mods_storage")  # onde os arquivos dos mods ficam guardados
BACKUPS_DIR = os.path.join(BASE_DIR, "backups")  # backups de catálogo criados pelo Manager
CHARACTER_CATALOG_CACHE_DIR = os.path.join(BASE_DIR, ".cache", "character_catalog")
CHARACTER_CATALOG_CACHE_FILE = os.path.join(CHARACTER_CATALOG_CACHE_DIR, "character_data.json")
CHARACTER_CATALOG_STATUS_FILE = os.path.join(CHARACTER_CATALOG_CACHE_DIR, "status.json")

_WRITE_LOCK = threading.RLock()
_MISSING = object()


class ConcurrentUpdateError(RuntimeError):
    pass


class _LoadedList(list):
    pass


class _LoadedDict(dict):
    pass


def _snapshot(value):
    result = _LoadedList(value) if isinstance(value, list) else _LoadedDict(value)
    result.baseline = copy.deepcopy(value)
    return result


def _merge(base, edited, current, path="catálogo"):
    """Mescla campos independentes; nunca perde silenciosamente uma edição."""
    if edited == base:
        return _MISSING if current is _MISSING else copy.deepcopy(current)
    if current == base or edited == current:
        return _MISSING if edited is _MISSING else copy.deepcopy(edited)
    if all(isinstance(value, dict) for value in (base, edited, current)):
        result = {}
        for key in dict.fromkeys([*current, *edited, *base]):
            value = _merge(base.get(key, _MISSING), edited.get(key, _MISSING),
                           current.get(key, _MISSING), f"{path}.{key}")
            if value is not _MISSING:
                result[key] = value
        return result
    if all(isinstance(value, list) for value in (base, edited, current)) and all(
            isinstance(item, dict) and item.get("id") for value in (base, edited, current) for item in value):
        mappings = [{item["id"]: item for item in value} for value in (base, edited, current)]
        if any(len(mapping) != len(value) for mapping, value in zip(mappings, (base, edited, current))):
            raise ConcurrentUpdateError(f"IDs duplicados em {path}.")
        old, new, live = mappings
        base_order = [item["id"] for item in base if item["id"] in new and item["id"] in live]
        edit_order = [item["id"] for item in edited if item["id"] in base_order]
        live_order = [item["id"] for item in current if item["id"] in base_order]
        if edit_order != base_order and live_order != base_order and edit_order != live_order:
            raise ConcurrentUpdateError(f"A ordem de {path} mudou em outra operação. Atualize e tente novamente.")
        order = edited if edit_order != base_order else current
        result = []
        for key in dict.fromkeys([*(item["id"] for item in order), *new, *live]):
            value = _merge(old.get(key, _MISSING), new.get(key, _MISSING), live.get(key, _MISSING), f"{path}[{key}]")
            if value is not _MISSING:
                result.append(value)
        return result
    raise ConcurrentUpdateError(f"{path} mudou em outra operação. Atualize a tela e tente novamente.")


@contextmanager
def _write_guard(path):
    # Coordena threads e outras instâncias do Manager. A leitura continua
    # livre: os leitores enxergam o JSON anterior ou o novo, nunca metade.
    with _WRITE_LOCK:
        with open(path + ".lock", "a+b") as lock_file:
            lock_file.seek(0)
            if os.path.getsize(path + ".lock") == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                yield
            finally:
                lock_file.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)


def _save_json(path, value, only_if_missing=False):
    with _write_guard(path):
        if only_if_missing and os.path.exists(path):
            return
        merged = value
        if hasattr(value, "baseline") and os.path.isfile(path):
            with open(path, encoding="utf-8") as stream:
                merged = _merge(value.baseline, value, json.load(stream))
        # Serializa antes de tocar no arquivo original; falhas deixam-no íntegro.
        payload = json.dumps(merged, indent=2, ensure_ascii=False)
        descriptor, temporary = tempfile.mkstemp(prefix=".catalog-", suffix=".tmp", dir=os.path.dirname(path))
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        if hasattr(value, "baseline"):
            # Mantém a base da visão do chamador; o próximo save volta a
            # mesclar alterações concorrentes sem removê-las.
            value.baseline = copy.deepcopy(list(value) if isinstance(value, list) else dict(value))

DEFAULT_SETTINGS = {
    "mods_path": "",
    "launcher": "steam",
    "auto_open_details": True,
    "hide_file_suffix": False,
    "show_type_badge": False,
    "bypass_game_running_lock": False,
    # O conteúdo instalável sempre fica na biblioteca privada. Estas opções
    # controlam somente o compactado original e os arquivos selecionados fora
    # do Manager depois que a confirmação termina com sucesso.
    "preserve_import_archives": True,
    "delete_import_sources_after_success": True,
    "theme_mode": "dark",
    "preview_volume": 0.5,
    "ui_language": "pt-BR",
    "language_selected": False,
    "tutorial_completed": False,
    "installed_scan_completed": False,
    "settings_ui_version": 10,
    # Estado imediatamente anterior à última operação em massa. Não é um
    # backup de arquivos: serve apenas para reverter switches, prioridades e
    # componentes sem precisar montar um perfil manual.
    "last_recovery_snapshot": None,
    # Histórico curto das ações do usuário. Fica no settings.json para não
    # interferir no catálogo nem exigir uma base de dados separada.
    "activity_log": [],
    # Alterações de bancos Wwise pedidas enquanto o jogo está aberto. Elas são
    # aplicadas assim que o processo do Marvel Rivals encerrar.
    "pending_background_audio_changes": [],
}


def ensure_dirs():
    os.makedirs(STORAGE_DIR, exist_ok=True)
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    if not os.path.exists(SETTINGS_FILE):
        _save_json(SETTINGS_FILE, dict(DEFAULT_SETTINGS), only_if_missing=True)
    if not os.path.exists(MODS_JSON):
        _save_json(MODS_JSON, [], only_if_missing=True)


def load_settings():
    ensure_dirs()
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        settings = _snapshot(json.load(f))
    previous_ui_version = int(settings.get("settings_ui_version", 0) or 0)
    changed = False
    # Remove a opção experimental de Nexus/API e qualquer chave pessoal que
    # tenha sido salva durante esse teste local.
    if "nexus_api_key" in settings:
        settings.pop("nexus_api_key", None)
        changed = True
    # A integração experimental com UModel foi removida; o caminho antigo não
    # deve permanecer como uma configuração morta.
    if "umodel_path" in settings:
        settings.pop("umodel_path", None)
        changed = True
    for key, value in DEFAULT_SETTINGS.items():
        if key not in settings:
            settings[key] = value
            changed = True
    # A caixa antiga existia, mas ainda não controlava a abertura de detalhes.
    # Na migração para a configuração funcional preservamos o comportamento que
    # o usuário já tinha: abrir detalhes automaticamente.
    if previous_ui_version < 8:
        settings["auto_open_details"] = True
        changed = True
    if previous_ui_version < 10:
        settings["settings_ui_version"] = 10
        changed = True
    if changed:
        save_settings(settings)
    return settings


def save_settings(data):
    _save_json(SETTINGS_FILE, data)


def load_character_catalog_cache():
    """Lê a cópia atualizável do catálogo sem tocar no fallback incluído."""
    if not os.path.isfile(CHARACTER_CATALOG_CACHE_FILE):
        return None
    with open(CHARACTER_CATALOG_CACHE_FILE, encoding="utf-8") as stream:
        return json.load(stream)


def save_character_catalog_cache(data):
    os.makedirs(CHARACTER_CATALOG_CACHE_DIR, exist_ok=True)
    _save_json(CHARACTER_CATALOG_CACHE_FILE, data)


def load_character_catalog_status():
    if not os.path.isfile(CHARACTER_CATALOG_STATUS_FILE):
        return {}
    try:
        with open(CHARACTER_CATALOG_STATUS_FILE, encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_character_catalog_status(data):
    os.makedirs(CHARACTER_CATALOG_CACHE_DIR, exist_ok=True)
    _save_json(CHARACTER_CATALOG_STATUS_FILE, data)


def load_mods():
    ensure_dirs()
    with open(MODS_JSON, "r", encoding="utf-8") as f:
        return _snapshot(json.load(f))


def save_mods(mods):
    _save_json(MODS_JSON, mods)


def personal_corrections_path():
    """Preferências por conteúdo, independentes da existência de um mod."""
    return os.path.join(os.path.dirname(MODS_JSON), "personal_corrections.json")


def load_personal_corrections():
    path = personal_corrections_path()
    if not os.path.isfile(path):
        return _snapshot({"version": 1, "records": []})
    with open(path, encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("records"), list):
        raise ValueError("O registro de correções pessoais tem formato inválido.")
    return _snapshot(value)


def save_personal_corrections(data):
    _save_json(personal_corrections_path(), data)


def new_id():
    return uuid.uuid4().hex[:12]


def now_iso():
    return datetime.datetime.now().isoformat()


def mod_storage_dir(mod_id):
    d = os.path.join(STORAGE_DIR, mod_id)
    os.makedirs(d, exist_ok=True)
    return d


def operation_dir(operation_id, create=False):
    """Diretório privado de um journal e seus arquivos temporários."""
    token = str(operation_id)
    if not 12 <= len(token) <= 32 or any(character not in "0123456789abcdef" for character in token):
        raise ValueError("Identificador de operação inválido.")
    root = os.path.realpath(os.path.join(BACKUPS_DIR, "operations"))
    path = os.path.realpath(os.path.join(root, token))
    if os.path.commonpath([root, path]) != root or path == root:
        raise ValueError("Caminho de operação inválido.")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def save_operation_journal(journal):
    path = os.path.join(operation_dir(journal["id"], create=True), "journal.json")
    _save_json(path, journal)


def load_operation_journal(operation_id):
    path = os.path.join(operation_dir(operation_id), "journal.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as stream:
        journal = json.load(stream)
    if not isinstance(journal, dict) or journal.get("id") != str(operation_id):
        raise ValueError("Registro de recuperação inválido.")
    return journal


def list_operation_journals():
    root = os.path.join(BACKUPS_DIR, "operations")
    if not os.path.isdir(root):
        return []
    result = []
    for name in os.listdir(root):
        try:
            journal = load_operation_journal(name)
        except (ValueError, OSError):
            continue
        if journal:
            result.append(journal)
    return result
