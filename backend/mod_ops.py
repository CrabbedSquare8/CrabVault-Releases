"""
mod_ops.py - regras de negocio: adicionar mod, ativar/desativar, tags,
personagens/skins/tipos, pastas (recursivo), auto-deteccao de pasta do
jogo via Steam, prioridade.
"""
import os
import re
import shutil
import pathlib
import subprocess
import base64
import mimetypes
import io
import hashlib
import json
import threading
import time
import tempfile
import struct
import stat as stat_module
import urllib.parse
import copy
import difflib
from functools import wraps

try:
    from PIL import Image
except ImportError:
    Image = None

from . import (storage, native3d_jobs, native3d_support, component_rules,
               operation_jobs, operation_recovery, characters, character_catalog)
from .characters import MARVEL_CHARACTERS, CHARACTER_BY_ID, SKIN_BY_ID, SKIN_ICON_BY_ID, canonical_skin_name

_FILE_OPERATION_LOCK = threading.RLock()
_DETAIL_METADATA_CACHE_LOCK = threading.Lock()
_DETAIL_METADATA_CACHE = {}
_DETAIL_METADATA_CACHE_LIMIT = 16


def _detail_metadata_revision():
    """Identifica mudanças persistentes sem reler o catálogo inteiro."""
    revision = []
    for path in (storage.MODS_JSON, storage.SETTINGS_FILE):
        try:
            info = os.stat(path)
            revision.append((os.path.abspath(path), info.st_mtime_ns, info.st_size, info.st_ino))
        except OSError:
            revision.append((os.path.abspath(path), None, None, None))
    return tuple(revision)


def _cached_mod_details(mod_id):
    key = (str(mod_id), _detail_metadata_revision())
    with _DETAIL_METADATA_CACHE_LOCK:
        cached = _DETAIL_METADATA_CACHE.get(key)
        if cached is None:
            return None
        _DETAIL_METADATA_CACHE.pop(key)
        _DETAIL_METADATA_CACHE[key] = cached
        return copy.deepcopy(cached)


def _remember_mod_details(mod_id, mod):
    key = (str(mod_id), _detail_metadata_revision())
    with _DETAIL_METADATA_CACHE_LOCK:
        for stale in [item for item in _DETAIL_METADATA_CACHE if item[0] == str(mod_id)]:
            _DETAIL_METADATA_CACHE.pop(stale, None)
        _DETAIL_METADATA_CACHE[key] = copy.deepcopy(mod)
        while len(_DETAIL_METADATA_CACHE) > _DETAIL_METADATA_CACHE_LIMIT:
            _DETAIL_METADATA_CACHE.pop(next(iter(_DETAIL_METADATA_CACHE)))


def _serialized_files(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if operation_jobs.current():
            while not _FILE_OPERATION_LOCK.acquire(timeout=0.1):
                operation_jobs.progress("waiting", "Aguardando outra operação em arquivos…")
            try:
                operation_jobs.check()
                return function(*args, **kwargs)
            finally:
                _FILE_OPERATION_LOCK.release()
        with _FILE_OPERATION_LOCK:
            return function(*args, **kwargs)
    return wrapped

_HERO_ID_BY_NAME = {}
_SKIN_ICON_BY_CHARACTER_AND_NAME = {}
_HERO_FALLBACK_ICON_BY_NAME = {}


def _refresh_identity_indexes():
    """Atualiza os atalhos derivados sem trocar objetos importados por outros módulos."""
    hero_ids = {name: ident for ident, name in CHARACTER_BY_ID.items()}
    skin_icons = {}
    for skin_id, (skin_character, skin_name) in SKIN_BY_ID.items():
        icon = SKIN_ICON_BY_ID.get(skin_id)
        if icon:
            skin_icons.setdefault((skin_character, canonical_skin_name(skin_name, skin_character)), icon)
    fallback_icons = {character: icon for (character, skin), icon in skin_icons.items() if skin == "Default"}
    _HERO_ID_BY_NAME.clear(); _HERO_ID_BY_NAME.update(hero_ids)
    _SKIN_ICON_BY_CHARACTER_AND_NAME.clear(); _SKIN_ICON_BY_CHARACTER_AND_NAME.update(skin_icons)
    _HERO_FALLBACK_ICON_BY_NAME.clear(); _HERO_FALLBACK_ICON_BY_NAME.update(fallback_icons)


_refresh_identity_indexes()

# A lista principal pode ter centenas de cards. Sem este cache, cada recarga
# lia e codificava novamente todas as miniaturas em Base64, mesmo quando nada
# havia mudado no disco. O cache vive apenas enquanto o aplicativo está aberto
# e é invalidado pelo tamanho/data de modificação do arquivo.
_THUMBNAIL_URL_CACHE = {}
_THUMBNAIL_URL_CACHE_LIMIT = 512

# A conversão acontece sob demanda e todo o trabalho/cache fica no projeto,
# que neste ambiente está no disco D:. Abrir os detalhes do mod nunca toca
# nesse pipeline; ele só é iniciado pelo botão 3D de um componente Mesh.
_NATIVE3D_CACHE_VERSION = "native3d-v7-independent-direct-files"
_NATIVE3D_CACHE_ROOT = os.path.join(storage.RESOURCE_DIR, "frontend", "viewer-cache")
_NATIVE3D_WORK_ROOT = os.path.join(storage.BASE_DIR, ".cache", "native3d")
_NATIVE3D_EXTRACTOR_EXE = os.path.join(storage.RESOURCE_DIR, "tools", "native3d", "runtime", "Marvel3DExtractor.exe")
_NATIVE3D_EXTRACTOR_DLL = os.path.join(storage.RESOURCE_DIR, "tools", "native3d", "bin", "Release", "net10.0", "Marvel3DExtractor.dll")
_NATIVE3D_DOTNET = os.path.join(storage.RESOURCE_DIR, ".dotnet-sdk-10", "dotnet.exe")
_NATIVE3D_PREVIEW_LOCK = threading.Lock()


def _record_activity(action, message, metadata=None):
    """Acrescenta uma ação curta ao histórico persistente da interface."""
    settings = storage.load_settings()
    history = settings.get("activity_log", [])
    if not isinstance(history, list):
        history = []
    entry = {
        "id": storage.new_id(),
        "at": storage.now_iso(),
        "action": str(action or "action"),
        "message": str(message or "Alteração no catálogo"),
    }
    if metadata:
        entry["metadata"] = metadata
    settings["activity_log"] = [entry, *history][:100]
    storage.save_settings(settings)


def get_activity_log(limit=60):
    """Retorna o histórico mais recente, sem expor opções internas."""
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 60
    history = storage.load_settings().get("activity_log", [])
    if not isinstance(history, list):
        return []
    return [entry for entry in history[:limit] if isinstance(entry, dict)]


def clear_activity_log():
    settings = storage.load_settings()
    settings["activity_log"] = []
    storage.save_settings(settings)
    return {"ok": True}


def clear_old_activity_log(days=30):
    """Remove somente entradas anteriores ao número de dias informado."""
    try:
        days = max(1, min(int(days), 3650))
    except (TypeError, ValueError):
        return {"ok": False, "error": "Período inválido."}
    cutoff = time.time() - (days * 86400)
    settings = storage.load_settings()
    history = settings.get("activity_log", []) if isinstance(settings.get("activity_log", []), list) else []
    kept = []
    for entry in history:
        try:
            timestamp = time.mktime(time.strptime(str(entry.get("at", ""))[:19], "%Y-%m-%dT%H:%M:%S"))
        except (TypeError, ValueError, OverflowError):
            timestamp = time.time()
        if timestamp >= cutoff:
            kept.append(entry)
    settings["activity_log"] = kept
    storage.save_settings(settings)
    return {"ok": True, "removed": len(history) - len(kept)}


def record_import_performance(sample):
    """Guarda medições curtas do frontend para diagnosticar pausas pós-importação."""
    if not isinstance(sample, dict):
        return {"ok": False, "error": "Medição inválida."}
    allowed = ("prepare_ms", "commit_ms", "reload_ms", "detail_ms", "total_ms", "backend_ms")
    normalized = {"at": storage.now_iso(), "kind": str(sample.get("kind") or "import")[:40],
                  "mod_id": str(sample.get("mod_id") or "")[:100]}
    for key in allowed:
        try:
            value = max(0.0, min(float(sample.get(key, 0) or 0), 3_600_000.0))
        except (TypeError, ValueError):
            value = 0.0
        normalized[key] = round(value, 2)
    settings = storage.load_settings()
    entries = settings.get("import_performance_log", [])
    if not isinstance(entries, list):
        entries = []
    settings["import_performance_log"] = [normalized, *entries][:30]
    storage.save_settings(settings)
    return {"ok": True, "sample": normalized}


def get_import_performance(limit=10):
    try:
        limit = max(1, min(int(limit), 30))
    except (TypeError, ValueError):
        limit = 10
    entries = storage.load_settings().get("import_performance_log", [])
    return [entry for entry in entries[:limit] if isinstance(entry, dict)] if isinstance(entries, list) else []


def _hero_icon_url(character):
    """Retrato local do herói; para heróis novos usa a skin Default oficial."""
    hero_id = _HERO_ID_BY_NAME.get(character)
    hero_path = os.path.join(storage.RESOURCE_DIR, "frontend", "assets", "hero", f"{hero_id}.png") if hero_id else ""
    if hero_path and os.path.exists(hero_path):
        return f"assets/hero/{hero_id}.png"
    return _HERO_FALLBACK_ICON_BY_NAME.get(character)


def _safe_storage_segment(value, fallback):
    value = re.sub(r'[<>:"/\\\\|?*]+', "_", (value or "").strip()).strip(". ")
    return value or fallback


def _safe_game_folder(folder):
    """Normaliza um caminho relativo de ~mods para nomes válidos no Windows.

    A skin exibida pode manter caracteres como ``:``; somente a pasta física
    recebe a versão segura (por exemplo, ``Helen Angerboda_ The Rebel``).
    """
    parts = pathlib.PureWindowsPath(str(folder or "")).parts
    safe_parts = []
    for part in parts:
        if part in (".", "", "\\", "/"):
            continue
        if part == "..":
            raise ValueError("Destino inválido.")
        safe_parts.append(_safe_storage_segment(part, "Mod"))
    return os.path.join(*safe_parts) if safe_parts else ""


def _is_physics_component(component):
    """Physics usa a armature base e jamais deve determinar a skin do mod."""
    text = " ".join([
        str(component.get("name", "")),
        *(str(entry.get("name", "")) for entry in component.get("files", [])),
        *(str(path) for path in component.get("asset_paths", [])),
    ]).casefold()
    return any(marker in text for marker in (
        "physics", "_phys", "jiggle", "animblueprint", "anim_blueprint",
        "skeleton_animblueprint", "skeletonanimblueprint",
    ))


def _is_texture_component(component):
    """Texturas são acompanhamentos visuais e ficam após o componente principal."""
    text = " ".join([
        str(component.get("name", "")),
        *(str(entry.get("name", "")) for entry in component.get("files", [])),
    ]).casefold()
    return any(marker in text for marker in ("texture", "textures", "textura", "texturas", "_diffuse", "_normal", "_roughness", "_mask")) or any(
        pathlib.PureWindowsPath(str(entry.get("name", ""))).name.casefold().startswith("t_")
        for entry in component.get("files", [])
    )


def _is_ui_component(component):
    """UI é acompanhamento; evita falsos positivos como ``Suit``."""
    text = " ".join([
        str(component.get("name", "")),
        *(str(entry.get("name", "")) for entry in component.get("files", [])),
        *(str(path) for path in component.get("asset_paths", [])),
    ]).replace("\\", "/").casefold()
    return bool(re.search(r"(?:^|[/_\s-])ui(?:$|[/_\s-])", text)) or any(
        marker in text for marker in ("/interface/", "/widgets/", "/hud/", "nameplate", "spray")
    )


def _is_mesh_asset_path(path):
    path = str(path).split(" [", 1)[0].replace("\\", "/").casefold()
    name = path.rsplit("/", 1)[-1]
    if any(marker in name for marker in ("skeleton", "animblueprint", "anim_blueprint", "physics", "_phys")):
        return False
    return name.startswith(("sk_", "sm_")) or "/meshes/" in path


def _is_mesh_component(component):
    return any(_is_mesh_asset_path(path) for path in component.get("asset_paths", []))


def _ordered_component_types(types):
    order = ("Mesh", "Texture", "UI", "Physics", "Audio", "Blueprint", "VFX", "Unknown")
    unique = list(dict.fromkeys(str(value) for value in types if value))
    return sorted(unique, key=lambda value: (order.index(value) if value in order else len(order), value)) or ["Unknown"]


def _classify_component(component, mod_types=None):
    """Classifica um componente sem reler o contêiner no disco."""
    paths = list(component.get("asset_paths", []))
    file_names = [str(entry.get("name", "")) if isinstance(entry, dict) else str(entry)
                  for entry in component.get("files", [])]
    detected = _detect_types_from_asset_paths(paths, file_names, component.get("name", ""))
    saved = component.get("types") or ([component.get("type")] if component.get("type") else [])
    types = [value for value in [*detected, *saved] if value and value != "Unknown"]
    is_mesh = _is_mesh_component(component)
    is_physics = _is_physics_component(component)
    is_texture = _is_texture_component(component)
    is_ui = _is_ui_component(component)
    if is_physics:
        types = [value for value in types if value != "Blueprint"]
        if not is_mesh:
            types = [value for value in types if value != "Mesh"]
        types.append("Physics")
    if is_texture:
        if not is_mesh:
            types = [value for value in types if value != "Mesh"]
        types.append("Texture")
    if is_ui:
        if not is_mesh:
            types = [value for value in types if value != "Mesh"]
        types.append("UI")
    if is_mesh:
        types.append("Mesh")
    if not types and mod_types and not (is_physics or is_texture or is_ui):
        types = [value for value in mod_types if value != "Unknown"]
    return _ordered_component_types(types)


def _component_cached_asset_paths(mod, component):
    """Assets do componente; o cache agregado só serve para componente único."""
    cache = mod.get("asset_path_cache") or {}
    paths = component.get("asset_paths") or []
    if isinstance(cache, dict):
        for key in (f"classification-v1:{component.get('id')}",
                    f"component-files-v1:{component.get('id')}", f"component_{component.get('id')}",
                    f"conflict_component:{component.get('id')}"):
            entry = cache.get(key)
            if isinstance(entry, dict) and entry.get("paths"):
                paths = entry["paths"]
                break
    names = lambda entries: {str(entry.get("name", "")).replace("\\", "/").casefold()
                             for entry in entries if entry.get("name")}
    mod_files = names(mod.get("files", []))
    covers_mod = (len(mod.get("components", [])) == 1 and bool(mod_files)
                  and names(component.get("files", [])) == mod_files)
    if not paths and covers_mod and isinstance(cache, dict):
        entry = cache.get("all_files")
        if isinstance(entry, dict):
            paths = entry.get("paths") or []
    return paths, covers_mod


def _component_types_from_metadata(mod, component):
    """Reaproveita caches atuais/legados sem executar análise de contêineres."""
    paths, covers_mod = _component_cached_asset_paths(mod, component)
    classification_input = dict(component, asset_paths=paths)
    mod_types = mod.get("types") or [mod.get("type") or "Unknown"]
    inherited = mod_types if covers_mod else []
    types = _classify_component(classification_input, inherited)
    # Um único componente que cobre exatamente os arquivos do mod também
    # contém seus tipos confirmados, mesmo se o tipo salvo era só Physics.
    # Havendo paths, a evidência dos assets prevalece (Physics puro não vira Mesh).
    if covers_mod and not paths:
        types = _ordered_component_types([value for value in [*types, *mod_types]
                                          if value != "Unknown"])
    # Os bancos Wwise importados pelo fluxo de áudio de Background carregam
    # esta relação estrutural no catálogo. Ela é evidência mais forte que o
    # nome do PAK e evita exigir uma leitura Unreal que pode não expor o BNK.
    if mod.get("background_audio") and component.get("audio_bank"):
        types = _ordered_component_types([
            *[value for value in types if value != "Unknown"], "Audio"
        ])
    return types


_COMPONENT_ANALYSIS_RETRY = {}
_COMPONENT_ANALYSIS_LOCK = threading.Lock()


def _component_analysis_signature(files):
    # Independente da pasta ativa/storage: alternar um switch não exige scan.
    entries = []
    for path in files:
        try:
            stat = os.stat(path)
            entries.append((os.path.basename(path).casefold(), stat.st_size, stat.st_mtime_ns))
        except OSError:
            entries.append((os.path.basename(path).casefold(), None, None))
    return hashlib.sha256(repr(sorted(entries)).encode()).hexdigest()


def _component_analysis_pending(mod, component, files):
    if mod.get("install_target") in {"marvel_content", "binaries_win64"}:
        return False
    if not any(str(entry.get("name", "")).lower().endswith((".pak", ".utoc", ".ucas"))
               for entry in component.get("files", [])):
        return False
    signature = _component_analysis_signature(files)
    cached = (mod.get("asset_path_cache") or {}).get(f"classification-v1:{component.get('id')}", {})
    if cached.get("signature") == signature and cached.get("paths"):
        return False
    retry_key = (mod.get("id"), component.get("id"))
    previous_signature, attempted_at = _COMPONENT_ANALYSIS_RETRY.get(retry_key, (None, 0))
    return signature != previous_signature or time.monotonic() - attempted_at >= 60


def _update_mod_component_types(mod):
    types = _ordered_component_types(
        value for value in [*(mod.get("types") or [mod.get("type")]),
                            *(value for c in mod.get("components", []) for value in c.get("types", []))]
        if value and value != "Unknown"
    )
    mod["types"], mod["type"] = types, types[0]


def _analyze_mod_components(mod, source_files):
    """Analisa cada pacote uma vez, incluindo variações desativadas."""
    for component in mod.get("components", []):
        files = _component_source_files(mod, component, source_files)
        if not _component_analysis_pending(mod, component, files):
            continue
        key = f"classification-v1:{component['id']}"
        signature = _component_analysis_signature(files)
        paths = []
        if files and len(files) == len(component.get("files", [])):
            # Sem uma análise versionada, reaproveita a evidência legada.
            # Se o pacote mudou depois da análise, relê seus próprios assets.
            if key not in (mod.get("asset_path_cache") or {}):
                paths, _ = _component_cached_asset_paths(mod, component)
            if not paths:
                paths = _paths_from_bundle(files)
        if not paths:
            _COMPONENT_ANALYSIS_RETRY[(mod.get("id"), component.get("id"))] = (signature, time.monotonic())
            continue
        if signature != _component_analysis_signature(files):
            continue
        mod.setdefault("asset_path_cache", {})[key] = {"signature": signature, "paths": paths}
        # Os assets reais substituem classificações antigas/parciais.
        types = _classify_component(dict(component, asset_paths=paths, type=None, types=[]))
        component["types"], component["type"] = types, types[0]
    _update_mod_component_types(mod)


def classify_mod_components(mod_id):
    """Completa a análise sob demanda, sem mover arquivos nem alterar switches."""
    with _COMPONENT_ANALYSIS_LOCK:
        mod = next((item for item in storage.load_mods() if item.get("id") == mod_id), None)
        if not mod:
            return {"ok": False, "error": "Mod não encontrado."}
        if mod.get("install_target") in {"marvel_content", "binaries_win64"}:
            return {"ok": True, "changed": False}
        _analyze_mod_components(mod, _mod_source_files(mod))
        # A leitura pode demorar. Recarrega e aplica apenas tipos/cache aos
        # mesmos arquivos; preserva exclusões, nomes, ordem e switches recentes.
        mods = storage.load_mods()
        current = next((item for item in mods if item.get("id") == mod_id), None)
        if not current:
            return {"ok": True, "changed": False}
        sources = _mod_source_files(current)
        analyzed = {item["id"]: item for item in mod.get("components", [])}
        changed = False
        for component in current.get("components", []):
            result = analyzed.get(component.get("id"))
            key = f"classification-v1:{component.get('id')}"
            cached = (mod.get("asset_path_cache") or {}).get(key)
            if not result or not cached or result.get("files") != component.get("files"):
                continue
            files = _component_source_files(current, component, sources)
            if cached["signature"] != _component_analysis_signature(files):
                continue
            for field in ("type", "types"):
                if component.get(field) != result.get(field):
                    component[field] = result[field]
                    changed = True
            cache = current.setdefault("asset_path_cache", {})
            if cache.get(key) != cached:
                cache[key] = cached
                changed = True
        previous_types = (current.get("type"), current.get("types"))
        _update_mod_component_types(current)
        changed |= previous_types != (current.get("type"), current.get("types"))
        if changed:
            storage.save_mods(mods)
        return {"ok": True, "changed": changed}


def get_component_diagnosis(mod_id, component_id):
    mod = next((m for m in storage.load_mods() if m.get("id") == mod_id), None)
    component = next((c for c in (mod or {}).get("components", []) if c.get("id") == component_id), None)
    if not component:
        return {"ok": False, "error": "Componente não encontrado."}
    files = _component_source_files(mod, component, _mod_source_files(mod))
    paths, _ = _component_cached_asset_paths(mod, component)
    types = _component_types_from_metadata(mod, component)
    if len(files) != len(component.get("files", [])):
        status, message = "missing", "Há arquivos ausentes; restaure o pacote para concluir a análise."
    elif not paths:
        attempted = (mod_id, component_id) in _COMPONENT_ANALYSIS_RETRY
        status = "read_error" if attempted else "pending"
        message = ("A leitura não retornou assets. Verifique o pacote e a ferramenta de extração." if attempted
                   else "Este componente ainda não possui uma análise dos assets.")
    elif types == ["Unknown"]:
        status, message = "unrecognized", "Os assets foram lidos, mas não correspondem aos tipos reconhecidos."
    else:
        status, message = "analyzed", "Classificação baseada nos assets listados no pacote."
    evidence = []
    for type_name in types:
        matching = [path for path in paths if type_name in _detect_types_from_asset_paths([path], [], "")]
        structural_audio = (type_name == "Audio" and mod.get("background_audio")
                            and component.get("audio_bank"))
        source = ("assets" if matching else "metadados da importação" if structural_audio
                  else "nome ou classificação anterior")
        evidence.append({"type": type_name, "source": source,
                         "count": len(matching), "paths": matching[:8]})
    character, skin = _identity_from_asset_paths(paths)
    return {"ok": True, "status": status, "message": message, "types": types,
            "evidence": evidence, "asset_count": len(paths), "character": character, "skin": skin,
            "identity_override": mod.get("identity_override"), "component_name": component.get("name")}


def retry_component_analysis(mod_id, component_id):
    mods = storage.load_mods()
    mod = next((m for m in mods if m.get("id") == mod_id), None)
    component = next((c for c in (mod or {}).get("components", []) if c.get("id") == component_id), None)
    if not component:
        return {"ok": False, "error": "Componente não encontrado."}
    cache = mod.get("asset_path_cache") or {}
    for prefix in ("classification-v1:", "component-files-v1:", "component_", "conflict_component:"):
        cache.pop(prefix + component_id, None)
    if len(mod.get("components", [])) == 1:
        cache.pop("all_files", None)
    component.pop("asset_paths", None)
    storage.save_mods(mods)
    _COMPONENT_ANALYSIS_RETRY.pop((mod_id, component_id), None)
    return classify_mod_components(mod_id)


def _components_from_files(files, primary_name="", archive_components=False, labels_by_file=None):
    """Agrupa cada trio PAK/UCAS/UTOC pelo nome-base do pacote.

    Um pacote Physics é sempre um acompanhamento: fica no fim da lista e não
    recebe o estado principal em importações de arquivos compactados.
    """
    groups = {}
    labels_by_file = labels_by_file or {}
    for entry in files or []:
        name = entry.get("name", "")
        stem = os.path.splitext(name)[0]
        if stem:
            # Em ZIP/RAR, a mesma variação costuma morar em uma subpasta. O
            # rótulo calculado na importação preserva esse contexto na tela,
            # sem separar .pak/.ucas/.utoc que pertencem ao mesmo conjunto.
            label = labels_by_file.get(name) or stem
            groups.setdefault(label, []).append(entry)
    primary_stem = os.path.splitext(primary_name or "")[0].casefold()
    non_accompaniment_labels = [label for label, entries in groups.items()
                                if not _is_physics_component({"name": label, "files": entries})
                                and not _is_texture_component({"name": label, "files": entries})]
    primary_label = next((label for label in groups if os.path.splitext(label)[0].casefold() == primary_stem), "")
    if (not primary_label or _is_physics_component({"name": primary_label, "files": groups[primary_label]})
            or _is_texture_component({"name": primary_label, "files": groups[primary_label]})) and non_accompaniment_labels:
        primary_label = non_accompaniment_labels[0]
    ordered = sorted(groups.items(), key=lambda item: (
        2 if _is_physics_component({"name": item[0], "files": item[1]}) else
        1 if _is_texture_component({"name": item[0], "files": item[1]}) else 0,
        item[0].casefold() != primary_label.casefold(),
        item[0].casefold(),
    ))
    components = []
    for index, (label, entries) in enumerate(ordered):
        detected_types = _detect_types_from_asset_paths(
            [], [entry.get("name", "") for entry in entries], label
        )
        components.append({
            "id": storage.new_id(), "name": label, "files": entries,
            "type": detected_types[0], "types": detected_types,
            "enabled": not archive_components or index == 0,
        })
    return components


def _storage_relative(mod):
    """Caminho legível, mas com ID no final para manter unicidade."""
    if mod.get("storage_folder"):
        return mod["storage_folder"]
    return os.path.join(
        _safe_storage_segment(mod.get("character"), "Generic"),
        _safe_storage_segment(mod.get("skin"), "Default"),
        f"{_safe_storage_segment(mod.get('name'), 'Mod')} [{mod['id']}]",
    )


def _storage_dir(mod, create=False):
    path = os.path.join(storage.STORAGE_DIR, _storage_relative(mod))
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def _reshade_target_dir(mods_path):
    """Resolve ``Marvel\\Binaries\\Win64`` a partir do caminho configurado de ~mods."""
    current = pathlib.Path(mods_path).resolve()
    marvel_root = next((parent for parent in (current, *current.parents)
                        if parent.name.casefold() == "marvel"), None)
    target = (marvel_root / "Binaries" / "Win64") if marvel_root else None
    if not target or not target.is_dir():
        raise OSError("Não encontrei Marvel\\Binaries\\Win64 a partir da pasta ~mods configurada.")
    return str(target)


def _game_target_dir(mod, mods_path):
    if mod.get("install_target") == "binaries_win64":
        return _reshade_target_dir(mods_path)
    if mod.get("install_target") == "marvel_content":
        current = pathlib.Path(mods_path).resolve()
        marvel_root = next((parent for parent in (current, *current.parents)
                            if parent.name.casefold() == "marvel"), None)
        target = (marvel_root / "Content" / "Marvel") if marvel_root else None
        if not target or not target.is_dir():
            raise OSError("Não encontrei Marvel\\Content\\Marvel a partir da pasta ~mods configurada.")
        return str(target)
    return os.path.join(mods_path, _safe_game_folder(mod.get("folder", "")))


def _movies_backup_dir():
    return os.path.join(storage.BACKUPS_DIR, "original_moviesbink")


def _ensure_movies_backup(content_dir):
    source = os.path.join(content_dir, "MoviesBink")
    backup = _movies_backup_dir()
    if os.path.isdir(backup):
        return backup
    if not os.path.isdir(source):
        raise OSError("A pasta original MoviesBink não foi encontrada.")
    os.makedirs(os.path.dirname(backup), exist_ok=True)
    shutil.copytree(source, backup)
    return backup


def restore_cinematic_defaults():
    """Restaura a cópia original e desliga todos os backgrounds gerenciados."""
    mods = storage.load_mods()
    settings = storage.load_settings()
    backgrounds = [mod for mod in mods if mod.get("install_target") == "marvel_content"]
    if not backgrounds:
        return {"ok": True, "restored": False, "disabled": 0}
    content_dir = _game_target_dir(backgrounds[0], settings.get("mods_path", ""))
    backup = _movies_backup_dir()
    if not os.path.isdir(backup):
        return {"ok": False, "error": "Ainda não existe um backup original do MoviesBink."}
    _ensure_game_operation_allowed()
    active = os.path.join(content_dir, "MoviesBink")
    if os.path.isdir(active):
        shutil.rmtree(active)
    shutil.copytree(backup, active)
    disabled = 0
    for mod in backgrounds:
        if mod.get("enabled"):
            mod["enabled"] = False
            disabled += 1
    storage.save_mods(mods)
    _record_activity("restore_backgrounds", "Backgrounds restaurados ao padrão", {"disabled": disabled})
    return {"ok": True, "restored": True, "disabled": disabled}


def _rebuild_backgrounds(mods, mods_path):
    """Reaplica backgrounds ligados sobre o MoviesBink original, em ordem."""
    sample = next((mod for mod in mods if mod.get("install_target") == "marvel_content"), None)
    if not sample:
        return
    content_dir = _game_target_dir(sample, mods_path)
    backup = _movies_backup_dir()
    if not os.path.isdir(backup):
        raise OSError("Não existe um backup original do MoviesBink para reconstruir os Backgrounds.")
    _ensure_game_operation_allowed()
    active = os.path.join(content_dir, "MoviesBink")
    if os.path.isdir(active):
        shutil.rmtree(active)
    shutil.copytree(backup, active)
    for mod in mods:
        if mod.get("install_target") == "marvel_content" and mod.get("enabled"):
            _apply_enable(mod, mods_path, True)


def _refresh_background_files(mods, mods_path, file_names):
    """Atualiza só os arquivos afetados, respeitando a última camada ativa."""
    sample = next((mod for mod in mods if mod.get("install_target") == "marvel_content"), None)
    if not sample:
        return
    content_dir = _game_target_dir(sample, mods_path)
    backup = _ensure_movies_backup(content_dir)
    _ensure_game_operation_allowed()
    names = {_background_relative_file_path(name) for name in file_names if name}
    if not names:
        return
    winners = {}
    for background in mods:
        if background.get("install_target") != "marvel_content" or not background.get("enabled"):
            continue
        active_names = {
            entry.get("name") for component in background.get("components", [])
            if component.get("enabled", True)
            for entry in component.get("files", []) if entry.get("name")
        }
        for entry in background.get("files", []):
            name = entry.get("name")
            target_name = _background_relative_file_path(name)
            # Um Background com componentes, mas sem nenhum selecionado, é
            # apenas uma biblioteca de prévias: ele não pode vencer nenhum
            # arquivo ativo. Antes, a lista vazia caía no mesmo caso de um
            # mod sem componentes e reaplicava todos os seus BK2.
            if (target_name not in names
                    or (background.get("components") and name not in active_names)):
                continue
            source = os.path.join(_storage_dir(background), name)
            if os.path.isfile(source):
                winners[target_name] = source
    for name in names:
        destination = os.path.join(content_dir, name)
        source = winners.get(name) or os.path.join(backup, name)
        if os.path.isfile(source):
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            _install_file_fast(source, destination)
        elif os.path.isfile(destination):
            os.remove(destination)


def _disable_background_conflicts(mods, source_mod_id, file_names):
    """Desliga versões concorrentes do mesmo BK2 em outros Backgrounds ativos.

    Manter duas versões ativas deixava o resultado depender da ordem em que
    os complementos foram importados. A seleção mais recente passa a ser a
    única versão ativa daquele arquivo, sem desligar o complemento inteiro.
    """
    target_names = {_background_relative_file_path(name) for name in file_names if name}
    if not target_names:
        return []
    disabled = []
    for background in mods:
        if (background.get("install_target") != "marvel_content"
                or not background.get("enabled")
                or background.get("id") == source_mod_id):
            continue
        for component in background.get("components", []):
            if not component.get("enabled", True):
                continue
            component_names = {
                _background_relative_file_path(entry.get("name"))
                for entry in component.get("files", []) if entry.get("name")
            }
            if component_names.intersection(target_names):
                component["enabled"] = False
                disabled.append({"mod_id": background.get("id"), "component_id": component.get("id")})
    return disabled


def _safe_relative_file_path(value):
    path = pathlib.PureWindowsPath(str(value or ""))
    if not path.parts or path.is_absolute() or ".." in path.parts:
        raise ValueError("O arquivo do ReShade possui um caminho inválido.")
    return os.path.join(*path.parts)


def _background_relative_file_path(value):
    """Mantém ``MoviesBink`` como raiz, ignorando pastas extras do ZIP."""
    relative = _safe_relative_file_path(value)
    parts = pathlib.PureWindowsPath(relative).parts
    for index, part in enumerate(parts):
        if part.casefold() == "moviesbink":
            return os.path.join(*parts[index:])
    return relative


def _normalize_background_layout(mod):
    """Migra um Background legado que guardou uma pasta extra antes de MoviesBink."""
    if mod.get("install_target") != "marvel_content":
        return set()
    storage_dir = _storage_dir(mod)
    renamed = {}
    affected = set()
    for entry in mod.get("files", []):
        old_name = str(entry.get("name") or "")
        if not old_name:
            continue
        new_name = _background_relative_file_path(old_name)
        if new_name == old_name:
            continue
        source = os.path.join(storage_dir, old_name)
        destination = os.path.join(storage_dir, new_name)
        if os.path.isfile(source) and not os.path.isfile(destination):
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.move(source, destination)
        entry["name"] = new_name
        renamed[old_name] = new_name
        affected.add(new_name)
    if renamed:
        for component in mod.get("components", []):
            for entry in component.get("files", []):
                old_name = str(entry.get("name") or "")
                if old_name in renamed:
                    entry["name"] = renamed[old_name]
    return affected


LOCATION_TAGS = {
    "5001": "Hydra Charteris", "5002": "Asgard", "5003": "Tokyo 2099",
    "5004": "Wakanda", "5005": "Klyntar", "5006": "New York", "5007": "Kunlun",
    "5008": "Hellfire Gala", "5015": "Garden", "5016": "Museum",
    "5017": "S7 Downtown", "5020": "Times Square",
}


def _cinematic_metadata(name):
    parts = pathlib.PureWindowsPath(name).parts
    lowered = [part.casefold() for part in parts]
    tag = next((part for part in parts if part in LOCATION_TAGS), "")
    stem = pathlib.PureWindowsPath(name).stem.replace("_", " ")
    title_lower = stem.casefold()
    if "loginandlobby" in lowered:
        category = "Login e Lobby"
        short_category = "Lobby"
        index = lowered.index("loginandlobby")
        group = parts[index + 1] if len(parts) > index + 1 else "Outros"
        location = re.sub(r"^s(\d+)$", r"Season \1", group, flags=re.IGNORECASE)
        if "loginloop" in title_lower:
            purpose = "Tela de login"
        elif "transition" in title_lower:
            purpose = "Transição: login → início"
        elif "lobbyloop" in title_lower:
            purpose = "Tela de início"
        else:
            purpose = "Tela de login ou lobby"
    elif "levelvideo" in lowered:
        category = "Vídeos dos telões"
        short_category = "Telões"
        location = LOCATION_TAGS.get(tag, "Outros")
        purpose = "Vídeo exibido nos telões da Times Square"
    elif "levelentrance" in lowered:
        category = "Entrada da partida"
        short_category = "Entrada"
        location = LOCATION_TAGS.get(tag, "Outros")
        if "attack" in title_lower:
            purpose = "Entrada da partida · equipe de ataque"
        elif "defence" in title_lower or "defense" in title_lower:
            purpose = "Entrada da partida · equipe de defesa"
        else:
            purpose = "Cinematic de entrada da partida"
    elif "levelexit" in lowered:
        category = "Fim da partida"
        short_category = "Fim"
        location = LOCATION_TAGS.get(tag, "Outros")
        if "attack" in title_lower:
            purpose = "Fim da partida, antes do MVP · ataque"
        elif "defence" in title_lower or "defense" in title_lower:
            purpose = "Fim da partida, antes do MVP · defesa"
        else:
            purpose = "Cinematic antes do MVP, ao fim da partida"
    elif "loading" in lowered:
        category = "Carregamento da partida"
        short_category = "Carregamento"
        location = LOCATION_TAGS.get(tag, "Outros")
        purpose = "Carregamento após selecionar o personagem"
    elif "league" in lowered:
        category = "Esportes"
        short_category = "Esportes"
        index = lowered.index("league")
        location = parts[index + 1] if len(parts) > index + 1 else "Esportes"
        purpose = "Vídeo exibido na área Esportes"
    else:
        category = "Inicialização do jogo"
        short_category = "Abertura"
        location = "Abertura"
        purpose = "Logo, aviso ou tela exibida ao iniciar o jogo"
    return {"tag": tag, "location": location,
            "category": category, "short_category": short_category,
            "purpose": purpose, "title": stem}


def _background_components(files):
    return [
        {"id": storage.new_id(), "name": _cinematic_metadata(entry["name"])["title"],
         "files": [entry], "enabled": True, **_cinematic_metadata(entry["name"])}
        for entry in files if str(entry.get("name", "")).lower().endswith(".bk2")
    ] or [{"id": storage.new_id(), "name": "Principal", "files": files, "enabled": True}]


_BACKGROUND_AUDIO_LOCATIONS = {
    "arakko": "Hellfire Gala", "asgard": "Asgard", "hydra": "Hydra Charteris",
    "klyntar": "Klyntar", "krakoa": "Hellfire Gala", "kunlun": "Kunlun",
    "museum": "Museum", "newyork": "New York", "thebes": "Times Square",
    "tokyo": "Tokyo 2099", "wakanda": "Wakanda", "garden": "Garden",
}

_BACKGROUND_AUDIO_QUEUE_LOCK = threading.Lock()
_BACKGROUND_AUDIO_QUEUE_THREAD = None


def _background_audio_metadata(bank_name):
    """Converte o nome do banco Wwise no contexto que o usuário reconhece."""
    stem = pathlib.PureWindowsPath(bank_name).stem.casefold()
    compact = re.sub(r"[^a-z0-9]", "", stem).removeprefix("bnkcutscene")
    location = next((label for key, label in _BACKGROUND_AUDIO_LOCATIONS.items() if compact.startswith(key) or key in compact), "Outros")
    if "garden" in compact:
        location = "Garden"
    variant_match = re.search(r"(?:e|h|m|c)\d{0,2}$", compact)
    variant = variant_match.group(0).upper() if variant_match else ""
    if stem.startswith("bnk_cutscene_"):
        title = f"{location}{' · ' + variant if variant else ''}"
        return {"location": location, "variant": variant, "purpose": f"Áudio da cinematic de {title}", "title": title}
    if stem == "bnk_ui_interface":
        return {"location": "Interface", "variant": "", "purpose": "Efeitos sonoros da interface", "title": "Interface"}
    if stem == "music_formal":
        return {"location": "Lobby", "variant": "", "purpose": "Música de fundo do lobby", "title": "Música do lobby"}
    return {"location": location, "variant": variant, "purpose": "Banco de áudio", "title": pathlib.PureWindowsPath(bank_name).stem}


def _find_vgmstream_cli():
    """Prefere o decoder incluído no Manager, sem depender do PATH."""
    candidates = [
        os.path.join(storage.RESOURCE_DIR, "tools", "vgmstream", "vgmstream-cli.exe"),
        shutil.which("vgmstream-cli.exe"),
    ]
    return next((path for path in candidates if path and os.path.isfile(path)), None)


def _find_bink_player():
    """Prefere o Bink Player oficial incluído, com PATH como compatibilidade."""
    candidates = [
        os.path.join(storage.RESOURCE_DIR, "tools", "rad", "binkplay.exe"),
        shutil.which("binkplay.exe"),
    ]
    return next((path for path in candidates if path and os.path.isfile(path)), None)


def _sync_storage_location(mod):
    """Move o backup privado quando personagem/skin corrigidos mudam."""
    current = _storage_dir(mod)
    desired_relative = os.path.join(
        _safe_storage_segment(mod.get("character"), "Generic"),
        _safe_storage_segment(mod.get("skin"), "Default"),
        f"{_safe_storage_segment(mod.get('name'), 'Mod')} [{mod['id']}]",
    )
    desired = os.path.join(storage.STORAGE_DIR, desired_relative)
    if os.path.normcase(os.path.normpath(current)) == os.path.normcase(os.path.normpath(desired)):
        return False
    if os.path.isdir(current) and not os.path.exists(desired):
        os.makedirs(os.path.dirname(desired), exist_ok=True)
        shutil.move(current, desired)
        mod["storage_folder"] = desired_relative
        return True
    return False


def _image_data_url(path):
    """Retorna a imagem em data URL para o WebView poder renderizá-la.

    O WebView2 pode bloquear imagens ``file://`` que ficam fora da pasta do
    frontend. As capas ficam no armazenamento privado de cada mod, portanto
    elas precisam ser entregues desta forma.
    """
    if not path or not os.path.isfile(path):
        return None
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if not mime.startswith("image/"):
        return None
    with open(path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _cached_thumbnail_url(path):
    """Lê uma miniatura pronta uma única vez por versão do arquivo."""
    if not path or not os.path.isfile(path):
        return None
    try:
        stat = os.stat(path)
        cache_key = (os.path.normcase(os.path.abspath(path)), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return _image_data_url(path)
    cached = _THUMBNAIL_URL_CACHE.get(cache_key)
    if cached is not None:
        return cached
    data_url = _image_data_url(path)
    if data_url:
        if len(_THUMBNAIL_URL_CACHE) >= _THUMBNAIL_URL_CACHE_LIMIT:
            _THUMBNAIL_URL_CACHE.clear()
        _THUMBNAIL_URL_CACHE[cache_key] = data_url
    return data_url


def _media_data_url(path):
    """Retorna imagens ou vídeos da galeria em data URL para o WebView."""
    if not path or not os.path.isfile(path):
        return None
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if not (mime.startswith("image/") or mime.startswith("video/")):
        return None
    with open(path, "rb") as media_file:
        encoded = base64.b64encode(media_file.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _thumbnail_key(path):
    """Revisão da mídia sem ler seus bytes: caminho, alteração e tamanho."""
    if not path:
        return None
    try:
        file_stat = os.stat(path)
        if not stat_module.S_ISREG(file_stat.st_mode):
            return None
    except OSError:
        return None
    revision = f"{os.path.abspath(path)}:{file_stat.st_mtime_ns}:{file_stat.st_size}".encode("utf-8")
    return hashlib.sha1(revision).hexdigest()


def _thumbnail_data_url(path, *, fallback_original=True):
    """Miniatura persistente para os cards; evita enviar fotos enormes ao WebView."""
    if not path or not os.path.isfile(path):
        return None
    if Image is None:
        return _image_data_url(path) if fallback_original else None
    try:
        cache_key = _thumbnail_key(path)
        if cache_key is None:
            return _image_data_url(path) if fallback_original else None
        cache_dir = os.path.join(storage.STORAGE_DIR, ".thumbnails")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, cache_key + ".jpg")
        if os.path.isfile(cache_path):
            return _cached_thumbnail_url(cache_path)
        with Image.open(path) as image:
            image.thumbnail((480, 320), Image.Resampling.LANCZOS)
            if image.mode not in ("RGB", "L"):
                background = Image.new("RGB", image.size, "#17171a")
                background.paste(image, mask=image.getchannel("A") if "A" in image.getbands() else None)
                image = background
            elif image.mode == "L":
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=78, optimize=True)
        with open(cache_path, "wb") as thumbnail:
            thumbnail.write(buffer.getvalue())
        data_url = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
        cache_stat = os.stat(cache_path)
        _THUMBNAIL_URL_CACHE[(os.path.normcase(os.path.abspath(cache_path)), cache_stat.st_mtime_ns, cache_stat.st_size)] = data_url
        return data_url
    except Exception:
        return _image_data_url(path) if fallback_original else None


# ---------------------------------------------------------------------------
# Leitura basica
# ---------------------------------------------------------------------------
def _resolved_skin_name(skin, character=""):
    """Exibe skins antigas ``Skin ID 123`` pelo nome já conhecido no catálogo."""
    raw = str(skin or "").strip()
    match = re.fullmatch(r"skin\s*id\s*(\d+)", raw, re.IGNORECASE)
    if match:
        identified = SKIN_BY_ID.get(match.group(1))
        if identified and (not character or identified[0] == character):
            return canonical_skin_name(identified[1], identified[0])
    return canonical_skin_name(raw, character)


def list_mods(include_gallery=False, only_mod_id=None, include_thumbnails=True, *, _mods=None,
              _include_asset_cache=True):
    catalog = storage.load_mods() if _mods is None else _mods
    # Apresentação não altera a visão de persistência nem as contagens.
    mods = [dict(mod) for mod in catalog if not only_mod_id or mod.get("id") == only_mod_id]
    addon_sizes = {}
    for item in catalog:
        parent_id = item.get("parent_background_id")
        if parent_id:
            addon_sizes[parent_id] = addon_sizes.get(parent_id, 0) + float(item.get("size_mb", 0) or 0)
    hero_icons = {}
    for m in mods:
        if not _include_asset_cache:
            m.pop("asset_path_cache", None)
        m.setdefault("priority", 1)
        m["catalog_size_mb"] = round(float(m.get("size_mb", 0) or 0) + addon_sizes.get(m.get("id"), 0), 2)
        m.setdefault("skin", "")
        m["skin"] = _resolved_skin_name(m["skin"], m.get("character"))
        m["skin_icon_url"] = _SKIN_ICON_BY_CHARACTER_AND_NAME.get(
            (m.get("character"), m.get("skin"))
        )
        mod_types = m.get("types") or [m.get("type") or "Unknown"]
        component_types = [
            component_type
            for component in m.get("components", [])
            for component_type in (component.get("types") or [component.get("type") or "Unknown"])
            if component_type and component_type != "Unknown"
        ]
        m["types"] = list(dict.fromkeys([*mod_types, *component_types]))
        if m.get("install_target") == "marvel_content":
            locations = {component.get("location") for component in m.get("components", [])
                         if component.get("location") and component.get("location") != "Outros"}
            if not locations:
                locations = {_cinematic_metadata(entry.get("name", ""))["location"] for entry in m.get("files", [])
                             if _cinematic_metadata(entry.get("name", ""))["location"] != "Outros"}
            m["background_locations"] = sorted(locations)
        # ``images`` suporta galerias; ``image`` é mantido para mods criados
        # nas versões anteriores e continua sendo a capa principal.
        image_names = m.get("images") or ([m["image"]] if m.get("image") else [])
        image_titles = m.get("image_titles") or {}
        cover_name = m.get("image") or (image_names[0] if image_names else None)
        cover_path = os.path.join(_storage_dir(m), cover_name) if cover_name else ""
        m["thumbnail_key"] = _thumbnail_key(cover_path)
        # A tela principal não deve esperar a leitura/conversão de todas as
        # capas. Ela pede cada miniatura depois que a lista já foi desenhada.
        m["image_url"] = _thumbnail_data_url(cover_path) if include_thumbnails else None
        if include_gallery:
            # A página de detalhes recebe somente miniaturas. Uma galeria
            # grande pode ter mais de 100 MB de imagens e enviá-las todas
            # como data URL travava a interface antes mesmo do primeiro clique.
            gallery = []
            for name in image_names:
                media_path = os.path.join(_storage_dir(m), name)
                if not os.path.isfile(media_path):
                    continue
                is_video = os.path.splitext(name)[1].lower() in {".mp4", ".webm", ".ogv", ".mov"}
                gallery.append({
                    "name": name,
                    "url": None,
                    "preview_url": _thumbnail_data_url(media_path) if include_thumbnails and not is_video else None,
                    "thumbnail_key": _thumbnail_key(media_path),
                    "title": image_titles.get(name, ""),
                    "media_type": "video" if is_video else "image",
                })
            m["gallery_images"] = gallery
        else:
            m["gallery_images"] = []
        m["image_urls"] = [m["image_url"]] if m["image_url"] else []
        # Caminho relativo: o WebView carrega index.html de frontend/ e bloqueia
        # file:// absolutos em algumas instalações do Windows.
        character = m.get("character")
        if character not in hero_icons:
            hero_icons[character] = _hero_icon_url(character)
        m["hero_icon_url"] = hero_icons[character]
    return mods


def get_library_snapshot():
    """Uma leitura do catálogo para a home, sem cache de assets nem miniaturas.

    O detalhe continua usando list_mods com galeria e cache completos. Capas
    permanecem sob demanda por get_mod_thumbnail após desenhar os cards.
    """
    mods = storage.load_mods()
    settings = storage.load_settings()
    return {
        "mods": list_mods(include_thumbnails=False, _mods=mods, _include_asset_cache=False),
        "characters": get_characters(_mods=mods),
        "types": get_types(_mods=mods),
        "tags": get_tags(_mods=mods, _settings=settings),
        "folders": get_folders(_mods=mods, _settings=settings),
    }


def get_mod_thumbnail(mod_id):
    """Retorna somente a miniatura da capa solicitada por um card visível."""
    mod = next((item for item in storage.load_mods() if item.get("id") == mod_id), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}
    image_names = mod.get("images") or ([mod["image"]] if mod.get("image") else [])
    cover_name = mod.get("image") or (image_names[0] if image_names else None)
    if not cover_name:
        return {"ok": True, "image_url": None, "thumbnail_key": None}
    cover_path = os.path.join(_storage_dir(mod), cover_name)
    thumbnail_key = _thumbnail_key(cover_path)
    image_url = _thumbnail_data_url(cover_path)
    if _thumbnail_key(cover_path) != thumbnail_key:
        return {"ok": False, "error": "A capa mudou durante o carregamento. Tente novamente."}
    return {"ok": True, "image_url": image_url, "thumbnail_key": thumbnail_key}


def get_gallery_preview(mod_id, media_name):
    """Entrega só a miniatura solicitada; abrir o detalhe não decodifica imagens."""
    if not isinstance(media_name, str) or not media_name or os.path.basename(media_name) != media_name:
        return {"ok": False, "error": "Mídia inválida."}
    mod = next((item for item in storage.load_mods() if item.get("id") == mod_id), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}
    images = mod.get("images") or ([mod["image"]] if mod.get("image") else [])
    if media_name not in images:
        return {"ok": False, "error": "Mídia não pertence a este mod."}
    path = os.path.join(_storage_dir(mod), media_name)
    thumbnail_key = _thumbnail_key(path)
    if thumbnail_key is None:
        return {"ok": False, "error": "Arquivo de mídia não encontrado."}
    if os.path.splitext(media_name)[1].lower() in {".mp4", ".webm", ".ogv", ".mov"}:
        return {"ok": True, "preview_url": None, "thumbnail_key": thumbnail_key}
    preview_url = _thumbnail_data_url(path, fallback_original=False)
    if _thumbnail_key(path) != thumbnail_key:
        return {"ok": False, "error": "A mídia mudou durante o carregamento. Tente novamente."}
    if not preview_url:
        return {"ok": False, "error": "Não foi possível gerar a miniatura desta imagem."}
    return {"ok": True, "preview_url": preview_url, "thumbnail_key": thumbnail_key}


def get_gallery_media(mod_id, media_name):
    """Entrega a mídia original apenas quando o usuário pede para ampliá-la."""
    if not media_name or os.path.basename(media_name) != media_name:
        return {"ok": False, "error": "Mídia inválida."}
    mod = next((item for item in storage.load_mods() if item.get("id") == mod_id), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}
    images = mod.get("images") or ([mod["image"]] if mod.get("image") else [])
    if media_name not in images:
        return {"ok": False, "error": "Mídia não pertence a este mod."}
    path = os.path.join(_storage_dir(mod), media_name)
    url = _media_data_url(path)
    if not url:
        return {"ok": False, "error": "Arquivo de mídia não encontrado."}
    return {"ok": True, "url": url}


def get_characters(*, _mods=None):
    """Roster completo no filtro, inclusive heróis ainda sem mods."""
    mods = storage.load_mods() if _mods is None else _mods
    counts = {}
    for m in mods:
        if m.get("parent_background_id"):
            continue
        c = m.get("character") or "Generic"
        counts[c] = counts.get(c, 0) + 1
    # Backgrounds é uma área funcional do Manager, não um herói inferido.
    # Mantê-la sempre na barra permite filtrar e receber novos Backgrounds
    # mesmo antes do primeiro arquivo ser importado.
    names = [*MARVEL_CHARACTERS, "Backgrounds"]
    if counts.get("Generic"):
        names.append("Generic")
    roster = []
    for name in names:
        roster.append({
            "name": name,
            "count": counts.get(name, 0),
            # Mantém a mesma fonte de ícones usada nos cards e nos detalhes.
            "hero_icon_url": _hero_icon_url(name),
        })
    return roster


def get_character_roster():
    """Lista completa de herois do jogo, pro seletor do Add Mod (nao depende de ja ter mod)."""
    return MARVEL_CHARACTERS


def get_skins_for_character(character):
    """Skins ja usadas nos SEUS mods pra esse personagem (cresce organicamente, nada hardcoded)."""
    mods = storage.load_mods()
    skins = sorted({_resolved_skin_name(m.get("skin"), character) for m in mods
                    if m.get("character") == character and m.get("skin")})
    return skins


def get_character_skins(character):
    """Todas as skins conhecidas de um herói, com o total instalado."""
    mods = storage.load_mods()
    if character == "Backgrounds":
        counts = {}
        for mod in mods:
            if mod.get("install_target") != "marvel_content":
                continue
            sources = mod.get("components", []) or [{"files": mod.get("files", [])}]
            for component in sources:
                locations = {component.get("location")} if component.get("location") else {
                    _cinematic_metadata(entry.get("name", ""))["location"] for entry in component.get("files", [])
                }
                for location in locations:
                    if location and location != "Outros":
                        counts[location] = counts.get(location, 0) + 1
        return [{"name": name, "count": count, "skin_icon_url": None}
                for name, count in sorted(counts.items())]
    counts = {}
    for mod in mods:
        if mod.get("character") == character:
            skin = _resolved_skin_name(mod.get("skin"), character) or "Default"
            counts[skin] = counts.get(skin, 0) + 1
    known = {
        canonical_skin_name(skin, character) for hero, skin in SKIN_BY_ID.values()
        if hero == character and "placeholder" not in skin.casefold()
    }
    known.add("Default")
    known.update(skin for skin in counts if "placeholder" not in skin.casefold())
    skin_icons = {}
    for skin_id, (hero, skin) in SKIN_BY_ID.items():
        display_skin = canonical_skin_name(skin, character)
        if hero == character and display_skin not in skin_icons and SKIN_ICON_BY_ID.get(skin_id):
            skin_icons[display_skin] = SKIN_ICON_BY_ID[skin_id]
    return [{"name": skin, "count": counts.get(skin, 0), "skin_icon_url": skin_icons.get(skin)}
            for skin in sorted(known, key=lambda item: (item != "Default", item.casefold()))]


def get_types(*, _mods=None):
    mods = storage.load_mods() if _mods is None else _mods
    return sorted({type_name for m in mods
                   for type_name in (m.get("types") or [m.get("type") or "Unknown"])})


def get_tags(*, _mods=None, _settings=None):
    """Tags cadastradas, inclusive as novas ainda sem nenhum mod atribuído."""
    counts = {}
    mods = storage.load_mods() if _mods is None else _mods
    for mod in mods:
        for tag in mod.get("tags", []):
            counts[tag] = counts.get(tag, 0) + 1
    settings = storage.load_settings() if _settings is None else _settings
    saved_tags = settings.get("tag_catalog", [])
    for tag in saved_tags:
        if isinstance(tag, str) and tag.strip():
            counts.setdefault(tag.strip(), 0)
    return [{"name": name, "count": count} for name, count in
            sorted(counts.items(), key=lambda item: item[0].lower())]


def create_tag(tag):
    """Cria uma tag reutilizável, mesmo antes de atribuí-la a algum mod."""
    tag = (tag or "").strip()
    if not tag:
        return {"ok": False, "error": "Informe um nome para a tag."}
    if len(tag) > 48:
        return {"ok": False, "error": "A tag pode ter no máximo 48 caracteres."}
    settings = storage.load_settings()
    catalog = [item for item in settings.get("tag_catalog", []) if isinstance(item, str) and item.strip()]
    known = {item.casefold() for item in catalog}
    known.update(item["name"].casefold() for item in get_tags())
    if tag.casefold() not in known:
        catalog.append(tag)
        settings["tag_catalog"] = catalog
        storage.save_settings(settings)
    return {"ok": True, "tag": tag, "tags": get_tags()}


def get_component_labels():
    """Catálogo separado de rótulos para componentes/acompanhamentos."""
    labels = {"Principal", "Acompanhamento"}
    labels.update(
        item.strip() for item in storage.load_settings().get("component_label_catalog", [])
        if isinstance(item, str) and item.strip()
    )
    for mod in storage.load_mods():
        for component in mod.get("components", []):
            label = component.get("description")
            if isinstance(label, str) and label.strip():
                labels.add(label.strip())
    return sorted(labels, key=str.casefold)


def create_component_label(label):
    """Cria um rótulo reutilizável sem afetar o catálogo de tags dos mods."""
    label = (label or "").strip()
    if not label:
        return {"ok": False, "error": "Informe um nome para o rótulo."}
    if len(label) > 80:
        return {"ok": False, "error": "O rótulo pode ter no máximo 80 caracteres."}
    settings = storage.load_settings()
    catalog = [item for item in settings.get("component_label_catalog", [])
               if isinstance(item, str) and item.strip()]
    if label.casefold() not in {item.casefold() for item in get_component_labels()}:
        catalog.append(label)
        settings["component_label_catalog"] = catalog
        storage.save_settings(settings)
    return {"ok": True, "label": label, "labels": get_component_labels()}


def delete_component_label(label):
    """Remove um rótulo personalizado do catálogo e dos componentes.

    ``Principal`` e ``Acompanhamento`` são os estados automáticos do Manager,
    por isso não podem ser excluídos do catálogo.
    """
    label = (label or "").strip()
    if not label:
        return {"ok": False, "error": "Informe um rótulo válido."}
    if label.casefold() in {"principal", "acompanhamento"}:
        return {"ok": False, "error": "Os rótulos automáticos não podem ser removidos."}
    settings = storage.load_settings()
    settings["component_label_catalog"] = [item for item in settings.get("component_label_catalog", [])
                                           if not isinstance(item, str) or item.casefold() != label.casefold()]
    mods = storage.load_mods()
    for mod in mods:
        for component in mod.get("components", []):
            if str(component.get("description") or "").casefold() == label.casefold():
                component.pop("description", None)
    storage.save_settings(settings)
    storage.save_mods(mods)
    return {"ok": True, "labels": get_component_labels()}


def get_settings():
    return storage.load_settings()


def get_character_catalog_status():
    return character_catalog.get_status(characters._DATA_PATH)


def update_character_catalog(force=True):
    """Atualiza IDs externos e os torna disponíveis na sessão atual."""
    result = character_catalog.check_for_update(characters._DATA_PATH, force=bool(force))
    if result.get("ok") and result.get("checked"):
        characters.refresh_character_data()
        _refresh_identity_indexes()
        result["total"] = len(characters.CHARACTER_DATA)
    return result


def export_library_backup(destination):
    """Exporta catálogo e configurações sem copiar os arquivos grandes."""
    destination = str(destination or "").strip()
    if not destination:
        return {"ok": False, "error": "Escolha onde salvar o backup."}
    if not destination.lower().endswith(".json"):
        destination += ".json"

    payload = {
        "format": "marvel-manager-library-backup",
        "format_version": 1,
        "exported_at": storage.now_iso(),
        "mods": storage.load_mods(),
        "settings": storage.load_settings(),
    }
    try:
        with open(destination, "w", encoding="utf-8") as backup_file:
            json.dump(payload, backup_file, indent=2, ensure_ascii=False)
    except OSError as exc:
        return {"ok": False, "error": f"Não foi possível salvar o backup: {exc}"}

    _record_activity("library_backup_export", "Backup da biblioteca exportado", {"path": destination})
    return {"ok": True, "path": destination, "mods": len(payload["mods"])}


def export_library_backup_to_default_directory():
    """Cria um backup sequencial na pasta backups da instalação do Manager."""
    storage.ensure_dirs()
    index = 1
    while True:
        destination = os.path.join(storage.BACKUPS_DIR, f"marvel-manager-backup{index}.json")
        if not os.path.exists(destination):
            return export_library_backup(destination)
        index += 1


def restore_library_backup(source):
    """Restaura os registros da biblioteca sem tocar nos arquivos dos mods."""
    source = str(source or "").strip()
    if not source or not os.path.isfile(source):
        return {"ok": False, "error": "Arquivo de backup não encontrado."}
    try:
        with open(source, "r", encoding="utf-8") as backup_file:
            payload = json.load(backup_file)
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": f"Não foi possível ler o backup: {exc}"}

    if not isinstance(payload, dict) or payload.get("format") != "marvel-manager-library-backup":
        return {"ok": False, "error": "Este arquivo não é um backup do CrabVault."}
    if not isinstance(payload.get("mods"), list) or not isinstance(payload.get("settings"), dict):
        return {"ok": False, "error": "O backup está incompleto ou corrompido."}

    storage.save_mods(payload["mods"])
    storage.save_settings(payload["settings"])
    _record_activity(
        "library_backup_restore",
        "Backup da biblioteca restaurado",
        {"path": source, "mods": len(payload["mods"])},
    )
    return {"ok": True, "mods": len(payload["mods"]), "exported_at": payload.get("exported_at", "")}


def _expected_active_file_names(mod):
    """Nomes que devem estar instalados para o estado atual do mod."""
    files = [entry for entry in mod.get("files", [])
             if isinstance(entry, dict) and entry.get("name")]
    enabled_components = [component for component in mod.get("components", [])
                          if component.get("enabled", True)]
    if not mod.get("components"):
        return {entry["name"] for entry in files}
    names = {
        entry.get("name") for component in enabled_components
        for entry in component.get("files", [])
        if isinstance(entry, dict) and entry.get("name")
    }
    return names


def inspect_library_integrity():
    """Diagnostica a biblioteca sem modificar arquivos nem registros.

    Confere os backups privados necessários para reativar o mod, os arquivos
    que deveriam estar presentes no jogo quando ele está ligado e as mídias
    registradas na galeria. Arquivos compactados não entram na verificação:
    eles são opcionais e podem não existir para importações avulsas.
    """
    mods = storage.load_mods()
    settings = storage.load_settings()
    mods_path = str(settings.get("mods_path") or "")
    issues = []

    for mod in mods:
        files = [entry for entry in mod.get("files", []) if isinstance(entry, dict) and entry.get("name")]
        storage_dir = _storage_dir(mod)
        missing_backup = []
        missing_active = []
        missing_media = []

        # Mods externos ainda podem não ter backup porque foram encontrados
        # diretamente no ~mods. Só apontamos isso se eles estiverem desligados,
        # caso em que não há de onde restaurá-los.
        if mod.get("external"):
            external_disabled = not mod.get("enabled", False)
        else:
            external_disabled = False
            for entry in files:
                name = entry["name"]
                if not os.path.isfile(os.path.join(storage_dir, name)):
                    missing_backup.append(name)

        if mod.get("enabled") and mods_path:
            expected_names = _expected_active_file_names(mod)
            active_dir = _game_target_dir(mod, mods_path)
            for name in expected_names:
                if not os.path.isfile(os.path.join(active_dir, name)):
                    missing_active.append(name)

        # Uma mídia pode ser substituída manualmente na galeria. Itens que o
        # usuário marcou como ignorados não voltam a gerar um alerta eterno.
        ignored_media = {str(name) for name in mod.get("ignored_missing_media", []) if name}
        media_names = mod.get("images") or ([mod["image"]] if mod.get("image") else [])
        for name in media_names:
            if name and name not in ignored_media and not os.path.isfile(os.path.join(storage_dir, name)):
                missing_media.append(name)

        if missing_backup or missing_active or missing_media or external_disabled:
            issues.append({
                "id": mod.get("id"),
                "name": mod.get("name") or "Mod sem nome",
                "missing_backup": missing_backup,
                "missing_active": missing_active,
                "missing_media": missing_media,
                "external_disabled": external_disabled,
            })

    _record_activity(
        "library_integrity",
        f"Verificação de integridade: {len(issues)} mod(s) com pendências",
        {"checked": len(mods), "issues": len(issues)},
    )
    return {
        "checked": len(mods),
        "issues": issues,
        "mods_path_configured": bool(mods_path),
    }


def repair_library_integrity(mod_id):
    """Tenta restaurar somente arquivos faltantes de um mod diagnosticado.

    Nunca sobrescreve arquivos existentes: a restauração cria o backup privado
    a partir da cópia ativa ou reinstala no jogo a partir do backup. Mídias
    faltantes e mods externos desligados continuam exigindo ação manual.
    """
    mods = storage.load_mods()
    settings = storage.load_settings()
    mod = next((item for item in mods if item.get("id") == mod_id), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}

    files = [entry for entry in mod.get("files", [])
             if isinstance(entry, dict) and entry.get("name")]
    storage_dir = _storage_dir(mod, create=True)
    mods_path = str(settings.get("mods_path") or "")
    active_dir = _game_target_dir(mod, mods_path) if mods_path else ""
    repaired_backup, repaired_active, unavailable = [], [], []

    # Um backup pode ser recriado da cópia ainda instalada, inclusive para
    # registros que antes eram considerados externos.
    for entry in files:
        name = entry["name"]
        backup_path = os.path.join(storage_dir, name)
        active_path = os.path.join(active_dir, name) if active_dir else ""
        if not os.path.isfile(backup_path) and active_path and os.path.isfile(active_path):
            try:
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                shutil.copy2(active_path, backup_path)
                repaired_backup.append(name)
            except OSError:
                unavailable.append(name)

    # Restaurar na pasta do jogo só faz sentido para um mod ligado e apenas
    # quando há backup local. Respeita o bloqueio de jogo em curso.
    if mod.get("enabled") and active_dir:
        expected_names = _expected_active_file_names(mod)
        pending_active = [name for name in expected_names
                          if not os.path.isfile(os.path.join(active_dir, name))
                          and os.path.isfile(os.path.join(storage_dir, name))]
        if pending_active:
            _ensure_game_operation_allowed()
            os.makedirs(active_dir, exist_ok=True)
            for name in pending_active:
                try:
                    destination = os.path.join(active_dir, name)
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    if _install_file_fast(os.path.join(storage_dir, name), destination):
                        repaired_active.append(name)
                except OSError:
                    unavailable.append(name)
        for name in expected_names:
            if not os.path.isfile(os.path.join(active_dir, name)) and name not in repaired_active:
                unavailable.append(name)

    if repaired_backup or repaired_active:
        _record_activity(
            "library_repair",
            f"Reparo de integridade: {mod.get('name') or 'Mod sem nome'}",
            {"mod_id": mod_id, "backup": len(repaired_backup), "active": len(repaired_active)},
        )
    return {
        "ok": True,
        "repaired_backup": repaired_backup,
        "repaired_active": repaired_active,
        "unavailable": sorted(set(unavailable)),
    }


def ignore_missing_media(mod_id, media_names):
    """Oculta mídias ausentes do diagnóstico sem tocar nos arquivos restantes."""
    if not isinstance(media_names, list):
        return {"ok": False, "error": "Lista de mídias inválida."}
    mods = storage.load_mods()
    mod = next((item for item in mods if item.get("id") == mod_id), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}

    known_media = {str(name) for name in mod.get("images", []) if name}
    if mod.get("image"):
        known_media.add(str(mod["image"]))
    requested = {str(name) for name in media_names if name}
    ignored = {str(name) for name in mod.get("ignored_missing_media", []) if name}
    ignored.update(requested & known_media)
    mod["ignored_missing_media"] = sorted(ignored, key=str.casefold)
    storage.save_mods(mods)
    _record_activity(
        "library_ignore_missing_media",
        f"Mídia ausente ignorada: {mod.get('name') or 'Mod sem nome'}",
        {"mod_id": mod_id, "media": sorted(requested & known_media)},
    )
    return {"ok": True, "ignored": sorted(requested & known_media)}


def set_mods_path(path):
    s = storage.load_settings()
    s["mods_path"] = path
    storage.save_settings(s)
    return s


def save_settings(values):
    """Salva apenas opções conhecidas, preservando configurações futuras."""
    settings = storage.load_settings()
    allowed = {"mods_path", "launcher", "show_subfolders", "compact_list",
               "auto_open_details", "accent_color", "require_hold_to_delete", "view_mode",
               "hide_file_suffix", "show_type_badge", "bypass_game_running_lock",
               "preserve_import_archives", "delete_import_sources_after_success",
               "theme_mode", "preview_volume", "fmodel_path", "ui_language",
               "language_selected", "tutorial_completed"}
    settings.update({k: v for k, v in values.items() if k in allowed})
    storage.save_settings(settings)
    return settings


def _native3d_component_types(component):
    types = component.get("types")
    if not isinstance(types, list) or not types:
        types = [component.get("type")] if component.get("type") else []
    return {str(value).casefold() for value in types if value}


def _native3d_support_files(settings, check=None):
    """Obtém mapping e codecs no suporte privado do Manager, sem FModel."""
    return native3d_support.ensure_support(settings, check=check)


def get_native3d_support_status():
    status = native3d_support.get_status()
    status["extractor_ready"] = os.path.isfile(_NATIVE3D_EXTRACTOR_EXE)
    return status


def update_native3d_support(job=None):
    check = job.check if job else None
    native3d_support.ensure_support(check=check, update=True)
    return {"ok": True, **get_native3d_support_status()}


def _native3d_game_global_files(settings):
    mods_path = pathlib.Path(str(settings.get("mods_path") or "").strip())
    paks_dir = next((path for path in (mods_path, *mods_path.parents)
                     if path.name.casefold() == "paks"), None)
    if not paks_dir:
        raise OSError("Não encontrei a pasta Paks a partir do caminho de mods configurado.")
    global_utoc = paks_dir / "global.utoc"
    global_ucas = paks_dir / "global.ucas"
    if not global_utoc.is_file() or not global_ucas.is_file():
        raise OSError("Não encontrei global.utoc/global.ucas na pasta Paks do jogo.")
    character_files = tuple(
        paks_dir / f"pakchunkCharacter-Windows{extension}"
        for extension in (".pak", ".utoc", ".ucas")
    )
    if not all(path.is_file() for path in character_files):
        raise OSError("Não encontrei o pacote pakchunkCharacter completo na pasta Paks do jogo.")
    return global_utoc, global_ucas, *character_files


def _native3d_extractor_command():
    if os.path.isfile(_NATIVE3D_EXTRACTOR_EXE):
        return [_NATIVE3D_EXTRACTOR_EXE]
    if os.path.isfile(_NATIVE3D_DOTNET) and os.path.isfile(_NATIVE3D_EXTRACTOR_DLL):
        return [_NATIVE3D_DOTNET, _NATIVE3D_EXTRACTOR_DLL]
    raise OSError("O extrator 3D do CrabVault não está instalado corretamente.")


def _native3d_stage_archives(component_files, global_files):
    """Cria apenas listas temporárias; os containers são lidos na origem."""
    os.makedirs(_NATIVE3D_WORK_ROOT, exist_ok=True)
    return tempfile.mkdtemp(prefix="archives-", dir=_NATIVE3D_WORK_ROOT)


def _native3d_frontend_url(path):
    frontend_root = os.path.join(storage.RESOURCE_DIR, "frontend")
    relative = os.path.relpath(path, frontend_root).replace(os.sep, "/")
    return urllib.parse.quote(relative, safe="/._-")


def _native3d_read_glb_materials(path):
    try:
        with open(path, "rb") as file:
            header = file.read(20)
            if len(header) != 20 or header[:4] != b"glTF":
                return []
            chunk_length, chunk_type = struct.unpack_from("<II", header, 12)
            if chunk_type != 0x4E4F534A:
                return []
            payload = header[20:] + file.read(chunk_length)
        document = json.loads(payload[:chunk_length].decode("utf-8").rstrip("\x00 \t\r\n"))
        return [str(item.get("name") or "Material") for item in document.get("materials", [])]
    except (OSError, ValueError, json.JSONDecodeError, struct.error):
        return []


def _native3d_texture_from_reference(reference, png_by_stem):
    value = str(reference or "").replace("\\", "/")
    candidates = [value.rsplit(".", 1)[-1], value.split(".", 1)[0].rsplit("/", 1)[-1]]
    for candidate in candidates:
        match = png_by_stem.get(candidate.casefold())
        if match:
            return match
    return None


def _native3d_pick_texture(material_data, png_by_stem, preferred_keys):
    textures = material_data.get("Textures", {}) if isinstance(material_data, dict) else {}
    if not isinstance(textures, dict):
        return None
    lowered = {str(key).casefold(): value for key, value in textures.items()}
    for key in preferred_keys:
        reference = lowered.get(key.casefold())
        match = _native3d_texture_from_reference(reference, png_by_stem)
        if match:
            return match
    for key in preferred_keys:
        for actual, reference in lowered.items():
            if key.casefold() in actual:
                match = _native3d_texture_from_reference(reference, png_by_stem)
                if match:
                    return match
    return None


def _native3d_texture_role(stem):
    value = stem.casefold()
    if re.search(r"(?:^|_)(?:n|normal|normals)$", value):
        return "normal"
    if re.search(r"(?:^|_)(?:orm|rma|mra|s|spec|specular)$", value):
        return "orm"
    if re.search(r"(?:^|_)(?:e|emis|emissive)$", value):
        return "emissive"
    if re.search(r"(?:^|_)(?:d|bc|basecolor|diffuse|albedo)$", value):
        return "base_color"
    return "unknown"


def _native3d_match_key(value):
    key = re.sub(r"^(?:mi|m|mat|material|t)_+", "", str(value or "").casefold())
    key = re.sub(r"_(?:d|bc|basecolor|diffuse|albedo|n|normal|normals|orm|rma|mra|s|spec|specular|e|emis|emissive)$", "", key)
    return re.sub(r"[^a-z0-9]+", "", key)


def _native3d_semantic_key(value):
    """Compara Body/Head/Equip ignorando IDs de skin e sufixos de instância."""
    key = _native3d_match_key(value)
    key = re.sub(r"^\d+", "", key)
    key = re.sub(r"(?:inst|instance|lobby|uv)\d*$", "", key)
    key = re.sub(r"\d+$", "", key)
    return key


def _native3d_infer_material_textures(material_name, png_files):
    material_key = _native3d_match_key(material_name)
    material_semantic = _native3d_semantic_key(material_name)
    matches = []
    material_tokens = set(re.findall(r"[a-z]+|\d+", str(material_name).casefold())) - {"mi", "m", "mat", "material"}
    for path in png_files:
        texture_key = _native3d_match_key(pathlib.Path(path).stem)
        texture_semantic = _native3d_semantic_key(pathlib.Path(path).stem)
        texture_tokens = set(re.findall(r"[a-z]+|\d+", pathlib.Path(path).stem.casefold())) - {"t"}
        exact = bool(material_key and texture_key and material_key == texture_key)
        contained = bool(material_key and texture_key and (material_key in texture_key or texture_key in material_key))
        semantic = bool(material_semantic and texture_semantic and material_semantic == texture_semantic)
        overlap = len(material_tokens & texture_tokens)
        score = (120 if exact else 100 if semantic else 40 if contained else 0) + overlap
        if score >= 3:
            matches.append((score, path))
    result = {}
    for _, path in sorted(matches, key=lambda item: item[0], reverse=True):
        role = _native3d_texture_role(pathlib.Path(path).stem)
        if role != "unknown" and role not in result:
            result[role] = path
    return result


def _native3d_material_manifest(material_names, output_directory):
    png_files = [str(path) for path in pathlib.Path(output_directory).rglob("*")
                 if path.suffix.casefold() in {".png", ".mmtx"}]
    png_by_stem = {pathlib.Path(path).stem.casefold(): path for path in png_files}
    material_json = {}
    for path in pathlib.Path(output_directory).rglob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as file:
                material_json[path.stem.casefold()] = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue

    result = {}
    body_fallback = _native3d_infer_material_textures("Body", png_files)
    equip_fallback = _native3d_infer_material_textures("Equip", png_files)
    for name in material_names:
        data = material_json.get(name.casefold())
        textures = {}
        if data:
            textures = {
                "base_color": _native3d_pick_texture(data, png_by_stem, ["BaseColor", "Diffuse", "PM_Diffuse", "TopDiffuse"]),
                "normal": _native3d_pick_texture(data, png_by_stem, ["Normal", "Normals", "PM_Normals", "TopNormals"]),
                "orm": _native3d_pick_texture(data, png_by_stem, ["ORM", "SpecularMasks", "PM_SpecularMasks", "TopSpecularMasks"]),
                "emissive": _native3d_pick_texture(data, png_by_stem, ["Emissive", "PM_Emissive", "TopEmissive", "Emis_Text"]),
            }
        inferred = _native3d_infer_material_textures(name, png_files)
        for role, path in inferred.items():
            if not textures.get(role):
                textures[role] = path
        lowered_name = str(name).casefold()
        if not textures.get("base_color"):
            fallback = None
            if any(marker in lowered_name for marker in ("nikke", "suit", "outfit", "cloth", "cotton", "uv1", "uv2")):
                fallback = body_fallback
            elif any(marker in lowered_name for marker in ("equip", "weapon")):
                fallback = equip_fallback
            for role, path in (fallback or {}).items():
                if not textures.get(role):
                    textures[role] = path
        parameters = data.get("Parameters", {}) if isinstance(data, dict) else {}
        result[name] = {
            role: _native3d_frontend_url(path)
            for role, path in textures.items() if path
        }
        result[name]["translucent"] = bool(parameters.get("IsTranslucent", False))
    return result, len(png_files)


def _native3d_build_result(output_directory, component_name, extracted, previous=None):
    """Merge one prepared model into the catalog; other variants remain lazy."""
    selected = str(extracted.get("selected") or "")
    files = extracted.get("meshes") or []
    if not selected or not files:
        return {"ok": False, "error": "O extrator não retornou uma variante renderizável."}
    path = os.path.abspath(str(files[0]))
    root = os.path.abspath(output_directory)
    if os.path.commonpath([root, path]) != root or not os.path.isfile(path):
        return {"ok": False, "error": "O extrator retornou um caminho de modelo inválido."}
    names = _native3d_read_glb_materials(path)
    material_manifest, texture_count = _native3d_material_manifest(names, output_directory)
    prepared = {
        "url": _native3d_frontend_url(path), "ready": True,
        "materials": material_manifest, "material_count": len(names),
        "texture_count": texture_count,
    }
    older = {item.get("key"): item for item in (previous or {}).get("models", [])}
    models = []
    for model in extracted.get("models", []):
        key = str(model.get("key") or "")
        if not key:
            continue
        entry = dict(older.get(key) or {})
        entry.update(key=key, name=str(model.get("name") or "Modelo"))
        entry.setdefault("ready", False)
        if key == selected:
            entry.update(prepared)
        models.append(entry)
    return {
        "ok": any(item.get("key") == selected and item.get("ready") for item in models),
        "component_name": component_name, "selected": selected,
        "models": models, "cached": False,
        "timings": extracted.get("timings", {}),
        "texture_statistics": extracted.get("textures", {}),
        "warnings": extracted.get("failures", []),
    }


def _native3d_cached_result(manifest_path, signature):
    try:
        with open(manifest_path, "r", encoding="utf-8") as file:
            manifest = json.load(file)
        result = manifest.get("result")
        if manifest.get("signature") != signature or not isinstance(result, dict):
            return None
        if not isinstance(result.get("models"), list):
            return None
        frontend_root = os.path.join(storage.RESOURCE_DIR, "frontend")
        component_root = os.path.abspath(os.path.dirname(manifest_path))

        def exists(url):
            relative = urllib.parse.unquote(str(url or "")).replace("/", os.sep)
            path = os.path.abspath(os.path.join(frontend_root, relative))
            return (os.path.commonpath([component_root, path]) == component_root
                    and os.path.isfile(path) and os.path.getsize(path) > 0)

        for model in result["models"]:
            if not isinstance(model, dict):
                return None
            urls = [model.get("url")]
            for material in model.get("materials", {}).values():
                urls.extend(material.get(role) for role in ("base_color", "normal", "orm", "emissive")
                            if material.get(role))
            if model.get("ready") and not all(exists(url) for url in urls):
                model["ready"] = False
                model.pop("url", None)
        result["cached"] = True
        return result
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _native3d_ready_model(result, model_key=None):
    models = (result or {}).get("models", [])
    if not models:
        return None
    key = model_key or models[0].get("key")
    model = next((item for item in models if item.get("key") == key), None)
    if model and model.get("ready") and model.get("url"):
        result["selected"] = key
        result["ok"] = True
        return result
    return None


def _native3d_save_manifest(path, signature, result):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as file:
        json.dump({"signature": signature, "result": result}, file, ensure_ascii=False)
    os.replace(temporary, path)


def cancel_component_3d_preview(request_id):
    return native3d_jobs.cancel(request_id)


def prepare_component_3d_preview(mod_id, component_id, model_key=None, request_id=None, gpu_formats=None):
    """Prepare only the requested variant, with cancellable work and shared maps."""
    try:
        with native3d_jobs.request(request_id) as job:
            return _prepare_component_3d_preview(mod_id, component_id, model_key, job, gpu_formats)
    except native3d_jobs.PreviewCancelled:
        return {"ok": False, "cancelled": True}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "A preparação deste modelo excedeu 2 minutos e foi interrompida."}
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {"ok": False, "error": f"Não foi possível preparar o modelo 3D: {exc}"}


def _prepare_component_3d_preview(mod_id, component_id, model_key, job, gpu_formats=None):
    started = time.monotonic()
    gpu_formats = sorted({value for value in (gpu_formats if isinstance(gpu_formats, list) else [])
                          if isinstance(value, str) and value in {"dxt1", "dxt3", "dxt5", "bc7"}})
    mods = storage.load_mods()
    mod = next((item for item in mods if item.get("id") == mod_id), None)
    component = next((item for item in (mod or {}).get("components", [])
                      if item.get("id") == component_id), None)
    if not mod or not component:
        return {"ok": False, "error": "Componente não encontrado."}
    if "mesh" not in _native3d_component_types(component):
        return {"ok": False, "error": "O visualizador 3D está disponível apenas para componentes Mesh."}
    if model_key is not None and (not isinstance(model_key, str) or len(model_key) > 2048):
        return {"ok": False, "error": "Identificador de modelo inválido."}

    source_files = _component_source_files(mod, component, _mod_source_files(mod))
    containers = [path for path in source_files
                  if os.path.splitext(path)[1].casefold() in {".pak", ".utoc", ".ucas"}]
    if not containers:
        return {"ok": False, "error": "Não encontrei o PAK/UTOC/UCAS deste componente na biblioteca."}
    # The native provider already reads this index. No UAssetTool scan, catalog
    # migration or synchronous analysis is needed before a preview/cache hit.
    settings = storage.load_settings()
    global_files = _native3d_game_global_files(settings)
    command = _native3d_extractor_command()
    mapping, oodle, zlib = _native3d_support_files(settings, check=job.check)
    extractor = _NATIVE3D_EXTRACTOR_DLL if command[0] == _NATIVE3D_DOTNET else _NATIVE3D_EXTRACTOR_EXE
    extractor_files = [extractor]
    if extractor.endswith(".exe"):
        assembly = os.path.splitext(extractor)[0] + ".dll"
        if os.path.isfile(assembly):
            extractor_files.append(assembly)
    signature_items = [
        _NATIVE3D_CACHE_VERSION, _bundle_signature(containers), gpu_formats,
        *[(str(path), os.path.getsize(path), os.stat(path).st_mtime_ns)
          for path in [mapping, oodle, zlib, *extractor_files, *global_files]],
    ]
    signature = hashlib.sha256(repr(signature_items).encode("utf-8")).hexdigest()
    safe_mod = _safe_storage_segment(str(mod_id), "mod")
    safe_component = _safe_storage_segment(str(component_id), "component")
    component_cache = os.path.join(_NATIVE3D_CACHE_ROOT, safe_mod, safe_component)
    output_directory = os.path.join(component_cache, "model")
    manifest_path = os.path.join(component_cache, "manifest.json")
    cache_root = os.path.abspath(_NATIVE3D_CACHE_ROOT)
    resolved_cache = os.path.abspath(component_cache)
    if resolved_cache == cache_root or os.path.commonpath([cache_root, resolved_cache]) != cache_root:
        return {"ok": False, "error": "O caminho do cache 3D é inválido."}

    job.check()
    cached = _native3d_cached_result(manifest_path, signature)
    ready = _native3d_ready_model(cached, model_key)
    if ready:
        ready["elapsed_seconds"] = round(time.monotonic() - started, 3)
        return ready

    # One heavy decoder at a time, but cached models never wait for it.
    while not _NATIVE3D_PREVIEW_LOCK.acquire(timeout=0.1):
        job.check()
    try:
        job.check()
        cached = _native3d_cached_result(manifest_path, signature)
        ready = _native3d_ready_model(cached, model_key)
        if ready:
            ready["elapsed_seconds"] = round(time.monotonic() - started, 3)
            return ready
        if cached and cached.get("models") and model_key and not any(
                item.get("key") == model_key for item in cached["models"]):
            return {"ok": False, "error": "Esta variante não pertence ao componente."}
        if cached is None:
            if os.path.isdir(component_cache):
                shutil.rmtree(component_cache)
            os.makedirs(output_directory, exist_ok=True)
            # Retain completed texture files after cancellation, but never treat
            # an unfinished GLB as a successful preview.
            _native3d_save_manifest(manifest_path, signature, {"models": [], "ok": False})

        stage = None
        try:
            stage = _native3d_stage_archives(containers, global_files)
            component_list = os.path.join(stage, "component-containers.txt")
            with open(component_list, "w", encoding="utf-8") as file:
                file.write("\n".join(os.path.abspath(path) for path in containers))
            global_list = os.path.join(stage, "global-containers.txt")
            with open(global_list, "w", encoding="utf-8") as file:
                file.write("\n".join(os.path.abspath(path) for path in global_files))
            arguments = [
                *command, "--archives", stage, "--mappings", str(mapping),
                "--output", output_directory, "--oodle", str(oodle), "--zlib", str(zlib),
                "--component-containers", component_list,
                "--global-containers", global_list,
                "--gpu-textures", ",".join(gpu_formats),
            ]
            if model_key:
                arguments.extend(["--model", model_key])
            process = job.run(arguments)
        finally:
            if stage and os.path.isdir(stage):
                shutil.rmtree(stage, ignore_errors=True)
        job.check()

        extracted = None
        for line in reversed((process.stdout or "").splitlines()):
            try:
                payload = json.loads(line)
                if isinstance(payload, dict) and "ok" in payload:
                    extracted = payload
                    break
            except json.JSONDecodeError:
                continue
        if process.returncode != 0 or not (extracted or {}).get("ok"):
            error = (extracted or {}).get("error") or (process.stderr or "").strip()
            return {"ok": False, "error": error or "Não foi possível converter este modelo."}
        result = _native3d_build_result(output_directory, component.get("name", "Componente"), extracted, cached)
        if not result["ok"]:
            return result
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        _native3d_save_manifest(manifest_path, signature, result)
        _record_activity(
            "prepare_component_3d", f"Prévia 3D preparada: {component.get('name', 'Componente')}",
            {"mod_id": mod_id, "component_id": component_id, "model": result["selected"]},
        )
        return result
    finally:
        _NATIVE3D_PREVIEW_LOCK.release()


def launch_game():
    """Abre Marvel Rivals pelo protocolo do Steam, sem janela de terminal."""
    launcher = str(storage.load_settings().get("launcher", "steam")).casefold()
    if launcher != "steam":
        return {"ok": False, "error": "No momento o Launch Game está configurado apenas para Steam."}
    try:
        # Usa o manipulador de protocolo do Windows, sem ``cmd /c start``.
        os.startfile("steam://rungameid/2767030")
        return {"ok": True}
    except OSError as exc:
        return {"ok": False, "error": f"Não foi possível abrir o Steam: {exc}"}


# ---------------------------------------------------------------------------
# Perfis de modlist
# ---------------------------------------------------------------------------
def _snapshot_mod_states(mods):
    return [{
        "id": mod.get("id"),
        "enabled": bool(mod.get("enabled")),
        "priority": max(1, min(10, int(mod.get("priority", 1) or 1))),
        "components": {str(component.get("id")): bool(component.get("enabled", True))
                       for component in mod.get("components", []) if component.get("id")},
    } for mod in mods]


def get_recovery_snapshot():
    snapshot = storage.load_settings().get("last_recovery_snapshot")
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("mods"), list):
        return None
    return {
        "available": True,
        "action": snapshot.get("action", "operação em massa"),
        "created_at": snapshot.get("created_at", ""),
        "mod_count": len(snapshot["mods"]),
    }


def list_profiles():
    """Lista perfis salvos sem expor o snapshot completo dos mods."""
    settings = storage.load_settings()
    profiles = settings.get("profiles", [])
    if not isinstance(profiles, list):
        profiles = []
    return [{
        "id": profile.get("id"),
        "name": profile.get("name", "Perfil"),
        "created_at": profile.get("created_at", ""),
        "mod_count": len(profile.get("mods", [])),
    } for profile in profiles if isinstance(profile, dict)]


def save_profile(name):
    """Salva o estado de switches dos mods e de seus componentes."""
    name = str(name or "").strip()
    if not name:
        return {"ok": False, "error": "Informe um nome para o perfil."}
    if len(name) > 80:
        return {"ok": False, "error": "O nome do perfil deve ter no máximo 80 caracteres."}
    settings = storage.load_settings()
    profiles = settings.get("profiles", [])
    if not isinstance(profiles, list):
        profiles = []
    if any(str(profile.get("name", "")).casefold() == name.casefold() for profile in profiles if isinstance(profile, dict)):
        return {"ok": False, "error": "Já existe um perfil com esse nome."}
    snapshot = _snapshot_mod_states(storage.load_mods())
    profiles.append({"id": storage.new_id(), "name": name, "created_at": storage.now_iso(), "mods": snapshot})
    settings["profiles"] = profiles
    storage.save_settings(settings)
    _record_activity("save_profile", f"Perfil salvo: {name}", {"mods": len(snapshot)})
    return {"ok": True, "profiles": list_profiles()}


def update_profile(profile_id):
    """Substitui o snapshot do perfil pelo estado atual, preservando nome e ID."""
    settings = storage.load_settings()
    profiles = settings.get("profiles", []) if isinstance(settings.get("profiles", []), list) else []
    profile = next((item for item in profiles if isinstance(item, dict) and str(item.get("id")) == str(profile_id)), None)
    if not profile:
        return {"ok": False, "error": "Perfil não encontrado."}
    snapshot = _snapshot_mod_states(storage.load_mods())
    profile["mods"] = snapshot
    profile["updated_at"] = storage.now_iso()
    settings["profiles"] = profiles
    storage.save_settings(settings)
    _record_activity("update_profile", f"Perfil atualizado: {profile.get('name', 'Perfil')}", {"mods": len(snapshot)})
    return {"ok": True, "profiles": list_profiles()}


def delete_profile(profile_id):
    settings = storage.load_settings()
    profiles = settings.get("profiles", [])
    kept = [profile for profile in profiles if str(profile.get("id")) != str(profile_id)]
    if len(kept) == len(profiles):
        return {"ok": False, "error": "Perfil não encontrado."}
    settings["profiles"] = kept
    storage.save_settings(settings)
    removed = next((profile for profile in profiles if str(profile.get("id")) == str(profile_id)), {})
    _record_activity("delete_profile", f"Perfil excluído: {removed.get('name', 'Perfil')}", {"profile_id": profile_id})
    return {"ok": True, "profiles": list_profiles()}


def _proposed_saved_mod_state(mod, target):
    proposed = copy.deepcopy(mod)
    desired_components = target.get("components", {}) if isinstance(target.get("components"), dict) else {}
    for component in proposed.get("components", []):
        if component["id"] in desired_components:
            component["enabled"] = bool(desired_components[component["id"]])
    proposed["enabled"] = bool(target.get("enabled"))
    proposed["priority"] = max(1, min(10, int(target.get("priority", mod.get("priority", 1)) or 1)))
    if not mod.get("install_target"):
        component_rules.assert_valid_state(proposed.get("components", []))
    return proposed


def _journal_file_targets(records, mods_path):
    targets = []
    for mod in records:
        if not mods_path:
            continue
        root = _game_target_dir(mod, mods_path)
        game_root = root if mod.get("install_target") else mods_path
        for entry in _all_mod_file_entries(mod):
            relative = _safe_relative_file_path(entry["name"])
            targets.append((os.path.join(root, relative), game_root))
            if mod.get("install_target") == "marvel_content":
                targets.append((os.path.join(root, _background_relative_file_path(relative)), game_root))
            if mod.get("external"):
                targets.append((os.path.join(_storage_dir(mod), relative), storage.STORAGE_DIR))
    return targets


@_serialized_files
def recover_interrupted_operation(operation_id):
    journal = None
    try:
        if operation_recovery.is_live(operation_id):
            return {"ok": False, "error": "Esta operação ainda está em andamento."}
        journal = operation_recovery.Journal.load(operation_id, resume=True)
        if journal.data.get("phase") in {"completed", "cancelled", "recovered", "aborted"}:
            journal.release()
            return {"ok": True, "already_recovered": True}
        operation_recovery.validate_workspace(journal)
        if journal.data.get("mutation_started"):
            mods_path = storage.load_settings().get("mods_path", "")
            expected_path = os.path.realpath(mods_path) if mods_path else ""
            if os.path.normcase(expected_path) != os.path.normcase(journal.data.get("mods_path", "")):
                raise ValueError("O caminho do jogo mudou. Restaure o caminho anterior antes de recuperar esta operação.")
            allowed = {os.path.normcase(operation_recovery._inside(path, root)): os.path.normcase(os.path.realpath(root))
                       for path, root in _journal_file_targets(
                           [*journal.data.get("before_records", []), *journal.data.get("after_records", [])], mods_path)}
            if journal.data.get("kind") == "component_append":
                allowed.update({
                    os.path.normcase(operation_recovery._inside(path, root)): os.path.normcase(os.path.realpath(root))
                    for path, root in _journal_storage_file_targets(
                        [*journal.data.get("before_records", []), *journal.data.get("after_records", [])]
                    )
                })
            if journal.data.get("special_atomic"):
                from . import special_imports
                allowed.update({os.path.normcase(operation_recovery._inside(path, root)): os.path.normcase(os.path.realpath(root))
                                for path, root in special_imports.temporary_targets(journal)})
            for item in journal.data.get("files", []):
                target = os.path.normcase(os.path.realpath(item["path"]))
                if target not in allowed or os.path.normcase(os.path.realpath(item["root"])) != allowed[target]:
                    raise ValueError("O snapshot contém um destino que não pertence aos mods desta operação.")
            if mods_path:
                _ensure_game_operation_allowed()
            if journal.data.get("special_guard"):
                from . import special_imports
                special_imports.validate_recovery(journal)
        operation_recovery.rollback(journal)
        return {"ok": True, "title": journal.data.get("title"), "kind": journal.data.get("kind")}
    except Exception as exc:
        if journal:
            journal.fail(exc)
        return {"ok": False, "error": str(exc)}


def _preserve_external_mod_files(mod, mods_path):
    """Completa a biblioteca sem sobrescrever cópias privadas já existentes."""
    if not mod.get("external") or not mods_path:
        return
    source_root = _game_target_dir(mod, mods_path)
    private_root = operation_recovery._inside(_storage_dir(mod), storage.STORAGE_DIR)
    for entry in _all_mod_file_entries(mod):
        relative = _safe_relative_file_path(entry["name"])
        source = operation_recovery._inside(os.path.join(source_root, relative), source_root)
        destination = operation_recovery._inside(os.path.join(private_root, relative), private_root)
        if os.path.isfile(destination):
            continue
        if os.path.lexists(destination):
            raise OSError(f"O destino do backup não é um arquivo regular: {entry['name']}")
        if os.path.isfile(source):
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            # O arquivo não existia; um hardlink não altera o ativo nem os
            # snapshots. Backups existentes nunca são abertos para escrita.
            _install_file_fast(source, destination)


def _apply_saved_mod_state(mod, target, mods_path):
    previous = copy.deepcopy(mod)
    proposed = _proposed_saved_mod_state(mod, target)
    proposed["files"] = copy.deepcopy(_all_mod_file_entries(proposed))
    previous_files = copy.deepcopy(previous)
    previous_files["files"] = copy.deepcopy(_all_mod_file_entries(previous))
    if mods_path:
        _ensure_game_operation_allowed()
    if mod.get("external") and mods_path:
        _preserve_external_mod_files(mod, mods_path)
        proposed["external"] = False
    try:
        if mods_path and mod.get("enabled"):
            _apply_enable(previous_files, mods_path, False)
        mod.clear()
        mod.update(proposed)
        if mods_path and mod["enabled"]:
            _apply_enable(mod, mods_path, True)
    except OSError:
        if mods_path:
            _apply_enable(mod, mods_path, False)
        mod.clear()
        mod.update(previous)
        if mods_path and mod.get("enabled"):
            _apply_enable(previous_files, mods_path, True)
        raise


def _apply_state_batch(mods, settings, wanted, title, recovery_snapshot):
    """Confirma o lote inteiro ou restaura o snapshot de arquivos e catálogo."""
    mods_path = settings.get("mods_path", "")
    candidates, proposed_records = [], []
    try:
        for mod in mods:
            target = wanted.get(str(mod.get("id")))
            if not target:
                continue
            proposed = _proposed_saved_mod_state(mod, target)
            if proposed == mod:
                continue
            if mod.get("external") and mods_path:
                proposed["external"] = False
            candidates.append(mod)
            proposed_records.append(proposed)
        if not candidates:
            return {"ok": True, "changed": [], "errors": []}
        if mods_path:
            _ensure_game_operation_allowed()
    except (OSError, ValueError) as exc:
        return {"ok": False, "changed": [], "errors": [{"error": str(exc)}], "error": str(exc)}

    journal = operation_recovery.Journal.create("profile", title, candidates, proposed_records, mods_path)
    journal.set_settings({"last_recovery_snapshot": settings.get("last_recovery_snapshot")},
                         {"last_recovery_snapshot": recovery_snapshot})
    try:
        journal.capture_files(_journal_file_targets([*candidates, *proposed_records], mods_path))
        journal.mark("applying")
        for mod in candidates:
            _apply_saved_mod_state(mod, wanted[str(mod["id"])], mods_path)
        journal.set_records(journal.data["before_records"], candidates)
        storage.save_mods(mods)
        settings["last_recovery_snapshot"] = recovery_snapshot
        storage.save_settings(settings)
        journal.mark("catalog_saved")
        journal.finish("completed")
        return {"ok": True, "changed": [mod["id"] for mod in candidates], "errors": []}
    except Exception as exc:
        try:
            if mods_path and journal.data.get("mutation_started"):
                _ensure_game_operation_allowed()
            operation_recovery.rollback(journal)
        except Exception as recovery_error:
            journal.fail(f"{exc} — Recuperação pendente: {recovery_error}")
            return {"ok": False, "changed": [], "errors": [{"error": str(exc)}],
                    "error": f"{exc} Restaure a operação pendente nas configurações.", "recovery_id": journal.id}
        return {"ok": False, "changed": [], "errors": [{"error": str(exc)}], "error": str(exc)}


@_serialized_files
def apply_profile(profile_id):
    """Aplica um snapshot sem varrer ou reclassificar a biblioteca."""
    settings = storage.load_settings()
    profile = next((entry for entry in settings.get("profiles", []) if str(entry.get("id")) == str(profile_id)), None)
    if not profile:
        return {"ok": False, "error": "Perfil não encontrado."}
    wanted = {str(entry.get("id")): entry for entry in profile.get("mods", []) if entry.get("id")}
    mods = storage.load_mods()
    title = f"Aplicar perfil: {profile.get('name', 'Perfil')}"
    result = _apply_state_batch(mods, settings, wanted, title, {
        "action": title, "created_at": storage.now_iso(), "mods": _snapshot_mod_states(mods),
    })
    if result["ok"] and result["changed"]:
        try:
            _record_activity("apply_profile", f"Perfil aplicado: {profile.get('name', 'Perfil')}",
                             {"profile_id": profile_id, "changed": len(result["changed"])})
        except Exception:
            pass
    return {**result, "profile": profile.get("name")}


@_serialized_files
def restore_last_recovery_snapshot():
    """Restaura o estado anterior à última operação em massa registrada."""
    settings = storage.load_settings()
    snapshot = settings.get("last_recovery_snapshot")
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("mods"), list):
        return {"ok": False, "error": "Não há uma operação em massa para reverter."}

    wanted = {str(entry.get("id")): entry for entry in snapshot["mods"] if entry.get("id")}
    result = _apply_state_batch(storage.load_mods(), settings, wanted, "Reverter operação em massa", None)
    if result["ok"] and not result["changed"]:
        settings["last_recovery_snapshot"] = None
        storage.save_settings(settings)
    if result["ok"]:
        try:
            _record_activity("restore_recovery_snapshot", "Revertida operação em massa",
                             {"changed": len(result["changed"]), "source": snapshot.get("action", "")})
        except Exception:
            pass
    return {**result, "source": snapshot.get("action", "")}


# ---------------------------------------------------------------------------
# Auto-deteccao da pasta do jogo (Steam)
# ---------------------------------------------------------------------------
_MOD_PATH_SUFFIXES = [
    os.path.join("steamapps", "common", "MarvelRivals", "MarvelGame", "Marvel", "Content", "Paks", "~mods"),
    os.path.join("steamapps", "common", "MarvelRivals", "Marvel", "Content", "Paks", "~mods"),
]


def _parse_library_folders_vdf(vdf_path):
    """Extrai os valores de 'path' do libraryfolders.vdf (formato chave-valor simples da Valve)."""
    paths = []
    try:
        with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for match in re.finditer(r'"path"\s*"([^"]+)"', content):
            p = match.group(1).replace("\\\\", "\\")
            paths.append(p)
    except OSError:
        pass
    return paths


def _steam_install_candidates():
    candidates = [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    try:
        import winreg
        for hive, subkey in [
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        ]:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                    candidates.insert(0, install_path)
            except OSError:
                pass
    except ImportError:
        pass
    return candidates


def _steam_library_paths():
    libraries = []
    for steam_path in _steam_install_candidates():
        vdf = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf):
            libraries.extend(_parse_library_folders_vdf(vdf))
        elif os.path.isdir(steam_path):
            libraries.append(steam_path)

    seen, result = set(), []
    for p in libraries:
        if p and p not in seen and os.path.isdir(p):
            seen.add(p)
            result.append(p)
    return result


def auto_detect_mods_path():
    """Tenta achar a pasta ~mods do Marvel Rivals nas bibliotecas do Steam. Devolve o caminho ou None."""
    for lib in _steam_library_paths():
        for suffix in _MOD_PATH_SUFFIXES:
            candidate = os.path.join(lib, suffix)
            parent = os.path.dirname(candidate)
            if os.path.isdir(parent):
                os.makedirs(candidate, exist_ok=True)
                return candidate

    # fallback: varre letras de drive comuns (Windows) procurando a estrutura direto
    if os.name == "nt":
        for drive in "CDEFGHIJ":
            for sub in ("Steam", "SteamLibrary"):
                base = f"{drive}:\\{sub}"
                if not os.path.isdir(base):
                    continue
                for suffix in _MOD_PATH_SUFFIXES:
                    candidate = os.path.join(base, suffix)
                    parent = os.path.dirname(candidate)
                    if os.path.isdir(parent):
                        os.makedirs(candidate, exist_ok=True)
                        return candidate
    return None


# ---------------------------------------------------------------------------
# Pastas (arvore recursiva de verdade)
# ---------------------------------------------------------------------------
def _scan_folder_tree(base_path, rel_path, counts):
    full_path = os.path.join(base_path, rel_path) if rel_path else base_path
    name = os.path.basename(rel_path) if rel_path else (os.path.basename(os.path.normpath(base_path)) or "~mods")

    children = []
    try:
        with os.scandir(full_path) as entries:
            directories = []
            for entry in entries:
                try:
                    if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                        continue
                    # Junctions também são reparse points no Windows. Não
                    # percorra vínculos que podem criar ciclos ou sair da raiz.
                    if os.name == "nt" and getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400:
                        continue
                    if entry.name == "Components" and counts.get(rel_path):
                        continue
                    directories.append(entry.name)
                except OSError:
                    continue
        for entry_name in sorted(directories):
            child_rel = os.path.join(rel_path, entry_name) if rel_path else entry_name
            children.append(_scan_folder_tree(base_path, child_rel, counts))
    except OSError:
        pass

    count = counts.get(rel_path, 0)
    return {"name": name, "path": rel_path, "count": count, "children": children}


def get_folders(*, _mods=None, _settings=None):
    settings = storage.load_settings() if _settings is None else _settings
    mods_path = settings.get("mods_path", "")
    mods = storage.load_mods() if _mods is None else _mods

    counts = {}
    for m in mods:
        f = m.get("folder") or ""
        counts[f] = counts.get(f, 0) + 1

    if mods_path and os.path.isdir(mods_path):
        root = _scan_folder_tree(mods_path, "", counts)
        root["count"] = len(mods)
        return [root]
    else:
        children = [{"name": k, "path": k, "count": v, "children": []} for k, v in sorted(counts.items()) if k]
        return [{"name": "~mods", "path": "", "count": len(mods), "children": children}]


def create_folder(name, parent=""):
    name = (name or "").strip()
    if not name or any(part in name for part in ("/", "\\", "..")):
        return {"ok": False, "error": "Nome de pasta inválido."}
    base = storage.load_settings().get("mods_path", "")
    if not base:
        return {"ok": False, "error": "Configure a pasta ~mods primeiro."}
    path = os.path.normpath(os.path.join(base, parent, name))
    if os.path.commonpath([base, path]) != os.path.normpath(base):
        return {"ok": False, "error": "Pasta fora do diretório de mods."}
    os.makedirs(path, exist_ok=True)
    return {"ok": True, "path": os.path.relpath(path, base)}


# ---------------------------------------------------------------------------
# Deteccao automatica de tipo (heuristica por nome de arquivo)
# ---------------------------------------------------------------------------
_TYPE_RULES = [
    ("Audio", (".wav", ".mp3", ".ogg", ".wem", ".bnk")),
    ("Audio", ("_va_", "_audio_", "voice")),
    ("Physics", ("physics", "_phys")),
    ("Texture", ("t_", "_texture", "_d.uasset", "_n.uasset", "_diffuse", "_normal")),
    ("Mesh", ("sk_", "sm_", "_mesh")),
    ("Blueprint", ("bp_", "_blueprint")),
    ("UI", ("ui_", "_ui_", "hud_")),
]


def _detect_type(filenames):
    joined = " ".join(f.lower() for f in filenames)
    for type_name, keywords in _TYPE_RULES:
        for kw in keywords:
            if kw.startswith(".") and any(f.lower().endswith(kw) for f in filenames):
                return type_name
            if not kw.startswith(".") and kw in joined:
                return type_name
    return "Unknown"


def _detect_type_with_path(filenames, folder):
    """O nome da pasta também é um sinal forte para mods já instalados."""
    text = (folder + " " + " ".join(filenames)).lower()
    if any(word in text for word in ("audio", "voice", "sound", "music")):
        return "Audio"
    if (any(word in text for word in ("icon", "hud", "background", "spray", "widget", "nameplate"))
            or re.search(r"(?:^|[/_\s-])ui(?:$|[/_\s-])", text)):
        return "UI"
    if any(word in text for word in ("physics", "_phys", "jiggle", "animblueprint", "anim_blueprint")):
        return "Physics"
    return _detect_type(filenames)


_UASSET_TOOL = os.path.join(storage.RESOURCE_DIR, "tools", "uassettool", "UAssetTool.exe")


def _uassettool_environment():
    """Fornece .NET 8 privado só ao leitor de assets, sem mudar o ambiente do app."""
    environment = os.environ.copy()
    runtime = os.path.join(storage.RESOURCE_DIR, "tools", "dotnet8")
    if os.path.isfile(os.path.join(runtime, "dotnet.exe")):
        environment.update(DOTNET_ROOT=runtime, DOTNET_ROOT_X64=runtime,
                           DOTNET_MULTILEVEL_LOOKUP="0", DOTNET_DISABLE_GUI_ERRORS="1")
    return environment


def _paths_from_bundle(files):
    """Lê os nomes de assets internos de uma instalação IoStore/PAK.

    Mods atuais de Marvel Rivals normalmente são IoStore: o .pak tem só a
    tabela de chunks e a lista útil está no .utoc. UAssetTool é distribuído
    junto do app para fazer essa leitura sem extrair nem modificar o mod.
    """
    if not os.path.isfile(_UASSET_TOOL):
        return []
    # Um mod pode conter diversos pares PAK/UTOC: por exemplo, o mesh
    # principal e um pacote separado de Physics. Antes era lido só o primeiro
    # contêiner encontrado, o que descartava os demais tipos do mesmo mod.
    utocs = sorted(
        {os.path.abspath(path) for path in files if path.lower().endswith(".utoc")},
        key=lambda value: value.casefold(),
    )
    utoc_stems = {os.path.splitext(path)[0].casefold() for path in utocs}
    containers = [("list_iostore", path) for path in utocs]
    # Um PAK acompanhado por UTOC já foi lido como IoStore. PAKs isolados
    # continuam sendo analisados normalmente, sem duplicar os mesmos assets.
    for path in sorted(
        {os.path.abspath(value) for value in files if value.lower().endswith(".pak")},
        key=lambda value: value.casefold(),
    ):
        if os.path.splitext(path)[0].casefold() not in utoc_stems:
            containers.append(("list_pak", path))
    if not containers:
        return []
    paths, seen = [], set()
    for command, container in containers:
        try:
            # Ao usar pythonw.exe, ferramentas de linha de comando ainda podem
            # piscar uma janela de CMD. CREATE_NO_WINDOW mantém a leitura dos
            # assets totalmente em segundo plano no Windows.
            operation_jobs.check()
            job = operation_jobs.current()
            command_args = [_UASSET_TOOL, command, container]
            result = job.run(command_args, timeout=20, env=_uassettool_environment()) if job else subprocess.run(
                command_args,
                env=_uassettool_environment(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            # Um contêiner quebrado não deve impedir a análise dos outros
            # arquivos que pertencem ao mesmo mod.
            continue
        for line in result.stdout.splitlines():
            # PAKs de voz podem conter só bancos Wwise (.bnk/.wem), sem nenhum
            # .uasset. Mantemos esses caminhos para detectar áudio.
            match = re.search(r"(.+?\.(?:uasset|bnk|wem))\b", line, re.IGNORECASE)
            if not match:
                continue
            asset_path = match.group(1).strip()
            key = asset_path.replace("\\", "/").casefold()
            if key not in seen:
                seen.add(key)
                paths.append(asset_path)
    return paths


def _bundle_signature(files):
    """Assinatura barata para invalidar o cache se o pacote for alterado."""
    entries = []
    for path in sorted(files, key=lambda value: value.casefold()):
        try:
            stat = os.stat(path)
            entries.append((os.path.abspath(path), stat.st_size, stat.st_mtime_ns))
        except OSError:
            entries.append((os.path.abspath(path), None, None))
    # O prefixo versiona o formato do cache. A versão 2 lia apenas um
    # contêiner; a versão 3 combina todos os PAKs/UTOCs do pacote.
    return hashlib.sha256(repr(("asset-paths-v3-all-containers", entries)).encode("utf-8")).hexdigest()


def _cached_bundle_paths(mod, files, cache_key):
    """Lê os assets uma vez e reutiliza o resultado enquanto o pacote não muda.

    O UAssetTool é correto, mas pode levar vários segundos em UCAS grandes.
    O cache fica junto ao registro do mod e é descartado automaticamente ao
    mudar tamanho/data de qualquer arquivo do conjunto.
    """
    signature = _bundle_signature(files)
    cache = mod.get("asset_path_cache") or {}
    cached = cache.get(cache_key) if isinstance(cache, dict) else None
    if (isinstance(cached, dict) and cached.get("signature") == signature
            and isinstance(cached.get("paths"), list)):
        return cached["paths"], False
    paths = _paths_from_bundle(files)
    # Só salvamos uma leitura que realmente retornou assets. Se a ferramenta
    # não estiver disponível temporariamente, a próxima abertura pode tentar
    # novamente em vez de congelar um resultado vazio para sempre.
    if paths:
        cache = dict(cache) if isinstance(cache, dict) else {}
        cache[cache_key] = {"signature": signature, "paths": paths}
        mod["asset_path_cache"] = cache
        return paths, True
    return paths, False


def _component_source_files(mod, component, source_files):
    """Retorna somente os contêineres pertencentes a um componente."""
    names = {
        str(entry.get("name", "")).replace("\\", "/").casefold()
        for entry in component.get("files", [])
    }
    return [path for path in source_files if any(
        str(path).replace("\\", "/").casefold().endswith("/" + name)
        or str(path).replace("\\", "/").casefold() == name for name in names)]


def _conflict_asset_key(path):
    """Normaliza um caminho interno para comparação entre PAKs/IoStore."""
    normalized = str(path or "").replace("\\", "/").strip().lstrip("./").casefold()
    # A ferramenta pode devolver ../../../Marvel/Content/... ou apenas
    # Marvel/Content/.... O prefixo não muda o asset que o jogo sobrescreve.
    marker = "/marvel/content/"
    position = normalized.find(marker)
    if position >= 0:
        return normalized[position + 1:]
    if normalized.startswith("marvel/content/"):
        return normalized
    return normalized


def _conflict_asset_type(path):
    value = str(path or "").replace("\\", "/").casefold()
    if value.endswith((".bnk", ".wem")) or "wwiseaudio" in value or "/audio/" in value:
        return "Audio"
    if "/ui/" in value or "/interface/" in value or "/widgets/" in value or "/hud/" in value:
        return "UI"
    if "/texture" in value or "/textures/" in value or "/material" in value:
        return "Texture"
    if "/mesh" in value or "/meshes/" in value:
        return "Mesh"
    return "Asset"


def _conflict_owners_overlap(left, right):
    """A mesma regra de disputa é usada pelo relatório e pela resolução."""
    if left["mod_id"] == right["mod_id"]:
        return bool(left["is_primary"] and right["is_primary"])
    left_identity = (left["character"].casefold(), left["skin"].casefold())
    right_identity = (right["character"].casefold(), right["skin"].casefold())
    return bool(all(left_identity) and left_identity == right_identity)


def get_conflicts(mod_ids=None, *, persist_cache=True, _mods=None):
    """Localiza sobreposições reais entre assets internos ativos.

    Tipo do mod não é, por si só, um conflito. Dois Meshes só aparecem no
    relatório se ambos tiverem o mesmo ``.uasset`` interno; um banco Wwise
    (.bnk/.wem) não conflita com um Mesh. Componentes Physics são suporte de
    armature e ficam fora da disputa entre variações, conforme a regra do
    gerenciador.
    """
    mods = storage.load_mods() if _mods is None else _mods
    selected_ids = {str(mod_id) for mod_id in (mod_ids or [])}
    by_asset = {}
    checked_components = 0
    ignored_physics = 0
    unreadable = []
    cache_changed = False
    candidates = [mod for mod in mods if mod.get("enabled") and
                  (not selected_ids or str(mod.get("id")) in selected_ids)]
    total = sum(sum(1 for component in mod.get("components") or [{"enabled": True}]
                    if component.get("enabled", True) and not _is_physics_component(component)) for mod in candidates)
    processed = 0

    for mod in mods:
        operation_jobs.check()
        if selected_ids and str(mod.get("id")) not in selected_ids:
            continue
        if not mod.get("enabled"):
            continue
        source_files = _mod_source_files(mod)
        components = mod.get("components") or [{
            "id": "whole-mod",
            "name": mod.get("name", "Mod"),
            "files": mod.get("files", []),
            "enabled": True,
        }]
        for component_index, component in enumerate(components):
            if not component.get("enabled", True):
                continue
            if _is_physics_component(component):
                ignored_physics += 1
                continue
            operation_jobs.progress("analyzing", f"Analisando componente {processed + 1}/{total}: {component.get('name', 'Componente')}", processed, total)
            processed += 1
            component_files = _component_source_files(mod, component, source_files)
            if not component_files:
                unreadable.append({
                    "mod": mod.get("name", "Mod"),
                    "component": component.get("name", "Componente"),
                    "reason": "Os arquivos ativos não foram encontrados.",
                })
                continue
            cache_key = f"conflict_component:{component.get('id') or component.get('name', '')}"
            classified = (mod.get("asset_path_cache") or {}).get(f"classification-v1:{component.get('id')}", {})
            if classified.get("signature") == _component_analysis_signature(component_files) and classified.get("paths"):
                paths, changed = classified["paths"], False
            else:
                paths, changed = _cached_bundle_paths(mod, component_files, cache_key)
            cache_changed = cache_changed or changed
            if not paths:
                unreadable.append({
                    "mod": mod.get("name", "Mod"),
                    "component": component.get("name", "Componente"),
                    "reason": "Não foi possível listar os assets internos.",
                })
                continue
            checked_components += 1
            component_label = str(component.get("description") or "").strip()
            # Mantém a política anterior: a label Principal é explícita;
            # sem label, somente o primeiro componente é o principal.
            component_types = _detect_types_from_asset_paths(paths, component_files, component.get("name", ""))
            is_primary = component_label.casefold() == "principal" or (
                not component_label and component_index == 0
            )
            owner = {
                "mod_id": mod.get("id"),
                "mod": mod.get("name", "Mod"),
                "component_id": component.get("id"),
                "component": component.get("name", "Componente"),
                "priority": max(1, min(10, int(mod.get("priority", 1) or 1))),
                "character": mod.get("character") or "",
                "skin": _resolved_skin_name(mod.get("skin"), mod.get("character")) or "",
                "is_primary": is_primary,
                "types": component_types,
                "files": [entry.get("name") for entry in component.get("files", [])],
                "exclusive_group": str(component.get("exclusive_group") or "").casefold(),
            }
            # Um contêiner pode repetir uma entrada na sua tabela; não pode
            # transformar a mesma combinação mod/componente em conflito.
            for path in set(paths):
                operation_jobs.check()
                key = _conflict_asset_key(path)
                if key:
                    by_asset.setdefault(key, {"path": key, "owners": []})["owners"].append(owner)

    conflicts = []
    for record_index, record in enumerate(by_asset.values()):
        operation_jobs.progress("comparing", "Comparando os assets dos componentes ativos…", record_index, len(by_asset))
        owners_by_component = {}
        for owner in record["owners"]:
            owners_by_component[(owner["mod_id"], owner["component_id"])] = owner
        owners = list(owners_by_component.values())
        if len(owners) < 2:
            continue
        # Principal e acompanhamento do mesmo mod podem compartilhar assets.
        # Entre mods, a política anterior compara somente a mesma identidade
        # completa (personagem e skin), evitando alertas por assets comuns.
        conflicting_indexes = set()
        for index, left in enumerate(owners):
            operation_jobs.check()
            for other_index in range(index + 1, len(owners)):
                right = owners[other_index]
                is_conflict = _conflict_owners_overlap(left, right)
                if is_conflict:
                    conflicting_indexes.update((index, other_index))
        if len(conflicting_indexes) < 2:
            continue
        owners = [owner for index, owner in enumerate(owners) if index in conflicting_indexes]
        owners.sort(key=lambda item: (-item["priority"], item["mod"].casefold(), item["component"].casefold()))
        top_priority = owners[0]["priority"]
        top = [owner for owner in owners if owner["priority"] == top_priority]
        conflicts.append({
            "asset_path": record["path"],
            "asset_type": _conflict_asset_type(record["path"]),
            "kind": "automatic",
            "owners": owners,
            "winner": None if len(top) > 1 else owners[0],
            "tie": len(top) > 1,
            "resolution": "priority_preference" if len(top) == 1 else "tie",
            "reason": "Estes componentes ativos contêm o mesmo caminho interno de asset.",
        })

    # Conflitos declarados manualmente pelo usuário. Eles não precisam ter o
    # mesmo asset interno, mas só aparecem se os dois mods estiverem ativos.
    active_mods = [
        mod for mod in mods
        if mod.get("enabled") and (not selected_ids or str(mod.get("id")) in selected_ids)
    ]
    active_by_id = {str(mod.get("id")): mod for mod in active_mods}
    automatic_pairs = {
        tuple(sorted((str(left.get("mod_id")), str(right.get("mod_id")))))
        for conflict in conflicts
        for index, left in enumerate(conflict.get("owners", []))
        for right in conflict.get("owners", [])[index + 1:]
        if left.get("mod_id") != right.get("mod_id")
        and _conflict_owners_overlap(left, right)
    }
    manual_pairs = set()
    for mod in active_mods:
        operation_jobs.check()
        mod_id = str(mod.get("id"))
        for other_id in mod.get("manual_conflicts", []) or []:
            other_id = str(other_id)
            if other_id not in active_by_id or other_id == mod_id:
                continue
            pair = tuple(sorted((mod_id, other_id)))
            if pair in manual_pairs or pair in automatic_pairs:
                continue
            manual_pairs.add(pair)
            owners = []
            for owner_mod in (active_by_id[pair[0]], active_by_id[pair[1]]):
                owners.append({
                    "mod_id": owner_mod.get("id"),
                    "mod": owner_mod.get("name", "Mod"),
                    "component_id": "manual-conflict",
                    "component": "Conflito marcado manualmente",
                    "priority": max(1, min(10, int(owner_mod.get("priority", 1) or 1))),
                    "character": owner_mod.get("character") or "",
                    "skin": _resolved_skin_name(owner_mod.get("skin"), owner_mod.get("character")) or "",
                    "is_primary": True,
                })
            owners.sort(key=lambda item: (-item["priority"], item["mod"].casefold()))
            top_priority = owners[0]["priority"]
            top = [owner for owner in owners if owner["priority"] == top_priority]
            conflicts.append({
                "asset_path": "Conflito marcado manualmente",
                "asset_type": "Manual",
                "kind": "manual",
                "owners": owners,
                "winner": None if len(top) > 1 else owners[0],
                "tie": len(top) > 1,
            })

    conflicts.sort(key=lambda item: (item["asset_type"], item["asset_path"].casefold()))
    operation_jobs.check()
    if cache_changed and persist_cache:
        operation_jobs.begin_commit("Salvando o cache da verificação concluída…")
        storage.save_mods(mods)
    return {
        "ok": True,
        "conflicts": conflicts,
        "resolved_conflicts": sum(1 for conflict in conflicts if not conflict["tie"]),
        "tied_conflicts": sum(1 for conflict in conflicts if conflict["tie"]),
        "checked_components": checked_components,
        "ignored_physics_components": ignored_physics,
        "unreadable": unreadable,
        "priority_note": "A prioridade indica a preferência do Manager; ela não altera a ordem de carregamento do jogo. Desative os concorrentes para manter somente uma versão do asset.",
    }


def _all_mod_file_entries(mod):
    """Retorna a união dos arquivos do mod e de todos os seus componentes.

    Registros antigos às vezes guardam apenas o trio principal em ``files`` e
    deixam os demais trios somente dentro de ``components``. Para análise de
    tipo/conteúdo, todos eles fazem parte do mesmo mod e precisam ser lidos.
    """
    entries = []
    seen = set()

    def add(entry):
        if not isinstance(entry, dict):
            return
        name = str(entry.get("name", "")).strip()
        if not name:
            return
        # O nome do arquivo é suficiente: arquivos de componentes repetidos
        # no registro principal não devem forçar duas leituras do contêiner.
        key = name.casefold()
        if key not in seen:
            seen.add(key)
            entries.append(entry)

    for entry in mod.get("files", []) or []:
        add(entry)
    for component in mod.get("components", []) or []:
        for entry in component.get("files", []) or []:
            add(entry)
    return entries


def _all_library_file_entries(mod):
    """Inclui payloads reversíveis sem tratá-los como conteúdo atual do mod."""
    entries = list(_all_mod_file_entries(mod))
    seen = {str(entry.get("name", "")).casefold() for entry in entries}

    def add_payload(payload):
        if not isinstance(payload, dict):
            return
        for entry in payload.get("files", []) or []:
            name = str(entry.get("name", "")).strip()
            if name and name.casefold() not in seen:
                seen.add(name.casefold())
                entries.append(entry)
        for version in payload.get("versions", []) or []:
            add_payload(version)

    for component in mod.get("components", []) or []:
        for version in component.get("versions", []) or []:
            add_payload(version)
    for removed in mod.get("removed_components", []) or []:
        add_payload(removed.get("component", {}))
    return entries


def _mod_source_files(mod):
    """Localiza todos os arquivos que pertencem ao mod e seus componentes."""
    settings = storage.load_settings()
    game_folder = _game_target_dir(mod, settings.get("mods_path", "")) if settings.get("mods_path") else ""
    storage_folder = _storage_dir(mod)
    files = []
    for entry in _all_mod_file_entries(mod):
        name = entry.get("name", "")
        in_game = os.path.join(game_folder, name)
        in_storage = os.path.join(storage_folder, name)
        if os.path.isfile(in_game):
            files.append(in_game)
        elif os.path.isfile(in_storage):
            files.append(in_storage)
    return files


def _identity_source_files(mod, source_files):
    """Escolhe somente o pacote que pode representar a skin principal.

    Cada variante de um arquivo compactado contém seu próprio trio
    PAK/UCAS/UTOC. Physics aponta deliberadamente para a armature Default, por
    isso nunca é usado para classificar personagem/skin. Damos preferência à
    primeira variante não-Physics que estiver ativada pelo usuário.
    """
    components = mod.get("components") or []
    for component in components:
        if not component.get("enabled") or _is_physics_component(component):
            continue
        selected = _component_source_files(mod, component, source_files)
        if selected:
            return selected

    non_physics = [path for path in source_files
                   if "physics" not in os.path.basename(path).casefold()]
    return non_physics or source_files


def _put_physics_components_last(components):
    """Normaliza importações antigas: Mesh primeiro, acompanhamentos depois."""
    ranked = sorted(enumerate(components), key=lambda item: (
        0 if "Mesh" in (item[1].get("types") or [item[1].get("type")]) else
        3 if _is_physics_component(item[1]) else
        2 if _is_ui_component(item[1]) else
        1,
        item[0],
    ))
    return [component for _, component in ranked]


def reclassify_existing_components(dry_run=False, mod_id=None):
    """Migra tipos antigos usando nomes e caches já persistidos, sem scan profundo."""
    mods = storage.load_mods()
    changed_mods = 0
    changed_components = 0
    changes = []
    for mod in mods:
        if mod_id is not None and mod.get("id") != mod_id:
            continue
        if mod.get("install_target") == "marvel_content":
            continue
        mod_changed = False
        for component in mod.get("components", []):
            types = _component_types_from_metadata(mod, component)
            if component.get("types") != types or component.get("type") != types[0]:
                changes.append({"mod": mod.get("name", "Mod"), "component": component.get("name", "Componente"), "before": component.get("types") or [component.get("type") or "Unknown"], "after": types})
                component["types"] = types
                component["type"] = types[0]
                changed_components += 1
                mod_changed = True
        if not mod.get("components_order_custom"):
            ordered = _put_physics_components_last(mod.get("components", []))
            if ordered != mod.get("components", []):
                mod["components"] = ordered
                mod_changed = True
        component_types = [value for component in mod.get("components", []) for value in component.get("types", []) if value != "Unknown"]
        combined = _ordered_component_types([*(mod.get("types") or [mod.get("type") or "Unknown"]), *component_types])
        if mod.get("types") != combined or mod.get("type") != combined[0]:
            mod["types"] = combined
            mod["type"] = combined[0]
            mod_changed = True
        if mod_changed:
            changed_mods += 1
    if changed_mods and not dry_run:
        storage.save_mods(mods)
        _record_activity("classify_components", f"Classificação atualizada em {changed_mods} mod(s)", {"components": changed_components})
    return {"ok": True, "dry_run": bool(dry_run), "mods": changed_mods, "components": changed_components, "changes": changes}


def _split_merged_components(components, fallback_files=None):
    """Separa registros antigos que juntaram vários trios em um switch.

    Cada nome-base de pacote é um componente independente. Mantemos o estado
    do switch original em cada parte para não desligar uma variante que já
    estava ativa, e deixamos Physics por último.
    """
    source_components = components or []
    if not source_components and fallback_files:
        source_components = [{"name": "", "files": fallback_files, "enabled": True}]
    result, changed = [], False
    for component in source_components:
        groups = {}
        for entry in component.get("files", []):
            name = entry.get("name", "")
            stem = os.path.splitext(name)[0]
            if stem:
                groups.setdefault(stem, []).append(entry)
        if len(groups) <= 1:
            result.append(component)
            continue
        changed = True
        for stem, entries in groups.items():
            result.append({
                "id": storage.new_id(),
                "name": stem,
                "files": entries,
                "enabled": component.get("enabled", True),
            })
    normalized = _put_physics_components_last(result)
    if normalized != result:
        changed = True
    return normalized, changed


def repair_component_groups():
    """Atualiza somente a estrutura de componentes já salva, sem tocar nos arquivos."""
    mods = storage.load_mods()
    repaired = []
    for mod in mods:
        components, changed = _split_merged_components(mod.get("components"), mod.get("files"))
        if changed:
            mod["components"] = components
            repaired.append({"id": mod["id"], "name": mod.get("name", ""),
                             "components": len(components)})
    if repaired:
        storage.save_mods(mods)
    return {"ok": True, "repaired": repaired}


def _bundle_information(mod, source_files, asset_paths):
    """Metadados seguros que podem ser deduzidos do pacote local."""
    extensions = {os.path.splitext(path)[1].lower() for path in source_files}
    options = mod.get("install_options", {})
    is_iostore = ".utoc" in extensions or ".ucas" in extensions
    has_raw_assets = bool(options.get("legacy_pak")) or not asset_paths
    return {
        "iostore": is_iostore,
        "hybrid": bool(options.get("hybrid_iostore")),
        "encrypted": bool(options.get("obfuscation")),
        "raw_assets": has_raw_assets,
    }


def _identity_from_asset_paths(asset_paths):
    """Obtém herói e skin pelo caminho interno do asset do próprio mod."""
    # Bancos de voz Wwise carregam o ID completo diretamente no nome, por
    # exemplo ``bnk_vo_1031001.bnk`` (Luna Snow / Default).
    for asset in asset_paths:
        audio_id = re.search(r"\bbnk_[a-z0-9_]*?(\d{7})\.bnk\b", asset, re.IGNORECASE)
        if audio_id:
            skin_id = audio_id.group(1)
            character = CHARACTER_BY_ID.get(skin_id[:4])
            if character:
                skin = SKIN_BY_ID.get(skin_id, (character, "Default" if skin_id.endswith("001") else f"Skin ID {skin_id}"))[1]
                return character, skin
    candidates = []
    for asset in asset_paths:
        match = re.search(r"(?:Characters|Hero(?:_ST)?)/(\d{4})/(\d{7})(?:/|$)", asset, re.IGNORECASE)
        if not match:
            continue
        character_id, skin_id = match.groups()
        candidates.append((asset, character_id, skin_id))
    # Meshes identificam a skin principal com mais segurança do que texturas
    # de recolor e materiais compartilhados. Em pacotes só de materiais que
    # referenciam diversas skins, a base ...001 é a opção Default.
    candidates.sort(key=lambda item: (
        "/meshes/" not in item[0].lower(),
        # Em um pacote de skin a malha Default (…001) pode vir junto por
        # dependência. Quando também existe uma malha de skin específica,
        # esta é a identidade do mod e precisa vencer a base …001.
        item[2].endswith("001"),
        item[0].casefold(),
    ))
    for asset, character_id, skin_id in candidates:
        character = CHARACTER_BY_ID.get(character_id)
        if not character:
            continue
        # Uma skin desconhecida ainda mostra o herói correto. Só tratamos
        # IDs terminados em 001 como Default; os demais continuam visíveis
        # pelo ID para nunca atribuir uma skin errada ao mod.
        # Em pacotes sem Mesh, IDs ...001 são a aparência padrão mesmo se um
        # catálogo externo tiver associado esse ID de forma incorreta.
        has_mesh = any("/meshes/" in candidate[0].lower() for candidate in candidates)
        skin = ("Default" if skin_id.endswith("001") and not has_mesh
                else SKIN_BY_ID.get(skin_id, (character, "Default" if skin_id.endswith("001") else f"Skin ID {skin_id}"))[1])
        return character, skin
    return None, None


def _skin_from_install_folder(character, folder):
    """Usa a pasta organizada como contexto para arquivos auxiliares.

    Pacotes de physics, por exemplo, frequentemente referenciam a skin base
    (1031001), embora pertençam à skin escolhida na pasta do mod.
    """
    if not character or not folder:
        return None
    known_skins = {
        skin for hero, skin in SKIN_BY_ID.values()
        if hero == character and skin and skin != "Default"
    }
    by_normalized_name = {
        re.sub(r"[^a-z0-9]", "", skin.casefold()): skin
        for skin in known_skins
    }
    for part in pathlib.PureWindowsPath(folder).parts:
        normalized = re.sub(r"[^a-z0-9]", "", part.casefold())
        if normalized in by_normalized_name:
            return by_normalized_name[normalized]
    return None


def _skin_from_mod_name(character, name):
    """Último recurso para mods de UI, que não possuem caminho Characters/."""
    if not character or not name:
        return None
    normalized_name = re.sub(r"[^a-z0-9]", "", name.casefold())
    candidates = [
        skin for hero, skin in SKIN_BY_ID.values()
        if hero == character and skin and skin != "Default"
        and re.sub(r"[^a-z0-9]", "", skin.casefold()) in normalized_name
    ]
    return max(candidates, key=len) if candidates else None


def _detect_types_from_asset_paths(paths, files, folder):
    """Classifica usando paths já lidos, sem executar a ferramenta outra vez."""
    if not paths:
        detected = _detect_type_with_path([os.path.basename(f) for f in files], folder)
        return [detected]
    # UAssetTool pode devolver separadores Windows ou Unix; normalizamos antes
    # de procurar diretórios como Meshes/Textures/UI.
    lower = "\n".join(str(path).replace("\\\\", "/") for path in paths).lower()
    names = [os.path.basename(line.split(" [", 1)[0]).lower() for line in paths]
    found = []
    if any(_is_mesh_asset_path(path) for path in paths): found.append("Mesh")
    if any(name.startswith("t_") for name in names) or "/texture" in lower: found.append("Texture")
    # Voice packs podem não conter UAssets: nesses casos a única evidência é
    # o banco Wwise (.bnk/.wem) ou seu diretório interno.
    if (any(name.endswith((".bnk", ".wem")) for name in names)
            or "wwiseaudio" in lower or "/wwise/" in lower):
        found.append("Audio")
    if any(marker in lower for marker in ("/ui/", "/interface/", "/widgets/", "/hud/")): found.append("UI")
    if any(name.startswith("bp_") for name in names): found.append("Blueprint")
    if "/vfx/" in lower and any(name.startswith("mi_") for name in names): found.append("VFX")
    # Physics fica por último: em pacotes híbridos o conteúdo visual/áudio
    # continua sendo principal, mas Physics aparece como tipo adicional.
    # Quando ele é o único asset, deixa de virar Unknown.
    if (any("physics" in name or "_phys" in name or "jiggle" in name or "animblueprint" in name for name in names)
            or "/physics" in lower or "jiggle" in lower or "animblueprint" in lower):
        found.append("Physics")
    return found or [_detect_type_with_path([os.path.basename(f) for f in files], folder)]


def _detect_types_from_bundle(files, folder):
    """Todos os tipos encontrados, em ordem de prioridade visual.

    Mesh aparece antes de Audio para que pacotes híbridos sejam categorizados
    pelo conteúdo visual principal, sem esconder que também têm áudio.
    """
    return _detect_types_from_asset_paths(_paths_from_bundle(files), files, folder)


def _detect_type_from_bundle(files, folder):
    return _detect_types_from_bundle(files, folder)[0]


def _infer_character(folder):
    """Encontra o personagem pelo nome de qualquer pasta no caminho."""
    aliases = {"invisible woman": "Invisible Woman", "susan storm": "Invisible Woman",
               "scarlet witch": "Scarlet Witch", "wanda maximov": "Scarlet Witch",
               "spider man": "Spider-Man", "cloak and dagger": "Cloak & Dagger"}
    pieces = re.split(r"[\\/]", folder.lower())
    normalised = [re.sub(r"[^a-z0-9]", "", p) for p in pieces]
    for character in MARVEL_CHARACTERS:
        key = re.sub(r"[^a-z0-9]", "", character.lower())
        if key in normalised:
            return character
    for key, value in aliases.items():
        if re.sub(r"[^a-z0-9]", "", key) in normalised:
            return value
    return "Generic"


def _infer_character_from_text(*values):
    """Reconhece o herói citado no nome de um pacote.

    Alguns mods de parceria alteram assets dos dois heróis (por exemplo,
    Psylocke + Jeff). O primeiro herói explicitamente citado no nome do
    arquivo é o alvo do mod, enquanto o segundo costuma ser só o acessório.
    """
    text = re.sub(r"[^a-z0-9]", "", " ".join(str(value or "") for value in values).casefold())
    matches = []
    identities = [(character, character) for character in MARVEL_CHARACTERS]
    # Sue/Susan Storm é a Mulher Invisível, inclusive em nomes concatenados
    # de PAKs. A ocorrência mais específica vem antes do sobrenome Storm.
    identities.extend((alias, "Invisible Woman") for alias in ("Sue Storm", "Susan Storm"))
    for alias, character in identities:
        key = re.sub(r"[^a-z0-9]", "", alias.casefold())
        position = text.find(key)
        if position >= 0:
            matches.append((position, -len(key), character))
    return min(matches)[2] if matches else None


def analyze_mod_files(filepaths, asset_paths=None):
    """Retorna sugestões para o modal após o usuário selecionar os arquivos."""
    names = [os.path.basename(path) for path in filepaths]
    folder = os.path.dirname(filepaths[0]) if filepaths else ""
    if asset_paths is None:
        asset_paths = _paths_from_bundle(filepaths)
    character, skin = _identity_from_asset_paths(asset_paths)
    character = character or _infer_character(folder)
    skin = skin or ""
    named_character = _infer_character_from_text(*names)
    if named_character:
        character = named_character
    source_folder = os.path.basename(os.path.commonpath(filepaths)) if filepaths else ""
    if not source_folder and filepaths:
        source_folder = os.path.basename(os.path.dirname(filepaths[0]))
    safe_source = re.sub(r'[<>:"/\\|?*]+', "_", source_folder).strip(". ") or "Mod"
    detected_types = _detect_types_from_asset_paths(asset_paths, filepaths, folder)
    detected_type = detected_types[0]
    suggested_folder = (os.path.join("1_Audio", safe_source) if detected_type == "Audio"
                        else os.path.join(character, skin or "Default", safe_source))
    return {
        "suggested_name": os.path.splitext(names[0])[0] if names else "",
        "character": character,
        "skin": skin,
        "type": detected_type,
        "types": detected_types,
        "asset_count": len(asset_paths),
        "source_folder": source_folder,
        "suggested_folder": suggested_folder if character != "Generic" or detected_type == "Audio" else safe_source,
    }


def scan_installed_mods():
    """Indexa mods existentes em ~mods, sem modificar nenhum arquivo do jogo.

    Em uma pasta de pacote da estrutura nova (Personagem/Skin/Pacote), todos
    os conjuntos .pak/.ucas/.utoc da pasta pertencem ao mesmo mod e viram
    componentes alternáveis. O backup em mods_storage é criado sob demanda
    somente antes da primeira desativação.
    """
    settings = storage.load_settings()
    mods_path = settings.get("mods_path", "")
    if not mods_path or not os.path.isdir(mods_path):
        return {"ok": False, "error": "Configure uma pasta ~mods válida antes de varrer."}
    first_scan = settings.get("installed_scan_completed") is not True
    mods = storage.load_mods()

    def has_registered_parent_folder(folder):
        """Não duplica variações guardadas sob a pasta de um mod existente.

        Alguns mods compactados preservam uma árvore como
        ``Hero/Skin/Arquivo/Default/L``. O registro do Manager já representa
        ``Hero/Skin/Arquivo`` e seus componentes; as subpastas seguintes são
        só organização do autor, não novos mods independentes.
        """
        # A instalação pode ter ``Squirrel_Girl`` enquanto o registro criado
        # pelo Manager usa ``Squirrel Girl``. Para a hierarquia, são a mesma
        # pasta lógica; removemos separadores antes de comparar.
        normalise_part = lambda part: re.sub(r"[^a-z0-9]", "", part.casefold())
        child = tuple(normalise_part(part) for part in pathlib.PureWindowsPath(folder).parts)
        for existing_mod in mods:
            if existing_mod.get("external"):
                continue
            parent = tuple(normalise_part(part) for part in pathlib.PureWindowsPath(
                existing_mod.get("folder", "")
            ).parts)
            if len(parent) < 3 or len(child) <= len(parent):
                continue
            # ZIPs frequentemente incluem uma pasta de apresentação extra
            # entre Skin e o nome final do arquivo. Procuramos os segmentos
            # do registro na ordem em que aparecem, sem exigir que sejam
            # adjacentes: ``Hero/Skin/Arquivo`` continua sendo o pai de
            # ``Hero/Skin/Pasta extra/Arquivo/Default/L``.
            cursor = 0
            for part in parent:
                try:
                    cursor = child.index(part, cursor) + 1
                except ValueError:
                    break
            else:
                if cursor < len(child):
                    return True
        return False

    # Converte os registros legados vindos do scanner antigo: ele indexava
    # cada trio por separado, enquanto a mesma pasta de pacote pode conter o
    # mod principal e acompanhamentos (physics, variações etc.). Apenas
    # registros externos são reunidos aqui; mods importados pelo app mantêm
    # exatamente a organização que o usuário escolheu.
    external_by_folder = {}
    for mod in mods:
        folder = mod.get("folder", "")
        if mod.get("external") and len(pathlib.PureWindowsPath(folder).parts) >= 3:
            external_by_folder.setdefault(folder.lower(), []).append(mod)
    merged = 0
    removed_ids = set()
    for candidates in external_by_folder.values():
        if len(candidates) < 2:
            continue
        # Prefere como cartão principal o arquivo que não se chama Physics.
        candidates.sort(key=lambda item: ("physics" in item.get("name", "").lower(), item.get("created_at", "")))
        primary = candidates[0]
        all_files, seen_names = [], set()
        for item in candidates:
            for entry in item.get("files", []):
                key = entry.get("name", "").lower()
                if key and key not in seen_names:
                    all_files.append(entry)
                    seen_names.add(key)
        grouped_components = {}
        for entry in all_files:
            grouped_components.setdefault(os.path.splitext(entry["name"])[0], []).append(entry)
        primary["files"] = all_files
        primary["components"] = [
            {"id": storage.new_id(), "name": stem, "files": entries, "enabled": True}
            for stem, entries in grouped_components.items()
        ]
        primary["size_mb"] = round(sum(
            os.path.getsize(os.path.join(mods_path, primary.get("folder", ""), entry["name"]))
            for entry in all_files
            if os.path.isfile(os.path.join(mods_path, primary.get("folder", ""), entry["name"]))
        ) / (1024 * 1024), 2)
        if primary.get("type") == "Unknown":
            primary["type"] = next((item.get("type") for item in candidates if item.get("type") != "Unknown"), "Unknown")
        removed_ids.update(item["id"] for item in candidates[1:])
        merged += 1
    if removed_ids:
        mods[:] = [mod for mod in mods if mod["id"] not in removed_ids]
    existing = {(m.get("folder", "").lower(), f.get("name", "").lower())
                for m in mods for f in m.get("files", [])}
    groups = {}
    for root, _, names in os.walk(mods_path):
        rel_folder = os.path.relpath(root, mods_path)
        if rel_folder == ".":
            rel_folder = ""
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext not in {".pak", ".ucas", ".utoc"}:
                continue
            folder_parts = pathlib.PureWindowsPath(rel_folder).parts
            package_key = "__package__" if len(folder_parts) >= 3 else os.path.splitext(name)[0].lower()
            key = (rel_folder.lower(), package_key)
            groups.setdefault(key, {"folder": rel_folder, "stem": os.path.splitext(name)[0], "files": []})["files"].append(name)
    added = 0
    skipped_nested = 0
    for group in groups.values():
        # Não duplica algo que já foi cadastrado pelo app.
        if any((group["folder"].lower(), f.lower()) in existing for f in group["files"]):
            continue
        if has_registered_parent_folder(group["folder"]):
            skipped_nested += 1
            continue
        file_entries, total_size = [], 0
        for name in sorted(group["files"]):
            path = os.path.join(mods_path, group["folder"], name)
            file_entries.append({"name": name})
            total_size += os.path.getsize(path)
        component_groups = {}
        for entry in file_entries:
            component_groups.setdefault(os.path.splitext(entry["name"])[0], []).append(entry)
        # O scan serve para descobrir pacotes. Abrir cada UTOC aqui torna a
        # primeira varredura proporcional ao tamanho de toda a biblioteca e
        # pode levar vários minutos. A leitura profunda fica para os detalhes
        # do mod, onde o cache é criado apenas para o item aberto pelo usuário.
        detected_types = _detect_types_from_asset_paths(
            [], [os.path.join(mods_path, group["folder"], name) for name in group["files"]], group["folder"]
        )
        mod_id = storage.new_id()
        mods.append({
            "id": mod_id, "name": group["stem"], "character": _infer_character(group["folder"]),
            "skin": "", "type": detected_types[0], "types": detected_types,
            "tags": [], "image": None, "link": "", "files": file_entries,
            "components": [{"id": storage.new_id(), "name": stem, "files": entries, "enabled": True}
                           for stem, entries in component_groups.items()],
            "size_mb": round(total_size / (1024 * 1024), 2), "enabled": True,
            "folder": group["folder"], "priority": 1, "created_at": storage.now_iso(),
            "external": True,
        })
        added += 1
    # O scan conclui a classificação profunda para que os cards já sejam
    # salvos com seus tipos. Scans seguintes reutilizam o cache por assinatura
    # e só reabrem pacotes alterados ou ainda sem evidência.
    classified = 0
    identified = 0
    analyzed_components = 0
    with _COMPONENT_ANALYSIS_LOCK:
        for mod in mods:
            if not mod.get("external") or mod.get("install_target"):
                continue
            before_types = tuple(mod.get("types") or [mod.get("type") or "Unknown"])
            before_cache = {key for key in (mod.get("asset_path_cache") or {})
                            if key.startswith("classification-v1:")}
            source_files = _mod_source_files(mod)
            _analyze_mod_components(mod, source_files)
            after_cache = {key for key in (mod.get("asset_path_cache") or {})
                           if key.startswith("classification-v1:")}
            analyzed_components += len(after_cache - before_cache)
            if tuple(mod.get("types") or [mod.get("type") or "Unknown"]) != before_types:
                classified += 1
            # Reutiliza o cache do componente visual escolhido pela mesma
            # regra dos detalhes. Physics não pode decidir a skin principal.
            if not isinstance(mod.get("identity_override"), dict):
                selected = {os.path.normcase(os.path.abspath(path))
                            for path in _identity_source_files(mod, source_files)}
                identity_paths = []
                for component in mod.get("components", []):
                    component_files = _component_source_files(mod, component, source_files)
                    if not selected.intersection(os.path.normcase(os.path.abspath(path))
                                                 for path in component_files):
                        continue
                    cached = (mod.get("asset_path_cache") or {}).get(
                        f"classification-v1:{component.get('id')}", {}
                    )
                    identity_paths.extend(cached.get("paths") or [])
                character, skin = _identity_from_asset_paths(identity_paths)
                previous_identity = (mod.get("character"), mod.get("skin"))
                if character:
                    mod["character"] = character
                if skin:
                    mod["skin"] = skin
                if previous_identity != (mod.get("character"), mod.get("skin")):
                    identified += 1

    # Backgrounds não dependem de UAssetTool e nunca devem ser tratados como
    # mods visuais comuns mesmo se um BK2 citar o nome de um personagem.
    reclassified = 0
    for mod in mods:
        # Arquivos de cinematics são instalados em Marvel\\Content\\Marvel,
        # e não seguem a estrutura de PAKs do ~mods. Seus BK2 podem citar
        # personagens (por exemplo, Thing) e nunca devem ser reclassificados
        # pelo scanner como um mod visual comum.
        if mod.get("install_target") == "marvel_content":
            previous = (mod.get("character"), mod.get("skin"), mod.get("type"), mod.get("types"), mod.get("folder"))
            mod["character"] = "Backgrounds"
            mod["skin"] = ""
            mod["type"] = "Background"
            mod["types"] = ["Background"]
            mod["folder"] = "Backgrounds"
            mod.pop("identity_override", None)
            if previous != (mod["character"], mod["skin"], mod["type"], mod["types"], mod["folder"]):
                reclassified += 1
    storage.save_mods(mods)
    settings["installed_scan_completed"] = True
    storage.save_settings(settings)
    return {"ok": True, "added": added, "merged": merged, "reclassified": reclassified,
            "classified": classified, "analyzed_components": analyzed_components,
            "identified": identified,
            "first_scan": first_scan, "scan_completed": True,
            "skipped_nested": skipped_nested, "total": len(groups)}


# ---------------------------------------------------------------------------
# Ativar / desativar (copia ou remove os arquivos na pasta real do jogo)
# ---------------------------------------------------------------------------
def _install_file_fast(source, destination):
    """Instala um arquivo preservando o backup no storage.

    Quando o backup e a pasta ``~mods`` vivem no mesmo volume NTFS, um hard
    link é instantâneo e não duplica dezenas de GB de UCAS. Para instalações
    em outro disco (ou sistemas que não oferecem hard links), voltamos para a
    cópia normal sem alterar o comportamento do mod manager.
    """
    if not os.path.isfile(source):
        raise FileNotFoundError(f"Arquivo de origem ausente: {source}")
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if os.path.exists(destination):
        try:
            if os.path.samefile(source, destination):
                return True
        except OSError:
            pass
        os.remove(destination)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)
    return True


def _is_marvel_rivals_running():
    """Retorna True quando o executável do jogo estiver ativo no Windows."""
    if os.name != "nt":
        return False
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for image_name in ("MarvelRivals.exe", "Marvel-Win64-Shipping.exe"):
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/NH"],
                capture_output=True,
                text=True,
                errors="ignore",
                timeout=5,
                creationflags=creationflags,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if image_name.casefold() in result.stdout.casefold():
            return True
    return False


def _ensure_game_operation_allowed():
    settings = storage.load_settings()
    if settings.get("bypass_game_running_lock"):
        return
    if _is_marvel_rivals_running():
        raise OSError(
            "Marvel Rivals está em execução. Feche o jogo para alterar mods ou "
            "ative 'Ignorar bloqueio de operações' nas configurações."
        )


def _apply_enable(mod, mods_path, enable):
    _ensure_game_operation_allowed()
    if enable and not mod.get("install_target"):
        component_rules.assert_valid_state(mod.get("components", []))
    # Registros criados antes da sanitização podem ainda ter ':' ou outros
    # caracteres inválidos no Windows. Corrige o registro ao primeiro uso.
    safe_folder = _safe_game_folder(mod.get("folder", ""))
    mod["folder"] = safe_folder
    target_dir = _game_target_dir(mod, mods_path)
    mod_dir = _storage_dir(mod)

    if enable and mod.get("install_target") == "marvel_content":
        _ensure_movies_backup(target_dir)

    active_names = {
        entry["name"] for component in mod.get("components", []) if component.get("enabled", True)
        for entry in component.get("files", [])
    }
    if enable:
        os.makedirs(target_dir, exist_ok=True)
        for f in mod["files"]:
            # Para Backgrounds, componentes desmarcados significam que nenhum
            # BK2 dessa variação deve ser copiado para o jogo. Outros tipos
            # preservam a compatibilidade com registros legados sem seleção.
            if ((mod.get("install_target") == "marvel_content" and mod.get("components")
                 and f["name"] not in active_names)
                    or (mod.get("background_audio") and mod.get("components")
                        and f["name"] not in active_names)
                    or (mod.get("components") and f["name"] not in active_names)):
                continue
            src = os.path.join(mod_dir, f["name"])
            target_name = (_background_relative_file_path(f["name"])
                           if mod.get("install_target") == "marvel_content" else f["name"])
            destination = os.path.join(target_dir, target_name)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            _install_file_fast(src, destination)
    else:
        for f in mod["files"]:
            p = os.path.join(target_dir, f["name"])
            if os.path.exists(p):
                os.remove(p)


def _sync_game_location_for_identity(mod, mods_path):
    """Tira skins já identificadas da pasta ``Default`` antiga.

    A classificação visual não pode divergir da instalação real: se uma skin
    como Cherry Delight/Shining Star foi detectada, seus PAKs precisam ficar
    em ``Herói\\Skin\\Pacote``. Pacotes de áudio continuam em ``1_Audio``.
    """
    if not mods_path or mod.get("type") == "Audio":
        return False
    character = _safe_storage_segment(mod.get("character"), "Generic")
    skin = _safe_storage_segment(mod.get("skin"), "Default")
    parts = pathlib.PureWindowsPath(str(mod.get("folder") or "")).parts
    if len(parts) < 3:
        return False
    # Só migramos o layout legado Herói\\Default\\Pacote. Assim uma pasta
    # escolhida manualmente pelo usuário não é alterada sem necessidade. Se
    # o primeiro nível for outro herói, é uma classificação antiga errada e
    # também deve ser reparada (ex.: Psylocke salva sob Jeff).
    is_wrong_hero = parts[0].casefold() != character.casefold()
    has_manual_identity = isinstance(mod.get("identity_override"), dict)
    if ((parts[1].casefold() != "default" and not is_wrong_hero and not has_manual_identity) or (
        skin.casefold() == "default" and not is_wrong_hero and not has_manual_identity
    )):
        return False
    package = _safe_game_folder(parts[-1])
    desired_folder = os.path.join(character, skin, package)
    if os.path.normcase(os.path.normpath(mod.get("folder", ""))) == os.path.normcase(os.path.normpath(desired_folder)):
        return False

    was_enabled = bool(mod.get("enabled"))
    old_folder = mod.get("folder", "")
    try:
        if was_enabled:
            _apply_enable(mod, mods_path, False)
        mod["folder"] = desired_folder
        if was_enabled:
            _apply_enable(mod, mods_path, True)
        return True
    except OSError:
        # A pasta do jogo pode estar bloqueada pelo Steam/jogo. Nunca deixamos
        # o registro apontando para o destino novo se a cópia não terminou.
        mod["folder"] = old_folder
        if was_enabled:
            try:
                _apply_enable(mod, mods_path, True)
            except OSError:
                pass
        return False


@_serialized_files
def toggle_mod(mod_id):
    mods = storage.load_mods()
    settings = storage.load_settings()
    mods_path = settings.get("mods_path", "")

    for m in mods:
        if m["id"] == mod_id:
            new_state = not m["enabled"]
            disabled_conflicts = []
            # Mod indexado do jogo ainda não tem cópia de segurança. Antes de
            # desativá-lo, copiamos os arquivos ativos para o storage local.
            if not new_state and m.get("external"):
                backup_dir = _storage_dir(m, create=True)
                source_dir = os.path.join(mods_path, m["folder"])
                for f in m["files"]:
                    source = os.path.join(source_dir, f["name"])
                    if os.path.isfile(source):
                        shutil.copy2(source, os.path.join(backup_dir, f["name"]))
                m["external"] = False
            if m.get("install_target") == "marvel_content" and mods_path:
                # Um complemento é uma biblioteca de variações. Na primeira
                # ativação ele só deve expor suas prévias; cada cinematic é
                # escolhida individualmente pelo usuário depois disso.
                if new_state and m.get("parent_background_id") and not m.get("component_selection_initialized"):
                    for component in m.get("components", []):
                        component["enabled"] = False
                    m["component_selection_initialized"] = True
                m["enabled"] = new_state
                active_names = [
                    entry.get("name") for component in m.get("components", [])
                    if component.get("enabled", True)
                    for entry in component.get("files", []) if entry.get("name")
                ]
                disabled_conflicts = (_disable_background_conflicts(mods, m.get("id"), active_names)
                                      if new_state else [])
                _refresh_background_files(mods, mods_path, (entry.get("name") for entry in m.get("files", [])))
                _sync_background_audio_files(mods, mods_path)
            elif mods_path:
                _apply_enable(m, mods_path, new_state)
            m["enabled"] = new_state
            storage.save_mods(mods)
            _record_activity(
                "toggle_mod",
                f"{'Ativado' if new_state else 'Desativado'}: {m.get('name', 'Mod')}",
                {"mod_id": m.get("id"), "enabled": new_state},
            )
            return {"ok": True, "enabled": new_state, "disabled_conflicts": disabled_conflicts if m.get("install_target") == "marvel_content" else []}
    return {"ok": False, "error": "mod nao encontrado"}


@_serialized_files
def set_mods_enabled(mod_ids, enable):
    """Ativa/desativa vários mods em uma única gravação do catálogo."""
    wanted = {str(mod_id) for mod_id in (mod_ids or [])}
    if not wanted:
        return {"ok": False, "error": "Nenhum mod selecionado.", "changed": []}
    mods = storage.load_mods()
    settings = storage.load_settings()
    mods_path = settings.get("mods_path", "")
    before_snapshot = _snapshot_mod_states(mods)
    changed, errors = [], []

    for mod in mods:
        if mod.get("id") not in wanted or bool(mod.get("enabled")) == bool(enable):
            continue
        try:
            # Um mod descoberto diretamente na pasta do jogo precisa de cópia
            # local antes de ser desativado, exatamente como em toggle_mod.
            if not enable and mod.get("external"):
                backup_dir = _storage_dir(mod, create=True)
                source_dir = os.path.join(mods_path, mod.get("folder", ""))
                for entry in mod.get("files", []):
                    source = os.path.join(source_dir, entry.get("name", ""))
                    if os.path.isfile(source):
                        shutil.copy2(source, os.path.join(backup_dir, entry["name"]))
                mod["external"] = False
            if mods_path:
                _apply_enable(mod, mods_path, bool(enable))
            mod["enabled"] = bool(enable)
            changed.append(mod["id"])
        except OSError as exc:
            errors.append({"id": mod.get("id"), "name": mod.get("name", "Mod"), "error": str(exc)})

    if changed:
        storage.save_mods(mods)
        settings["last_recovery_snapshot"] = {
            "action": f"{'Ativar' if enable else 'Desativar'} {len(changed)} mod(s)",
            "created_at": storage.now_iso(),
            "mods": before_snapshot,
        }
        storage.save_settings(settings)
        _record_activity(
            "toggle_mods",
            f"{'Ativados' if enable else 'Desativados'} {len(changed)} mod(s)",
            {"mod_ids": changed, "enabled": bool(enable)},
        )
    return {"ok": not errors, "changed": changed, "errors": errors}


def set_manual_conflicts(mod_ids):
    """Registra um grupo de mods que o usuário sabe serem incompatíveis."""
    selected = list(dict.fromkeys(str(mod_id) for mod_id in (mod_ids or [])))
    if len(selected) < 2:
        return {"ok": False, "error": "Selecione pelo menos dois mods."}

    mods = storage.load_mods()
    by_id = {str(mod.get("id")): mod for mod in mods}
    selected = [mod_id for mod_id in selected if mod_id in by_id]
    if len(selected) < 2:
        return {"ok": False, "error": "Os mods selecionados não foram encontrados."}

    for mod_id in selected:
        mod = by_id[mod_id]
        others = {other_id for other_id in selected if other_id != mod_id}
        previous = {str(other_id) for other_id in mod.get("manual_conflicts", []) or []}
        mod["manual_conflicts"] = sorted(previous | others)

    storage.save_mods(mods)
    _record_activity("manual_conflict", f"Conflito manual marcado entre {len(selected)} mod(s)", {"mod_ids": selected})
    return {"ok": True, "marked": selected}


def _apply_component_states(mod, previous, mods_path):
    """Aplica somente componentes alterados, com restauração em caso de falha."""
    if not mods_path or not mod.get("enabled"):
        return
    _ensure_game_operation_allowed()
    old = {c["id"]: c for c in previous}
    changed = [c for c in mod.get("components", []) if c.get("enabled", True) != old[c["id"]].get("enabled", True)]
    target_dir, private_dir = _game_target_dir(mod, mods_path), _storage_dir(mod)
    if changed and mod.get("external"):
        # O scanner não cria biblioteca privada até a primeira alteração.
        # Guarde todos os pacotes antes de desativar uma alternativa externa.
        _preserve_external_mod_files(mod, mods_path)
        mod["external"] = False
    def apply(component, enabled):
        for entry in component.get("files", []):
            target = os.path.join(target_dir, entry["name"])
            if enabled:
                _install_file_fast(os.path.join(private_dir, entry["name"]), target)
            elif os.path.isfile(target):
                os.remove(target)
    # A variante desativada também precisa de fonte íntegra para a reversão
    # se uma cópia ou o salvamento do catálogo falhar mais adiante.
    for component in changed:
        if component.get("enabled", True) or old[component["id"]].get("enabled", True):
            for entry in component.get("files", []):
                if not os.path.isfile(os.path.join(private_dir, entry["name"])):
                    raise FileNotFoundError(f"Arquivo de componente ausente: {entry['name']}")
    touched = []
    try:
        for component in changed:
            touched.append(component)
            apply(component, component.get("enabled", True))
    except OSError:
        for component in reversed(touched):
            apply(component, old[component["id"]].get("enabled", True))
        raise


@_serialized_files
def set_component_rules(mod_id, component_id, exclusive_group="", requires=None):
    import copy
    mods = storage.load_mods()
    mod = next((m for m in mods if m.get("id") == mod_id), None)
    if not mod or mod.get("install_target"):
        return {"ok": False, "error": "Relações disponíveis apenas para componentes de PAKs."}
    previous = copy.deepcopy(mod.get("components", []))
    component = next((c for c in mod.get("components", []) if c["id"] == component_id), None)
    if not component:
        return {"ok": False, "error": "Componente não encontrado."}
    if not isinstance(requires or [], list) or not all(isinstance(value, str) for value in requires or []):
        return {"ok": False, "error": "Lista de dependências inválida."}
    component["exclusive_group"] = str(exclusive_group or "").strip()[:80]
    component["requires"] = list(dict.fromkeys(requires or []))
    applied = False
    mods_path = storage.load_settings().get("mods_path", "")
    try:
        mod["components"] = component_rules.changed_state(mod["components"], component_id, component.get("enabled", True))
        _apply_component_states(mod, previous, mods_path)
        applied = True
        storage.save_mods(mods)
    except (ValueError, OSError, storage.ConcurrentUpdateError) as error:
        if applied:
            attempted = mod["components"]
            mod["components"] = previous
            _apply_component_states(mod, attempted, mods_path)
        return {"ok": False, "error": str(error)}
    _record_activity("component_rules", f"Relações atualizadas: {component.get('name')}", {"mod_id": mod_id})
    from . import personal_corrections
    warnings = personal_corrections.remember_mod(mod, component_fields={component_id: ["exclusive_group", "requires"]})
    return {"ok": True, "warnings": warnings}


@_serialized_files
def toggle_component(mod_id, component_id):
    """Ativa/desativa somente um acompanhamento dentro de um mod instalado."""
    mods = storage.load_mods()
    settings = storage.load_settings()
    mods_path = settings.get("mods_path", "")
    mod = next((item for item in mods if item["id"] == mod_id), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}
    component = next((item for item in mod.get("components", []) if item["id"] == component_id), None)
    if not component:
        return {"ok": False, "error": "Componente não encontrado."}

    if mod.get("external") and mods_path and mod.get("install_target"):
        backup_dir = _storage_dir(mod, create=True)
        source_dir = os.path.join(mods_path, mod.get("folder", ""))
        for entry in mod.get("files", []):
            source = os.path.join(source_dir, entry["name"])
            if os.path.isfile(source):
                destination = os.path.join(backup_dir, entry["name"])
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                _install_file_fast(source, destination)
        mod["external"] = False
    new_state = not component.get("enabled", True)
    if not mod.get("install_target"):
        previous = mod["components"]
        applied = False
        try:
            mod["components"] = component_rules.changed_state(previous, component_id, new_state)
            _apply_component_states(mod, previous, mods_path)
            applied = True
            storage.save_mods(mods)
        except (ValueError, OSError, storage.ConcurrentUpdateError) as error:
            if applied:
                attempted = mod["components"]
                mod["components"] = previous
                _apply_component_states(mod, attempted, mods_path)
            return {"ok": False, "error": str(error)}
        _record_activity("toggle_component", f"Componente {'ativado' if new_state else 'desativado'}: {component.get('name')}",
                         {"mod_id": mod_id, "component_id": component_id})
        return {"ok": True, "enabled": new_state}
    component["enabled"] = new_state
    if mods_path and mod.get("enabled"):
        if mod.get("install_target") == "marvel_content":
            component_files = [entry.get("name") for entry in component.get("files", []) if entry.get("name")]
            disabled_conflicts = (_disable_background_conflicts(mods, mod.get("id"), component_files)
                                  if new_state else [])
            _refresh_background_files(mods, mods_path, component_files)
            _sync_background_audio_files(mods, mods_path)
            storage.save_mods(mods)
            _record_activity(
                "toggle_component",
                f"{'Ativado' if new_state else 'Desativado'} cinematic “{component.get('name', 'Cinematic')}”",
                {"mod_id": mod.get("id"), "component_id": component.get("id"), "enabled": new_state},
            )
            return {"ok": True, "enabled": new_state, "disabled_conflicts": disabled_conflicts}
        target_dir = _game_target_dir(mod, mods_path)
        storage_dir = _storage_dir(mod)
        if new_state:
            os.makedirs(target_dir, exist_ok=True)
            for entry in component.get("files", []):
                source = os.path.join(storage_dir, entry["name"])
                _install_file_fast(source, os.path.join(target_dir, entry["name"]))
        else:
            for entry in component.get("files", []):
                target = os.path.join(target_dir, entry["name"])
                if os.path.isfile(target):
                    os.remove(target)
    storage.save_mods(mods)
    _record_activity(
        "toggle_component",
        f"{'Ativado' if new_state else 'Desativado'} componente “{component.get('name', 'Componente')}” em {mod.get('name', 'Mod')}",
        {"mod_id": mod.get("id"), "component_id": component.get("id"), "enabled": new_state},
    )
    return {"ok": True, "enabled": new_state}


@_serialized_files
def disable_conflict_owner(mod_id, component_id):
    if component_id in {"whole-mod", "manual-conflict"}:
        return set_mods_enabled([mod_id], False)
    mod = next((m for m in storage.load_mods() if m.get("id") == mod_id), None)
    component = next((c for c in (mod or {}).get("components", []) if c.get("id") == component_id), None)
    if not component:
        return {"ok": False, "error": "Componente não encontrado."}
    return toggle_component(mod_id, component_id) if component.get("enabled", True) else {"ok": True}


def _background_audio_mods(parent_id, mods):
    return [item for item in mods if item.get("parent_background_id") == parent_id and item.get("background_audio")]


def _apply_background_audio_component(mod, component, mods_path, enable):
    """Instala/remove um único PAK de banco Wwise, sem tocar nos demais."""
    target_dir = _game_target_dir(mod, mods_path)
    source_dir = _storage_dir(mod)
    for entry in component.get("files", []):
        name = entry.get("name")
        if not name:
            continue
        target = os.path.join(target_dir, name)
        if enable:
            source = os.path.join(source_dir, name)
            if not os.path.isfile(source):
                raise OSError(f"Banco de áudio ausente na biblioteca: {name}")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            _install_file_fast(source, target)
        elif os.path.isfile(target):
            os.remove(target)


def _background_audio_component_needed(mods, audio_mod_id, audio_component_id):
    """Um banco só vai ao jogo se a cinematic que o usa estiver visível/ativa."""
    audio_mod = next((item for item in mods if item.get("id") == audio_mod_id), None)
    parent_id = (audio_mod or {}).get("parent_background_id")
    for background in mods:
        if background.get("install_target") != "marvel_content" or not background.get("enabled"):
            continue
        if background.get("id") != parent_id and background.get("parent_background_id") != parent_id:
            continue
        for cinematic in background.get("components", []):
            binding = cinematic.get("audio_binding") or {}
            if (cinematic.get("enabled", True)
                    and binding.get("mod_id") == audio_mod_id
                    and binding.get("component_id") == audio_component_id):
                return True
    return False


def _sync_background_audio_files(mods, mods_path):
    """Mantém no jogo somente áudios que têm uma cinematic ativa vinculada."""
    if not mods_path:
        return
    _ensure_game_operation_allowed()
    for audio_mod in (item for item in mods if item.get("background_audio")):
        for component in audio_mod.get("components", []):
            should_install = bool(component.get("enabled")) and _background_audio_component_needed(mods, audio_mod.get("id"), component.get("id"))
            _apply_background_audio_component(audio_mod, component, mods_path, should_install)


def _process_pending_background_audio_changes():
    """Aplica a fila persistente somente quando o jogo não bloqueia arquivos."""
    if _is_marvel_rivals_running():
        return 0
    with _BACKGROUND_AUDIO_QUEUE_LOCK:
        settings = storage.load_settings()
        pending = list(settings.get("pending_background_audio_changes") or [])
        if not pending:
            return 0
        mods = storage.load_mods()
        by_id = {item.get("id"): item for item in mods}
        remaining, applied = [], 0
        for request in pending:
            mod = by_id.get(request.get("mod_id"))
            component = next((item for item in (mod or {}).get("components", []) if item.get("id") == request.get("component_id")), None)
            try:
                if not mod or not component:
                    continue
                component["enabled"] = bool(request.get("enabled"))
                _apply_background_audio_component(mod, component, settings.get("mods_path", ""), bool(request.get("enabled")) and _background_audio_component_needed(mods, mod.get("id"), component.get("id")))
                component.pop("pending_enabled", None)
                mod["enabled"] = any(item.get("enabled") for item in mod.get("components", []))
                applied += 1
            except OSError:
                remaining.append(request)
        settings["pending_background_audio_changes"] = remaining
        storage.save_mods(mods)
        storage.save_settings(settings)
        return applied


def _start_background_audio_queue_worker():
    global _BACKGROUND_AUDIO_QUEUE_THREAD
    if _BACKGROUND_AUDIO_QUEUE_THREAD and _BACKGROUND_AUDIO_QUEUE_THREAD.is_alive():
        return
    def worker():
        global _BACKGROUND_AUDIO_QUEUE_THREAD
        for _ in range(60 * 60):
            if not _is_marvel_rivals_running():
                _process_pending_background_audio_changes()
                break
            time.sleep(2)
        _BACKGROUND_AUDIO_QUEUE_THREAD = None
    _BACKGROUND_AUDIO_QUEUE_THREAD = threading.Thread(target=worker, daemon=True, name="background-audio-queue")
    _BACKGROUND_AUDIO_QUEUE_THREAD.start()


def bind_background_audio(cinematic_mod_id, cinematic_component_id, audio_mod_id, audio_component_id):
    """Vincula explicitamente um banco Wwise a uma cinematic do mesmo perfil."""
    mods = storage.load_mods()
    cinematic_mod = next((item for item in mods if item.get("id") == cinematic_mod_id), None)
    audio_mod = next((item for item in mods if item.get("id") == audio_mod_id and item.get("background_audio")), None)
    cinematic = next((item for item in (cinematic_mod or {}).get("components", []) if item.get("id") == cinematic_component_id), None)
    audio = next((item for item in (audio_mod or {}).get("components", []) if item.get("id") == audio_component_id), None)
    parent_id = cinematic_mod.get("parent_background_id") if cinematic_mod else None
    parent_id = parent_id or (cinematic_mod or {}).get("id")
    if not cinematic_mod or cinematic_mod.get("install_target") != "marvel_content" or not cinematic:
        return {"ok": False, "error": "Cinematic não encontrada."}
    if not audio_mod or not audio or audio_mod.get("parent_background_id") != parent_id:
        return {"ok": False, "error": "Escolha um banco de áudio deste mesmo Background."}
    cinematic["audio_binding"] = {"mod_id": audio_mod_id, "component_id": audio_component_id}
    storage.save_mods(mods)
    return {"ok": True, "audio_name": audio_mod.get("name", "Áudio"), "bank_name": audio.get("name", "Banco")}


def unbind_background_audio(cinematic_mod_id, cinematic_component_id):
    """Remove apenas a associação visual; o banco continua na biblioteca."""
    mods = storage.load_mods()
    cinematic_mod = next((item for item in mods if item.get("id") == cinematic_mod_id), None)
    cinematic = next((item for item in (cinematic_mod or {}).get("components", []) if item.get("id") == cinematic_component_id), None)
    if not cinematic_mod or cinematic_mod.get("install_target") != "marvel_content" or not cinematic:
        return {"ok": False, "error": "Cinematic não encontrada."}
    cinematic.pop("audio_binding", None)
    storage.save_mods(mods)
    return {"ok": True}


def set_background_audio_enabled(mod_id, component_id, enable):
    """Liga/desliga um banco; durante a partida persiste a solicitação na fila."""
    mods = storage.load_mods()
    mod = next((item for item in mods if item.get("id") == mod_id and item.get("background_audio")), None)
    component = next((item for item in (mod or {}).get("components", []) if item.get("id") == component_id), None)
    if not mod or not component:
        return {"ok": False, "error": "Banco de áudio não encontrado."}
    enable = bool(enable)
    settings = storage.load_settings()
    if _is_marvel_rivals_running():
        queue = [item for item in settings.get("pending_background_audio_changes", [])
                 if not (item.get("mod_id") == mod_id and item.get("component_id") == component_id)]
        queue.append({"mod_id": mod_id, "component_id": component_id, "enabled": enable})
        settings["pending_background_audio_changes"] = queue
        component["pending_enabled"] = enable
        storage.save_mods(mods)
        storage.save_settings(settings)
        _start_background_audio_queue_worker()
        return {"ok": True, "enabled": component.get("enabled", False), "queued": True, "pending_enabled": enable}
    component["enabled"] = enable
    try:
        _apply_background_audio_component(mod, component, settings.get("mods_path", ""), enable and _background_audio_component_needed(mods, mod_id, component_id))
    except OSError as exc:
        component["enabled"] = not enable
        return {"ok": False, "error": str(exc)}
    component.pop("pending_enabled", None)
    mod["enabled"] = any(item.get("enabled") for item in mod.get("components", []))
    storage.save_mods(mods)
    _record_activity("toggle_background_audio", f"{'Ativado' if enable else 'Desativado'} áudio “{component.get('name', 'Banco')}”", {"mod_id": mod_id, "component_id": component_id, "enabled": enable})
    return {"ok": True, "enabled": enable}


def _extract_wems_from_bnk(bank_path, output_dir):
    """Extrai as mídias WEM embutidas no bloco DATA de um banco Wwise."""
    data = pathlib.Path(bank_path).read_bytes()
    offset, didx, data_chunk = 0, None, None
    while offset + 8 <= len(data):
        tag = data[offset:offset + 4]
        size = struct.unpack_from("<I", data, offset + 4)[0]
        payload = offset + 8
        if payload + size > len(data):
            break
        if tag == b"DIDX":
            didx = data[payload:payload + size]
        elif tag == b"DATA":
            data_chunk = data[payload:payload + size]
        offset = payload + size
    if not didx or not data_chunk or len(didx) < 12:
        return []
    outputs = []
    for index in range(0, len(didx) - 11, 12):
        wem_id, relative_offset, size = struct.unpack_from("<III", didx, index)
        wem_data = data_chunk[relative_offset:relative_offset + size]
        if len(wem_data) != size or not wem_data.startswith(b"RIFF"):
            continue
        output = os.path.join(output_dir, f"embedded_{wem_id}.wem")
        with open(output, "wb") as wem_file:
            wem_file.write(wem_data)
        outputs.append(output)
    return outputs


def _background_audio_archive_for_component(mod, component):
    """Resolve o PAK de origem do componente, inclusive em registros antigos."""
    storage_dir = _storage_dir(mod)
    archives = [item for item in mod.get("archives", []) if str(item).lower().endswith(".pak")]
    source_archive = component.get("source_archive")
    if source_archive:
        candidate = os.path.join(storage_dir, "Archive", source_archive)
        if os.path.isfile(candidate):
            return candidate
    component_file = str((component.get("files") or [{}])[0].get("name", ""))
    match = re.match(r"(?:Audio Components[\\/])?(\d+)_", component_file, re.IGNORECASE)
    if match:
        index = int(match.group(1)) - 1
        if 0 <= index < len(archives):
            candidate = os.path.join(storage_dir, archives[index])
            if os.path.isfile(candidate):
                return candidate
    return next((os.path.join(storage_dir, item) for item in archives if os.path.isfile(os.path.join(storage_dir, item))), None)


def _background_audio_display_name(mod, component):
    """Mantém o nome do PAK de origem visível no seletor de áudio."""
    component_file = str((component.get("files") or [{}])[0].get("name", ""))
    match = re.match(r"(?:Audio Components[\\/])?(\d+)_", component_file, re.IGNORECASE)
    archives = [item for item in mod.get("archives", []) if str(item).lower().endswith(".pak")]
    if match:
        index = int(match.group(1)) - 1
        if 0 <= index < len(archives):
            stem = pathlib.Path(archives[index]).stem
            if stem and not stem.casefold().startswith("edits"):
                return re.sub(r"_9999999_P$", "", stem, flags=re.IGNORECASE)
    return component.get("name", "Banco de áudio")


def get_background_audio_preview(mod_id, component_id):
    """Decodifica uma faixa WEM e devolve uma prévia tocável no WebView."""
    cli = _find_vgmstream_cli()
    if not cli:
        return {"ok": False, "error": "O leitor de áudio está ausente. Extraia novamente o pacote completo do CrabVault."}
    mod = next((item for item in storage.load_mods() if item.get("id") == mod_id and item.get("background_audio")), None)
    component = next((item for item in (mod or {}).get("components", []) if item.get("id") == component_id), None)
    if not mod or not component:
        return {"ok": False, "error": "Banco de áudio não encontrado."}
    archive = _background_audio_archive_for_component(mod, component)
    if not archive or not os.path.isfile(archive):
        return {"ok": False, "error": "O PAK original desse áudio não está na biblioteca."}
    preview_dir = os.path.join(_storage_dir(mod), "Audio Previews")
    os.makedirs(preview_dir, exist_ok=True)
    # O sufixo v2 invalida prévias antigas que usavam incorretamente o
    # primeiro WEM externo do pacote inteiro.
    wav_path = os.path.join(preview_dir, f"{component_id}-v2.wav")
    if not os.path.isfile(wav_path):
        temp_dir = tempfile.mkdtemp(prefix="marvel_manager_audio_preview_")
        try:
            extracted = subprocess.run([_UASSET_TOOL, "extract_pak", archive, temp_dir], env=_uassettool_environment(), capture_output=True, text=True, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            bank_name = component.get("audio_bank", "")
            bank = next((path for path in pathlib.Path(temp_dir).rglob("*.bnk") if path.name.casefold() == bank_name.casefold()), None)
            wems = _extract_wems_from_bnk(bank, temp_dir) if bank else []
            # Alguns bancos podem depender de WEM externos; este fallback só
            # é usado quando não houver mídia incorporada no banco escolhido.
            if not wems:
                fallback = next(iter(sorted(pathlib.Path(temp_dir).rglob("*.wem"), key=lambda path: path.name.casefold())), None)
                wems = [fallback] if fallback else []
            if not wems:
                return {"ok": False, "error": "Não encontrei uma faixa WEM nesse PAK para prévia."}
            decoded = None
            for wem in wems:
                decoded = subprocess.run([cli, "-i", "-o", wav_path, str(wem)], capture_output=True, text=True, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if decoded.returncode == 0 and os.path.isfile(wav_path):
                    break
            if not decoded or decoded.returncode != 0 or not os.path.isfile(wav_path):
                return {"ok": False, "error": "O vgmstream não conseguiu gerar a prévia do áudio."}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    with open(wav_path, "rb") as audio_file:
        data = base64.b64encode(audio_file.read()).decode("ascii")
    return {"ok": True, "data_url": f"data:audio/wav;base64,{data}"}


def remove_background_cinematic(mod_id, component_id):
    """Remove uma cinematic de um complemento, preservando os demais vídeos."""
    mods = storage.load_mods()
    settings = storage.load_settings()
    mods_path = settings.get("mods_path", "")
    mod = next((item for item in mods if item.get("id") == mod_id), None)
    if not mod or not mod.get("parent_background_id") or mod.get("install_target") != "marvel_content":
        return {"ok": False, "error": "Complemento de Background não encontrado."}
    component = next((item for item in mod.get("components", []) if item.get("id") == component_id), None)
    if not component:
        return {"ok": False, "error": "Cinematic não encontrada."}
    file_names = {entry.get("name") for entry in component.get("files", []) if entry.get("name")}
    if not file_names:
        return {"ok": False, "error": "A cinematic não possui arquivos para remover."}
    if mods_path and mod.get("enabled"):
        component["enabled"] = False
        _refresh_background_files(mods, mods_path, file_names)
    mod_dir = _storage_dir(mod)
    for name in file_names:
        path = os.path.join(mod_dir, name)
        if os.path.isfile(path):
            os.remove(path)
    mod["files"] = [entry for entry in mod.get("files", []) if entry.get("name") not in file_names]
    mod["components"] = [item for item in mod.get("components", []) if item.get("id") != component_id]
    storage.save_mods(mods)
    _record_activity(
        "remove_background_cinematic",
        f"Cinematic removida do complemento: {component.get('name', 'Cinematic')}",
        {"mod_id": mod_id, "component_id": component_id},
    )
    return {"ok": True, "removed": component.get("name", "Cinematic")}


def rename_component(mod_id, component_id, name):
    """Altera somente o nome exibido de um componente."""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "O nome do componente não pode ficar vazio."}
    mods = storage.load_mods()
    mod = next((item for item in mods if item["id"] == mod_id), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}
    component = next((item for item in mod.get("components", []) if item["id"] == component_id), None)
    if not component:
        return {"ok": False, "error": "Componente não encontrado."}
    component["name"] = name
    storage.save_mods(mods)
    from . import personal_corrections
    warnings = personal_corrections.remember_mod(mod, component_fields={component_id: ["name"]})
    return {"ok": True, "name": name, "warnings": warnings}


def move_component(mod_id, component_id, direction):
    """Move um componente uma posição na ordem exibida e de instalação."""
    if direction not in {"up", "down"}:
        return {"ok": False, "error": "Direção inválida."}
    mods = storage.load_mods()
    mod = next((item for item in mods if item["id"] == mod_id), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}
    components = mod.get("components", [])
    index = next((i for i, item in enumerate(components) if item.get("id") == component_id), None)
    if index is None:
        return {"ok": False, "error": "Componente não encontrado."}
    target_index = index - 1 if direction == "up" else index + 1
    if target_index < 0 or target_index >= len(components):
        return {"ok": False, "error": "O componente já está no limite da lista."}
    components[index], components[target_index] = components[target_index], components[index]
    # Não recolocamos Physics no final depois que o usuário escolheu uma ordem.
    mod["components_order_custom"] = True
    storage.save_mods(mods)
    return {"ok": True, "index": target_index}


def reorder_components(mod_id, component_ids):
    """Salva uma ordem completa recebida do arrastar-e-soltar da interface."""
    if not isinstance(component_ids, list):
        return {"ok": False, "error": "Ordem inválida."}
    mods = storage.load_mods()
    mod = next((item for item in mods if item["id"] == mod_id), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}
    components = mod.get("components", [])
    by_id = {item.get("id"): item for item in components}
    if len(component_ids) != len(components) or set(component_ids) != set(by_id):
        return {"ok": False, "error": "A lista de componentes foi alterada. Tente novamente."}
    mod["components"] = [by_id[component_id] for component_id in component_ids]
    mod["components_order_custom"] = True
    storage.save_mods(mods)
    return {"ok": True}


def move_components(mod_id, component_ids, direction):
    """Move um bloco de componentes selecionados, preservando sua ordem relativa."""
    if direction not in {"up", "down"} or not isinstance(component_ids, list):
        return {"ok": False, "error": "Movimento de componentes inválido."}
    selected = {str(component_id) for component_id in component_ids if component_id}
    if not selected:
        return {"ok": False, "error": "Selecione ao menos um componente."}
    mods = storage.load_mods()
    mod = next((item for item in mods if item.get("id") == mod_id), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}
    components = mod.get("components", [])
    present = {str(item.get("id")) for item in components if item.get("id")}
    selected &= present
    if not selected:
        return {"ok": False, "error": "Os componentes selecionados não foram encontrados."}

    if direction == "up":
        for index in range(1, len(components)):
            if str(components[index].get("id")) in selected and str(components[index - 1].get("id")) not in selected:
                components[index - 1], components[index] = components[index], components[index - 1]
    else:
        for index in range(len(components) - 2, -1, -1):
            if str(components[index].get("id")) in selected and str(components[index + 1].get("id")) not in selected:
                components[index], components[index + 1] = components[index + 1], components[index]
    mod["components_order_custom"] = True
    storage.save_mods(mods)
    return {"ok": True}


def set_component_description(mod_id, component_id, description):
    """Altera apenas o rótulo exibido abaixo do nome do componente."""
    description = (description or "").strip()
    if len(description) > 80:
        return {"ok": False, "error": "A descrição pode ter no máximo 80 caracteres."}
    mods = storage.load_mods()
    mod = next((item for item in mods if item["id"] == mod_id), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}
    component = next((item for item in mod.get("components", []) if item.get("id") == component_id), None)
    if not component:
        return {"ok": False, "error": "Componente não encontrado."}
    if description:
        component["description"] = description
        create_component_label(description)
    else:
        # Vazio restaura o texto automático Principal/Acompanhamento.
        component.pop("description", None)
    storage.save_mods(mods)
    from . import personal_corrections
    warnings = personal_corrections.remember_mod(mod, component_fields={component_id: ["description"]})
    return {"ok": True, "description": description, "warnings": warnings}


def set_components_description(mod_id, component_ids, description):
    """Aplica um mesmo rótulo a vários componentes de uma única vez."""
    if not isinstance(component_ids, list):
        return {"ok": False, "error": "Lista de componentes inválida."}
    description = (description or "").strip()
    if len(description) > 80:
        return {"ok": False, "error": "A descrição pode ter no máximo 80 caracteres."}
    selected = {str(component_id) for component_id in component_ids if component_id}
    if not selected:
        return {"ok": False, "error": "Selecione ao menos um componente."}
    mods = storage.load_mods()
    mod = next((item for item in mods if item.get("id") == mod_id), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}
    changed = 0
    for component in mod.get("components", []):
        if str(component.get("id")) not in selected:
            continue
        if description:
            component["description"] = description
        else:
            component.pop("description", None)
        changed += 1
    if not changed:
        return {"ok": False, "error": "Os componentes selecionados não foram encontrados."}
    if description:
        create_component_label(description)
    storage.save_mods(mods)
    from . import personal_corrections
    warnings = personal_corrections.remember_mod(mod, component_fields={cid: ["description"] for cid in selected})
    return {"ok": True, "description": description, "changed": changed, "warnings": warnings}


def _component_version_snapshot(component, mod=None):
    cache = (mod or {}).get("asset_path_cache", {}) if isinstance((mod or {}).get("asset_path_cache", {}), dict) else {}
    cached = cache.get(f"classification-v1:{component.get('id')}", {})
    return {
        "id": storage.new_id(),
        "saved_at": storage.now_iso(),
        "files": copy.deepcopy(component.get("files", [])),
        "type": component.get("type", "Unknown"),
        "types": copy.deepcopy(component.get("types") or [component.get("type", "Unknown")]),
        "source_archive": component.get("source_archive", "Origem não registrada"),
        "added_at": component.get("added_at"),
        "updated_at": component.get("updated_at"),
        "size_bytes": int(component.get("size_bytes", 0) or sum(int(entry.get("size", 0) or 0) for entry in component.get("files", []))),
        "content_sha256": component.get("content_sha256") or _component_content_hash(component),
        "asset_paths": copy.deepcopy(cached.get("paths", [])) if isinstance(cached, dict) else [],
    }


def _recompute_current_mod_types(mod):
    types = _ordered_component_types(
        value for component in mod.get("components", [])
        for value in (component.get("types") or [component.get("type") or "Unknown"])
        if value and value != "Unknown"
    )
    mod["types"], mod["type"] = types, types[0]
    mod["size_mb"] = round(sum(int(entry.get("size", 0) or 0) for entry in _all_mod_file_entries(mod)) / (1024 * 1024), 2)


def _active_component_file_names(mod):
    if not mod.get("enabled"):
        return set()
    return {entry.get("name") for component in mod.get("components", []) if component.get("enabled", True)
            for entry in component.get("files", []) if entry.get("name")}


def _commit_component_catalog_change(mods, before, after, title, action, metadata=None):
    """Confirma catálogo e arquivos ativos como uma única alteração recuperável."""
    settings = storage.load_settings()
    mods_path = settings.get("mods_path", "")
    before_active, after_active = _active_component_file_names(before), _active_component_file_names(after)
    removed, added = before_active - after_active, after_active - before_active
    journal = operation_recovery.Journal.create(
        "component_edit", title, before_records=[before], after_records=[after], mods_path=mods_path,
    )
    journal.data["mods_path"] = os.path.realpath(mods_path) if mods_path else ""
    journal.save()
    try:
        targets = []
        if mods_path:
            root = _game_target_dir(before, mods_path)
            for name in sorted(removed | added):
                targets.append((os.path.join(root, _safe_relative_file_path(name)), mods_path))
        journal.capture_files(targets)
        if mods_path and (removed or added):
            _ensure_game_operation_allowed()
        operation_jobs.begin_commit("Aplicando alteração do componente…")
        journal.mark("applying")
        if mods_path:
            target_root = _game_target_dir(after, mods_path)
            for name in removed:
                destination = os.path.join(target_root, _safe_relative_file_path(name))
                if os.path.isfile(destination):
                    os.remove(destination)
            private_root = _storage_dir(after)
            for name in added:
                relative = _safe_relative_file_path(name)
                _install_file_fast(os.path.join(private_root, relative), os.path.join(target_root, relative))
        index = next((position for position, item in enumerate(mods)
                      if str(item.get("id")) == str(before.get("id"))), None)
        if index is None:
            raise ValueError("O mod foi removido durante a operação.")
        mods[index] = after
        storage.save_mods(mods)
        journal.mark("catalog_saved")
        journal.finish("completed")
    except Exception as exc:
        try:
            operation_recovery.rollback(journal)
        except Exception as recovery_error:
            journal.fail(f"{exc} — Recuperação pendente: {recovery_error}")
            raise OSError(f"{exc} A operação ficou disponível para recuperação nas configurações.") from exc
        raise
    try:
        _record_activity(action, title, metadata or {"mod_id": after.get("id")})
    except Exception:
        pass
    return after


def preview_remove_component(mod_id, component_id):
    mod = next((item for item in storage.load_mods() if str(item.get("id")) == str(mod_id)), None)
    component = next((item for item in (mod or {}).get("components", [])
                      if str(item.get("id")) == str(component_id)), None)
    if not mod or not component:
        return {"ok": False, "error": "Componente não encontrado."}
    dependents = [item.get("name", "Componente") for item in mod.get("components", [])
                  if component_id in (item.get("requires") or [])]
    return {"ok": True, "name": component.get("name", "Componente"),
            "can_remove": len(mod.get("components", [])) > 1 and not dependents,
            "last_component": len(mod.get("components", [])) <= 1,
            "dependents": dependents, "enabled": bool(component.get("enabled"))}


@_serialized_files
def remove_component(mod_id, component_id):
    mods = storage.load_mods()
    before = next((copy.deepcopy(item) for item in mods if str(item.get("id")) == str(mod_id)), None)
    if not before:
        return {"ok": False, "error": "Mod não encontrado."}
    preview = preview_remove_component(mod_id, component_id)
    if not preview.get("can_remove"):
        if preview.get("last_component"):
            return {"ok": False, "error": "O último componente não pode ser removido. Remova o mod inteiro se necessário."}
        return {"ok": False, "error": "Remova primeiro as dependências: " + ", ".join(preview.get("dependents", []))}
    after = copy.deepcopy(before)
    index = next(position for position, item in enumerate(after.get("components", []))
                 if str(item.get("id")) == str(component_id))
    component = after["components"].pop(index)
    component_names = {entry.get("name") for entry in component.get("files", [])}
    after["files"] = [entry for entry in after.get("files", []) if entry.get("name") not in component_names]
    after.setdefault("removed_components", []).append({
        "id": storage.new_id(), "removed_at": storage.now_iso(), "index": index,
        "component": component,
    })
    _recompute_current_mod_types(after)
    try:
        saved = _commit_component_catalog_change(
            mods, before, after, f"Componente removido: {component.get('name', 'Componente')}",
            "remove_component", {"mod_id": mod_id, "component_id": component_id},
        )
        return {"ok": True, "removed_id": component_id,
                "removed_versions": len(saved.get("removed_components", []))}
    except (OSError, ValueError, storage.ConcurrentUpdateError) as error:
        return {"ok": False, "error": str(error)}


@_serialized_files
def restore_removed_component(mod_id, removed_id):
    mods = storage.load_mods()
    before = next((copy.deepcopy(item) for item in mods if str(item.get("id")) == str(mod_id)), None)
    if not before:
        return {"ok": False, "error": "Mod não encontrado."}
    after = copy.deepcopy(before)
    removed_index = next((position for position, item in enumerate(after.get("removed_components", []))
                          if str(item.get("id")) == str(removed_id)), None)
    if removed_index is None:
        return {"ok": False, "error": "Componente removido não encontrado."}
    removed = after["removed_components"].pop(removed_index)
    component = removed.get("component", {})
    if any(str(item.get("id")) == str(component.get("id")) for item in after.get("components", [])):
        return {"ok": False, "error": "Já existe um componente com essa identidade."}
    private = _storage_dir(after)
    if any(not os.path.isfile(os.path.join(private, _safe_relative_file_path(entry.get("name", ""))))
           for entry in component.get("files", [])):
        return {"ok": False, "error": "Os arquivos privados deste componente não estão mais disponíveis."}
    position = max(0, min(int(removed.get("index", len(after.get("components", [])))), len(after.get("components", []))))
    after.setdefault("components", []).insert(position, component)
    after.setdefault("files", []).extend(copy.deepcopy(component.get("files", [])))
    restored_disabled = False
    try:
        component_rules.assert_valid_state(after.get("components", []))
    except ValueError:
        component["enabled"] = False
        restored_disabled = True
    _recompute_current_mod_types(after)
    try:
        _commit_component_catalog_change(
            mods, before, after, f"Componente restaurado: {component.get('name', 'Componente')}",
            "restore_component", {"mod_id": mod_id, "component_id": component.get("id")},
        )
        return {"ok": True, "component_id": component.get("id"), "restored_disabled": restored_disabled}
    except (OSError, ValueError, storage.ConcurrentUpdateError) as error:
        return {"ok": False, "error": str(error)}


@_serialized_files
def promote_added_component_to_update(mod_id, added_component_id, target_component_id):
    mods = storage.load_mods()
    before = next((copy.deepcopy(item) for item in mods if str(item.get("id")) == str(mod_id)), None)
    if not before:
        return {"ok": False, "error": "Mod não encontrado."}
    after = copy.deepcopy(before)
    added = next((item for item in after.get("components", []) if str(item.get("id")) == str(added_component_id)), None)
    target = next((item for item in after.get("components", []) if str(item.get("id")) == str(target_component_id)), None)
    if not added or not target or added is target:
        return {"ok": False, "error": "Os componentes da atualização não foram encontrados."}
    if added.get("enabled"):
        return {"ok": False, "error": "A nova variante precisa estar desativada antes de substituir outra."}
    old_files = copy.deepcopy(target.get("files", []))
    added_files = copy.deepcopy(added.get("files", []))
    versions = copy.deepcopy(target.get("versions", []))
    versions.append(_component_version_snapshot(target, after))
    for key in ("files", "type", "types", "source_archive", "added_at", "size_bytes", "content_sha256"):
        if key in added:
            target[key] = copy.deepcopy(added[key])
    target["updated_at"] = storage.now_iso()
    target["versions"] = versions
    after["components"] = [item for item in after.get("components", []) if item is not added]
    replaced_names = {entry.get("name") for entry in [*old_files, *added_files]}
    after["files"] = [entry for entry in after.get("files", []) if entry.get("name") not in replaced_names]
    after["files"].extend(added_files)
    cache = after.setdefault("asset_path_cache", {})
    new_cache = cache.get(f"classification-v1:{added_component_id}")
    cache.pop(f"classification-v1:{target_component_id}", None)
    cache.pop(f"classification-v1:{added_component_id}", None)
    if new_cache:
        cache[f"classification-v1:{target_component_id}"] = new_cache
    _recompute_current_mod_types(after)
    try:
        saved = _commit_component_catalog_change(
            mods, before, after, f"Componente atualizado: {target.get('name', 'Componente')}",
            "update_component", {"mod_id": mod_id, "component_id": target_component_id},
        )
        return {"ok": True, "component_id": target_component_id,
                "versions": len(next(item for item in saved["components"] if item["id"] == target_component_id).get("versions", []))}
    except (OSError, ValueError, storage.ConcurrentUpdateError) as error:
        return {"ok": False, "error": str(error)}


@_serialized_files
def restore_component_version(mod_id, component_id, version_id):
    mods = storage.load_mods()
    before = next((copy.deepcopy(item) for item in mods if str(item.get("id")) == str(mod_id)), None)
    if not before:
        return {"ok": False, "error": "Mod não encontrado."}
    after = copy.deepcopy(before)
    component = next((item for item in after.get("components", []) if str(item.get("id")) == str(component_id)), None)
    if not component:
        return {"ok": False, "error": "Componente não encontrado."}
    versions = list(component.get("versions", []))
    version_index = next((position for position, item in enumerate(versions)
                          if str(item.get("id")) == str(version_id)), None)
    if version_index is None:
        return {"ok": False, "error": "Versão anterior não encontrada."}
    chosen = versions.pop(version_index)
    private = _storage_dir(after)
    if any(not os.path.isfile(os.path.join(private, _safe_relative_file_path(entry.get("name", ""))))
           for entry in chosen.get("files", [])):
        return {"ok": False, "error": "Os arquivos desta versão não estão mais disponíveis."}
    current = _component_version_snapshot(component, after)
    old_names = {entry.get("name") for entry in component.get("files", [])}
    new_files = copy.deepcopy(chosen.get("files", []))
    component["files"] = new_files
    component["type"] = chosen.get("type", "Unknown")
    component["types"] = copy.deepcopy(chosen.get("types") or [component["type"]])
    for key in ("source_archive", "added_at", "updated_at", "size_bytes", "content_sha256"):
        if key in chosen:
            component[key] = copy.deepcopy(chosen[key])
    component["versions"] = [*versions, current]
    after["files"] = [entry for entry in after.get("files", []) if entry.get("name") not in old_names]
    after["files"].extend(new_files)
    after.setdefault("asset_path_cache", {}).pop(f"classification-v1:{component_id}", None)
    _recompute_current_mod_types(after)
    try:
        _commit_component_catalog_change(
            mods, before, after, f"Versão restaurada: {component.get('name', 'Componente')}",
            "restore_component_version", {"mod_id": mod_id, "component_id": component_id, "version_id": version_id},
        )
        return {"ok": True, "component_id": component_id, "versions": len(component.get("versions", []))}
    except (OSError, ValueError, storage.ConcurrentUpdateError) as error:
        return {"ok": False, "error": str(error)}


# ---------------------------------------------------------------------------
# Adicionar mod
# ---------------------------------------------------------------------------
def prepare_mod_import(filepaths, labels=None):
    """Plano privado da importação: cada trio possui nomes relativos exclusivos."""
    labels = labels or {}
    groups = {}
    for source in dict.fromkeys(os.path.abspath(path) for path in filepaths):
        key = os.path.normcase(os.path.splitext(source)[0])
        groups.setdefault(key, []).append(source)
    components, sources = [], {}
    total_bytes = sum(os.path.getsize(source) for group in groups.values() for source in group)
    hashed_bytes = 0
    for group_index, group in enumerate(groups.values()):
        operation_jobs.check()
        component_id = storage.new_id()
        name = labels.get(os.path.normcase(group[0])) or pathlib.Path(group[0]).stem
        if not labels.get(os.path.normcase(group[0])) and sum(
                pathlib.Path(items[0]).stem.casefold() == pathlib.Path(group[0]).stem.casefold() for items in groups.values()) > 1:
            name = pathlib.Path(group[0]).parent.name + " · " + name
        entries = []
        for source in group:
            relative = os.path.join("Components", component_id, os.path.basename(source))
            if relative.casefold() in {value.casefold() for value in sources}:
                raise ValueError("O mesmo componente contém arquivos com nomes equivalentes.")
            sources[relative] = source
            digest = operation_jobs.hash_file(source, completed=hashed_bytes, total=total_bytes)
            hashed_bytes += os.path.getsize(source)
            entries.append({"name": relative, "original_name": os.path.basename(source),
                            "size": os.path.getsize(source), "sha256": digest})
        operation_jobs.progress("analyzing", f"Analisando componente {group_index + 1}/{len(groups)}: {name}",
                                group_index, len(groups))
        paths = _paths_from_bundle(group)
        types = _classify_component({"name": name, "files": entries, "asset_paths": paths})
        character, skin = _identity_from_asset_paths(paths)
        components.append({"id": component_id, "name": name, "files": entries,
                           "type": types[0], "types": types, "enabled": not labels or not components,
                           "asset_paths": paths, "suggested_character": character, "suggested_skin": skin})
    return {"components": components, "sources": sources}


def describe_mod_import(plan, archives):
    """Prévia sem caminhos privados: duplicatas são avisos, nunca exclusões."""
    def fingerprint(entries):
        return tuple(sorted((pathlib.Path(e["name"]).suffix.lower(), e.get("size"), e.get("sha256")) for e in entries))
    known = {}
    wanted_names = {tuple(sorted(e["original_name"].casefold() for e in c["files"])) for c in plan["components"]}
    for mod in storage.load_mods():
        for component in mod.get("components", []):
            entries = component.get("files", [])
            if not entries:
                continue
            if not all(e.get("sha256") for e in entries):
                if tuple(sorted(pathlib.Path(e["name"]).name.casefold() for e in entries)) not in wanted_names:
                    continue
                paths = _component_source_files(mod, component, _mod_source_files(mod))
                if len(paths) != len(entries):
                    continue
                entries = []
                for path in paths:
                    with open(path, "rb") as stream:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    entries.append({"name": path, "size": os.path.getsize(path), "sha256": digest})
            known.setdefault(fingerprint(entries), []).append(mod.get("name", "Mod"))
    names = {}
    for c in plan["components"]:
        for entry in c["files"]:
            names[entry["original_name"].casefold()] = names.get(entry["original_name"].casefold(), 0) + 1
    components = []
    for c in plan["components"]:
        key = fingerprint(c["files"])
        components.append({"id": c["id"], "name": c["name"], "types": c["types"], "enabled": c["enabled"],
                           "character": c.get("suggested_character"), "skin": c.get("suggested_skin"),
                           "files": [e["original_name"] for e in c["files"]],
                           "size_mb": round(sum(e["size"] for e in c["files"])/(1024*1024), 2),
                           "duplicate_of": list(known.get(key, [])),
                           "same_names": any(names[e["original_name"].casefold()] > 1 for e in c["files"])})
        known.setdefault(key, []).append(c["name"] + " (nesta seleção)")
    return {"archives": [os.path.basename(path) for path in archives], "components": components}


def validate_component_append_target(mod_id):
    """Confirma que o registro aceita novos componentes PAK isolados."""
    mod = next((item for item in storage.load_mods() if str(item.get("id")) == str(mod_id)), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}
    if mod.get("install_target") or mod.get("background_audio"):
        return {"ok": False, "error": "Este tipo de mod usa um fluxo próprio de complementos."}
    if mod.get("external"):
        return {"ok": False, "error": "Este mod precisa estar guardado na biblioteca antes de receber variantes."}
    if not os.path.isdir(_storage_dir(mod)):
        return {"ok": False, "error": "A cópia privada deste mod não foi encontrada."}
    return {"ok": True, "name": mod.get("name", "Mod")}


def _component_payload_fingerprint(component):
    entries = component.get("files", []) if isinstance(component, dict) else []
    if not entries or any(not entry.get("sha256") for entry in entries):
        return None
    return tuple(sorted((pathlib.Path(str(entry.get("name", ""))).suffix.lower(),
                         int(entry.get("size", 0) or 0), str(entry.get("sha256")))
                        for entry in entries))


def _component_content_hash(component):
    digests = sorted(str(entry.get("sha256")) for entry in component.get("files", []) if entry.get("sha256"))
    return hashlib.sha256("\n".join(digests).encode("ascii")).hexdigest() if digests else ""


def _apply_component_origin(component, archive_paths, added_at=None):
    component["added_at"] = added_at or storage.now_iso()
    component["size_bytes"] = sum(int(entry.get("size", 0) or 0) for entry in component.get("files", []))
    component["content_sha256"] = _component_content_hash(component)
    sources = [os.path.basename(path) for path in archive_paths or [] if path]
    component["source_archive"] = ", ".join(dict.fromkeys(sources)) if sources else "Arquivos selecionados"


def _component_asset_paths_for_suggestion(mod, component):
    paths, _ = _component_cached_asset_paths(mod, component)
    return {str(path).replace("\\", "/").casefold() for path in paths if path}


def _component_update_suggestions(mod, new_components, explicit_target=None):
    existing = list(mod.get("components", []))
    if explicit_target:
        target = next((item for item in existing if str(item.get("id")) == str(explicit_target)), None)
        if not target:
            raise ValueError("O componente escolhido para atualização não foi encontrado.")
        if len(new_components) != 1:
            raise ValueError("Para atualizar um componente, selecione apenas um pacote ou variante.")
        return [{"new_component_id": new_components[0]["id"], "target_component_id": target["id"],
                 "target_name": target.get("name", "Componente"), "score": 1.0,
                 "reason": "Componente escolhido pelo usuário."}]
    suggestions = []
    for new in new_components:
        new_paths = _component_asset_paths_for_suggestion({"components": [new]}, new)
        new_name = re.sub(r"[^a-z0-9]+", "", str(new.get("name", "")).casefold())
        best = None
        for candidate in existing:
            candidate_paths = _component_asset_paths_for_suggestion(mod, candidate)
            overlap = (len(new_paths & candidate_paths) / max(1, min(len(new_paths), len(candidate_paths)))
                       if new_paths and candidate_paths else 0.0)
            candidate_name = re.sub(r"[^a-z0-9]+", "", str(candidate.get("name", "")).casefold())
            name_score = difflib.SequenceMatcher(None, new_name, candidate_name).ratio() if new_name and candidate_name else 0.0
            score = max(overlap, name_score * 0.7)
            reason = (f"{round(overlap * 100)}% dos assets internos coincidem."
                      if overlap >= 0.5 else "Os nomes dos componentes são semelhantes.")
            if score >= 0.58 and (best is None or score > best[0]):
                best = (score, candidate, reason)
        if best:
            suggestions.append({"new_component_id": new["id"], "target_component_id": best[1]["id"],
                                "target_name": best[1].get("name", "Componente"),
                                "score": round(best[0], 3), "reason": best[2]})
    return suggestions


def _journal_storage_file_targets(records):
    """Arquivos privados permitidos na recuperação de anexos de componentes."""
    targets = []
    for mod in records:
        private_dir = _storage_dir(mod)
        for entry in _all_mod_file_entries(mod):
            relative = _safe_relative_file_path(entry.get("name", ""))
            targets.append((os.path.join(private_dir, relative), storage.STORAGE_DIR))
        for archive in mod.get("archives", []) or []:
            relative = _safe_relative_file_path(archive)
            targets.append((os.path.join(private_dir, relative), storage.STORAGE_DIR))
    return targets


@_serialized_files
def add_mod_components(mod_id, filepaths, meta):
    """Anexa variantes a um mod existente sem alterar seus componentes ativos."""
    if not filepaths:
        raise ValueError("Nenhum arquivo de componente foi selecionado.")
    settings = storage.load_settings()
    mods = storage.load_mods()
    target = next((item for item in mods if str(item.get("id")) == str(mod_id)), None)
    validation = validate_component_append_target(mod_id)
    if not validation.get("ok") or not target:
        raise ValueError(validation.get("error") or "Mod não encontrado.")
    journal = meta.get("_operation_journal")
    if not isinstance(journal, operation_recovery.Journal):
        journal = operation_recovery.Journal.create(
            "component_append", f"Adicionar componentes: {target.get('name', 'Mod')}",
            mods_path=settings.get("mods_path", ""),
        )
    journal.data["mods_path"] = os.path.realpath(settings.get("mods_path", "")) if settings.get("mods_path") else ""
    journal.save()
    try:
        return _add_mod_components_with_journal(mods, target, filepaths, meta, journal)
    except Exception as exc:
        try:
            operation_recovery.rollback(journal)
        except Exception as recovery_error:
            journal.fail(f"{exc} — Recuperação pendente: {recovery_error}")
            raise OSError(f"{exc} A operação ficou disponível para recuperação nas configurações.") from exc
        raise


def _add_mod_components_with_journal(mods, target, filepaths, meta, journal):
    plan = meta.get("_import_plan") or prepare_mod_import(filepaths, meta.get("component_labels"))
    existing_fingerprints = {
        fingerprint for fingerprint in
        (_component_payload_fingerprint(component) for component in target.get("components", []))
        if fingerprint
    }
    components, skipped = [], 0
    for component in copy.deepcopy(plan.get("components", [])):
        fingerprint = _component_payload_fingerprint(component)
        if fingerprint and fingerprint in existing_fingerprints:
            skipped += 1
            continue
        if fingerprint:
            existing_fingerprints.add(fingerprint)
        component["enabled"] = False
        _apply_component_origin(component, meta.get("source_archive_names") or meta.get("archive_paths") or [])
        components.append(component)
    if not components:
        raise ValueError("Todos os componentes selecionados já existem neste mod.")

    files = [entry for component in components for entry in component.get("files", [])]
    selected_names = {entry["name"] for entry in files}
    payload_dir = journal.stage_dir("payload")
    total_copy_bytes = sum(int(entry.get("size", 0) or 0) for entry in files)
    total_copy_bytes += sum(os.path.getsize(path) for path in meta.get("archive_paths", []) or []
                            if path and os.path.isfile(path))
    copied_bytes = 0
    for entry in files:
        source = plan.get("sources", {}).get(entry["name"])
        if not source or entry["name"] not in selected_names:
            raise ValueError("O plano da importação perdeu um arquivo de componente.")
        destination = os.path.join(payload_dir, _safe_relative_file_path(entry["name"]))
        copied_bytes += operation_jobs.copy_file(
            source, destination, completed=copied_bytes, total=total_copy_bytes,
            expected_hash=entry.get("sha256"),
        )

    archive_names = []
    for index, archive_path in enumerate(meta.get("archive_paths", []) or []):
        if not archive_path or not os.path.isfile(archive_path):
            continue
        archive_name = _safe_storage_segment(os.path.basename(archive_path), "source.archive")
        relative = os.path.join("Archive", "Additions", journal.id, str(index + 1), archive_name)
        copied_bytes += operation_jobs.copy_file(
            archive_path, os.path.join(payload_dir, relative),
            completed=copied_bytes, total=total_copy_bytes,
        )
        archive_names.append(relative)

    classification = {"id": target.get("id"), "files": files, "components": components,
                      "asset_path_cache": {}}
    staged_files = [os.path.join(payload_dir, entry["name"]) for entry in files]
    _analyze_mod_components(classification, staged_files)
    suggestion_mod = copy.deepcopy(target)
    suggestion_mod.setdefault("asset_path_cache", {}).update(classification.get("asset_path_cache", {}))
    suggestions = _component_update_suggestions(
        suggestion_mod, components, explicit_target=meta.get("target_component_id")
    )
    for component in components:
        component.pop("asset_paths", None)

    before = copy.deepcopy(target)
    after = copy.deepcopy(target)
    after.setdefault("components", []).extend(components)
    after.setdefault("files", []).extend(files)
    after.setdefault("archives", []).extend(archive_names)
    after.setdefault("asset_path_cache", {}).update(classification.get("asset_path_cache", {}))
    after["size_mb"] = round(float(after.get("size_mb", 0) or 0)
                             + sum(int(entry.get("size", 0) or 0) for entry in files) / (1024 * 1024), 2)
    _update_mod_component_types(after)

    private_dir = _storage_dir(target)
    new_relative_names = [entry["name"] for entry in files] + archive_names
    storage_targets = []
    for relative in new_relative_names:
        checked = _safe_relative_file_path(relative)
        destination = operation_recovery._inside(os.path.join(private_dir, checked), storage.STORAGE_DIR)
        if os.path.lexists(destination):
            raise FileExistsError(f"Já existe um arquivo privado com este destino: {relative}")
        storage_targets.append((destination, storage.STORAGE_DIR))

    journal.set_records([before], [after])
    journal.capture_files(storage_targets)
    operation_jobs.begin_commit("Salvando os novos componentes na biblioteca…")
    journal.mark("applying")
    for relative in new_relative_names:
        source = operation_recovery._inside(os.path.join(payload_dir, _safe_relative_file_path(relative)), payload_dir)
        destination = operation_recovery._inside(os.path.join(private_dir, _safe_relative_file_path(relative)), storage.STORAGE_DIR)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(source, destination)

    index = next((position for position, item in enumerate(mods)
                  if str(item.get("id")) == str(target.get("id"))), None)
    if index is None:
        raise ValueError("O mod foi removido durante a operação.")
    mods[index] = after
    storage.save_mods(mods)
    journal.mark("catalog_saved")
    journal.finish("completed")
    try:
        _record_activity(
            "add_mod_components", f"Adicionados {len(components)} componente(s): {after.get('name', 'Mod')}",
            {"mod_id": after.get("id"), "added": len(components), "skipped_duplicates": skipped},
        )
    except Exception:
        # Os arquivos e o catálogo já foram confirmados; histórico é secundário.
        pass
    after["added_components"] = len(components)
    after["skipped_duplicates"] = skipped
    after["added_component_ids"] = [component["id"] for component in components]
    after["suggested_updates"] = suggestions
    return after


@_serialized_files
def add_mod(filepaths, meta):
    if not filepaths:
        raise ValueError("Nenhum arquivo de mod foi selecionado.")
    settings = storage.load_settings()
    journal = meta.get("_operation_journal")
    if not isinstance(journal, operation_recovery.Journal):
        journal = operation_recovery.Journal.create("import", f"Importar: {meta.get('name') or 'Mod'}",
                                                    mods_path=settings.get("mods_path", ""))
    journal.data["mods_path"] = os.path.realpath(settings["mods_path"]) if settings.get("mods_path") else ""
    journal.save()
    try:
        record = _add_mod_with_journal(filepaths, meta, journal)
    except Exception as exc:
        try:
            if journal.data.get("mutation_started") and journal.data.get("mods_path"):
                _ensure_game_operation_allowed()
            operation_recovery.rollback(journal)
        except Exception as recovery_error:
            journal.fail(f"{exc} — Recuperação pendente: {recovery_error}")
            raise OSError(f"{exc} A operação ficou disponível para recuperação nas configurações.") from exc
        raise
    if meta.get("personal_correction_choice"):
        from . import personal_corrections
        warnings = personal_corrections.remember_mod(record)
        if warnings:
            record.setdefault("warnings", []).extend(warnings)
    return record


def _add_mod_with_journal(filepaths, meta, journal):
    """
    filepaths: lista de caminhos absolutos (escolhidos no dialogo nativo)
    meta: dict vindo do JS -> name, character, skin, link, folder, image_path
    O 'type' NAO vem do usuario, e detectado automaticamente pelos arquivos.
    """
    settings = storage.load_settings()
    mods_path = settings.get("mods_path", "")

    plan = meta.get("_import_plan") or prepare_mod_import(filepaths, meta.get("component_labels"))
    if meta.get("personal_correction_choice"):
        from . import personal_corrections
        plan, meta = personal_corrections.apply_import_choice(plan, meta)
    mod_id = storage.new_id()
    storage_folder = os.path.join(
        _safe_storage_segment(meta.get("character"), "Generic"),
        _safe_storage_segment(meta.get("skin"), "Default"),
        f"{_safe_storage_segment(meta.get('name') or os.path.splitext(os.path.basename(filepaths[0]))[0], 'Mod')} [{mod_id}]",
    )
    final_dir = os.path.join(storage.STORAGE_DIR, storage_folder)
    journal.own_storage_dir(final_dir)
    dest_dir = journal.stage_dir("payload")
    journal.mark("copying")

    components = copy.deepcopy(plan["components"])
    component_added_at = storage.now_iso()
    for component in components:
        _apply_component_origin(
            component, meta.get("source_archive_names") or meta.get("archive_paths") or [], component_added_at,
        )
    selected = meta.get("enabled_component_ids")
    if selected is not None:
        known_ids = {component["id"] for component in components}
        if not isinstance(selected, list) or not set(selected) <= known_ids:
            raise ValueError("A seleção de componentes da importação é inválida.")
        for component in components:
            component["enabled"] = component["id"] in selected
    files = [entry for component in components for entry in component["files"]]
    image_paths = meta.get("image_paths") or ([] if not meta.get("image_path") else [meta["image_path"]])
    total_copy_bytes = sum(entry["size"] for entry in files) + sum(
        os.path.getsize(path) for path in [*(meta.get("archive_paths") or []), *image_paths]
        if path and os.path.isfile(path))
    copied_bytes = 0
    total_size = 0
    for entry in files:
        dst = os.path.join(dest_dir, entry["name"])
        copied_bytes += operation_jobs.copy_file(plan["sources"][entry["name"]], dst,
                                                 completed=copied_bytes, total=total_copy_bytes,
                                                 expected_hash=entry["sha256"])
        total_size += os.path.getsize(dst)

    # Preserva o ZIP/RAR original analisado. Os arquivos extraídos continuam
    # na raiz do backup para ativar/desativar o mod normalmente.
    archive_names = []
    for archive_index, archive_path in enumerate(meta.get("archive_paths") or []):
        if not archive_path or not os.path.isfile(archive_path):
            continue
        archive_name = _safe_storage_segment(os.path.basename(archive_path), "source.archive")
        archive_dir = os.path.join(dest_dir, "Archive", str(archive_index + 1))
        os.makedirs(archive_dir, exist_ok=True)
        copied_bytes += operation_jobs.copy_file(archive_path, os.path.join(archive_dir, archive_name),
                                                 completed=copied_bytes, total=total_copy_bytes)
        archive_names.append(os.path.join("Archive", str(archive_index + 1), archive_name))

    image_names = []
    for index, image_path in enumerate(image_paths):
        if image_path and os.path.exists(image_path):
            image_name = f"image_{index + 1}_" + os.path.basename(image_path)
            copied_bytes += operation_jobs.copy_file(image_path, os.path.join(dest_dir, image_name),
                                                     completed=copied_bytes, total=total_copy_bytes)
            image_names.append(image_name)

    character = meta.get("character") or "Generic"
    skin = meta.get("skin") or ""
    source_folder = (meta.get("source_folder") or meta.get("name") or os.path.splitext(os.path.basename(filepaths[0]))[0]).strip()
    source_folder = re.sub(r'[<>:"/\\|?*]+', "_", source_folder).strip(". ") or "Mod"
    classification = {"id": mod_id, "files": files, "components": components}
    _analyze_mod_components(classification, [os.path.join(dest_dir, entry["name"]) for entry in files])
    for component in components:
        component.pop("asset_paths", None)
    detected_types = classification["types"]
    detected_type = detected_types[0]
    default_folder = (os.path.join("1_Audio", source_folder) if detected_type == "Audio"
                      else os.path.join(character, skin or "Default", source_folder))
    # Áudio puro sempre vai para a categoria 1_Audio. Quando o pacote contém
    # Mesh e Audio, o detector retorna Mesh antes de Audio e ele fica junto da
    # skin do personagem.
    folder = default_folder if detected_type == "Audio" else (meta.get("folder") or default_folder)
    folder = _safe_game_folder(folder)

    record = {
        "id": mod_id,
        "storage_folder": storage_folder,
        "name": meta.get("name") or os.path.splitext(os.path.basename(filepaths[0]))[0],
        "character": character,
        "skin": skin,
        # A seleção do modal é uma decisão explícita do usuário. Muitos mods
        # carregam assets de mais de uma skin; sem este marcador, uma leitura
        # futura poderia trocar a organização escolhida por uma heurística.
        "identity_override": {"character": character, "skin": skin or "Default"}
        if character and character != "Generic" else None,
        "type": detected_type,
        "types": detected_types,
        "tags": [tag.strip() for tag in meta.get("tags", []) if tag and tag.strip()],
        "image": image_names[0] if image_names else None,
        "images": image_names,
        "link": meta.get("link") or "",
        "files": files,
        "archives": archive_names,
        "components": components,
        "asset_path_cache": classification.get("asset_path_cache", {}),
        "size_mb": round(total_size / (1024 * 1024), 2),
        "enabled": bool(mods_path),
        "folder": folder,
        "priority": 1,
        "created_at": storage.now_iso(),
        "install_options": meta.get("install_options", {}),
    }

    if mods_path:
        _ensure_game_operation_allowed()
    operation_jobs.begin_commit()
    journal.set_records([], [record])
    journal.capture_files(_journal_file_targets([record], mods_path))
    journal.mark("applying")
    os.makedirs(os.path.dirname(final_dir), exist_ok=True)
    shutil.move(dest_dir, final_dir)
    if mods_path:
        _apply_enable(record, mods_path, True)
    mods = storage.load_mods()
    mods.append(record)
    storage.save_mods(mods)
    journal.mark("catalog_saved")
    journal.finish("completed")
    try:
        _record_activity(
            "add_mod", f"Adicionado: {record.get('name', 'Mod')}",
            {"mod_id": record.get("id"), "folder": record.get("folder", "")},
        )
    except Exception:
        # A instalação já está confirmada; um erro de histórico não a desfaz.
        pass
    return record


@_serialized_files
def add_reshade_mod(filepaths, meta):
    """Prepara e instala ReShade com cancelamento e recuperação durável."""
    from . import special_imports
    return special_imports.install(filepaths, meta, "reshade")


@_serialized_files
def add_background_mod(filepaths, meta):
    """Importa cinemáticas preservando camadas e o MoviesBink original."""
    from . import special_imports
    return special_imports.install(filepaths, meta, "background")


@_serialized_files
def add_background_audio_mod(filepaths, meta):
    """Separa áudio em staging; bancos novos continuam desativados."""
    from . import special_imports
    return special_imports.install(filepaths, meta, "background_audio")

@_serialized_files
def delete_mod(mod_id):
    mods = storage.load_mods()
    settings = storage.load_settings()
    mods_path = settings.get("mods_path", "")

    target = next((m for m in mods if m["id"] == mod_id), None)
    if not target:
        return {"ok": False}

    if mods_path and target["enabled"]:
        if target.get("install_target") == "marvel_content":
            target["enabled"] = False
            _refresh_background_files(mods, mods_path, (entry.get("name") for entry in target.get("files", [])))
        else:
            _apply_enable(target, mods_path, False)

    mod_dir = _storage_dir(target)
    if os.path.isdir(mod_dir):
        # Remove somente os pacotes; mídias e compactados continuam privados.
        protected_images = set(target.get("images") or [])
        if target.get("image"):
            protected_images.add(target["image"])
        for entry in target.get("files", []):
            file_path = os.path.join(mod_dir, entry.get("name", ""))
            if os.path.isfile(file_path):
                os.remove(file_path)
        # Se não houver imagens, a pasta vazia pode ser removida normalmente.
        remaining_images = [name for name in protected_images if os.path.isfile(os.path.join(mod_dir, name))]
        if not remaining_images and not target.get("archives"):
            shutil.rmtree(mod_dir, ignore_errors=True)

    mods[:] = [m for m in mods if m["id"] != mod_id]
    storage.save_mods(mods)
    _record_activity("remove_mod", f"Removido da biblioteca: {target.get('name', 'Mod')}", {"mod_id": mod_id})
    return {"ok": True}


@_serialized_files
def delete_mod_permanently(mod_id):
    """Remove o registro e todos os dados privados, inclusive imagens e ZIPs."""
    mods = storage.load_mods()
    settings = storage.load_settings()
    mods_path = settings.get("mods_path", "")
    target = next((m for m in mods if m["id"] == mod_id), None)
    if not target:
        return {"ok": False, "error": "Mod não encontrado."}
    if mods_path and target.get("enabled"):
        _apply_enable(target, mods_path, False)
    mod_dir = _storage_dir(target)
    if os.path.isdir(mod_dir):
        shutil.rmtree(mod_dir, ignore_errors=True)
    mods[:] = [m for m in mods if m["id"] != mod_id]
    storage.save_mods(mods)
    _record_activity("delete_mod", f"Excluído permanentemente: {target.get('name', 'Mod')}", {"mod_id": mod_id})
    return {"ok": True}


@_serialized_files
def move_mod(mod_id, folder):
    """Move arquivos ativos e atualiza o destino do mod, sem tocar no backup."""
    folder = (folder or "").strip().strip("\\/")
    if ".." in pathlib.PurePath(folder).parts:
        return {"ok": False, "error": "Destino inválido."}
    mods = storage.load_mods()
    settings = storage.load_settings()
    mods_path = settings.get("mods_path", "")
    target = next((m for m in mods if m["id"] == mod_id), None)
    if not target:
        return {"ok": False, "error": "Mod não encontrado."}
    old_folder = target.get("folder", "")
    if old_folder == folder:
        return {"ok": True}
    if target.get("enabled") and mods_path:
        _apply_enable(target, mods_path, False)
    target["folder"] = folder
    if target.get("enabled") and mods_path:
        _apply_enable(target, mods_path, True)
    storage.save_mods(mods)
    _record_activity(
        "move_mod",
        f"Movido: {target.get('name', 'Mod')} → {folder}",
        {"mod_id": mod_id, "folder": folder},
    )
    return {"ok": True}


@_serialized_files
def set_mod_identity(mod_id, character, skin):
    """Corrige manualmente personagem e skin sem o próximo scan desfazer a escolha.

    Mods visuais acompanham a identidade nova tanto em ``~mods`` quanto no
    backup em ``mods_storage``. Mods exclusivamente de áudio continuam no
    diretório ``1_Audio``: eles podem ter personagem/skin informados para
    filtros, mas não devem ser movidos para a árvore de skins do jogo.
    """
    character = (character or "").strip()
    skin = (skin or "").strip()
    if character not in MARVEL_CHARACTERS and character != "Generic":
        return {"ok": False, "error": "Personagem inválido."}
    if not character:
        character = "Generic"
    if character == "Generic":
        skin = ""
    else:
        skin = canonical_skin_name(skin or "Default", character) or "Default"

    mods = storage.load_mods()
    settings = storage.load_settings()
    mods_path = settings.get("mods_path", "")
    target = next((m for m in mods if m.get("id") == mod_id), None)
    if not target:
        return {"ok": False, "error": "Mod não encontrado."}

    types = {str(item).casefold() for item in (target.get("types") or [target.get("type") or "Unknown"])}
    audio_only = "audio" in types and not types.intersection({"mesh", "texture", "ui", "blueprint"})
    old_state = {
        "folder": target.get("folder", ""),
        "character": target.get("character", ""),
        "skin": target.get("skin", ""),
        "identity_override": target.get("identity_override"),
        "storage_folder": target.get("storage_folder"),
    }
    old_parts = pathlib.PureWindowsPath(str(target.get("folder") or "")).parts
    package = _safe_game_folder(old_parts[-1] if old_parts else _safe_package_folder(target.get("name")))
    new_folder = old_state["folder"] if audio_only else os.path.join(
        _safe_storage_segment(character, "Generic"),
        _safe_storage_segment(skin, "Default"),
        package,
    )
    was_enabled = bool(target.get("enabled"))
    try:
        if was_enabled and mods_path:
            _apply_enable(target, mods_path, False)
        target["character"] = character
        target["skin"] = skin
        target["folder"] = new_folder
        target["identity_override"] = ({"character": character, "skin": skin}
                                       if character != "Generic" else None)
        _sync_storage_location(target)
        if was_enabled and mods_path:
            _apply_enable(target, mods_path, True)
        storage.save_mods(mods)
        _record_activity(
            "correct_identity",
            f"Classificação corrigida: {target.get('name', 'Mod')} → {character} / {skin or 'Default'}",
            {"mod_id": mod_id, "character": character, "skin": skin},
        )
        from . import personal_corrections
        warnings = personal_corrections.remember_mod(target, identity=True)
        return {"ok": True, "character": character, "skin": skin, "folder": new_folder, "warnings": warnings}
    except OSError as error:
        target.update(old_state)
        try:
            _sync_storage_location(target)
            if was_enabled and mods_path:
                _apply_enable(target, mods_path, True)
        except OSError:
            pass
        storage.save_mods(mods)
        return {"ok": False, "error": f"Não foi possível corrigir a classificação: {error}"}


def get_move_destination_root(mod_id):
    """Retorna a pasta do herói usada pelo seletor nativo de destino.

    O menu nunca deve expor toda a árvore de ``~mods``: ela fica enorme e
    acaba oferecendo pastas de outros mods como destino. A escolha é limitada
    ao herói que já foi identificado para este registro.
    """
    mods = storage.load_mods()
    mods_path = storage.load_settings().get("mods_path", "")
    target = next((m for m in mods if m.get("id") == mod_id), None)
    if not target:
        return {"ok": False, "error": "Mod não encontrado."}
    if not mods_path or not os.path.isdir(mods_path):
        return {"ok": False, "error": "Configure uma pasta ~mods válida antes de mover o mod."}
    character = (target.get("character") or "").strip()
    if not character or character == "Generic":
        return {"ok": False, "error": "Este mod ainda não possui um personagem identificado."}
    root = os.path.abspath(os.path.join(mods_path, _safe_storage_segment(character, "Generic")))
    os.makedirs(root, exist_ok=True)
    return {"ok": True, "directory": root, "character": character}


@_serialized_files
def move_mod_to_skin_folder(mod_id, selected_folder):
    """Move um mod para uma skin escolhida no seletor nativo.

    ``selected_folder`` precisa ser uma pasta de skin dentro do herói do mod.
    O pacote do mod continua em uma subpasta própria; assim não misturamos os
    PAKs de mods diferentes. O backup em ``mods_storage`` acompanha a nova
    identidade para manter o jogo e o armazenamento privados sincronizados.
    """
    mods = storage.load_mods()
    mods_path = storage.load_settings().get("mods_path", "")
    target = next((m for m in mods if m.get("id") == mod_id), None)
    if not target:
        return {"ok": False, "error": "Mod não encontrado."}
    if not mods_path or not os.path.isdir(mods_path):
        return {"ok": False, "error": "Configure uma pasta ~mods válida antes de mover o mod."}

    character = (target.get("character") or "").strip()
    if not character or character == "Generic":
        return {"ok": False, "error": "Este mod ainda não possui um personagem identificado."}
    character_root = os.path.abspath(os.path.join(mods_path, _safe_storage_segment(character, "Generic")))
    destination = os.path.abspath(selected_folder or "")
    try:
        if os.path.commonpath([character_root, destination]) != character_root:
            return {"ok": False, "error": "Escolha uma pasta dentro do personagem deste mod."}
    except ValueError:
        return {"ok": False, "error": "Destino inválido."}
    if os.path.normcase(os.path.normpath(destination)) == os.path.normcase(os.path.normpath(character_root)):
        return {"ok": False, "error": "Escolha a pasta da skin, não a pasta do personagem."}
    if not os.path.isdir(destination):
        return {"ok": False, "error": "A pasta de skin escolhida não existe."}

    relative_skin_folder = os.path.relpath(destination, mods_path)
    try:
        relative_skin_folder = _safe_game_folder(relative_skin_folder)
    except ValueError:
        return {"ok": False, "error": "Destino inválido."}
    destination_parts = pathlib.PureWindowsPath(relative_skin_folder).parts
    if len(destination_parts) != 2 or destination_parts[0].casefold() != _safe_storage_segment(character, "Generic").casefold():
        return {"ok": False, "error": "Escolha uma pasta de skin diretamente dentro do personagem."}

    # A pasta escolhida representa a skin. O pacote atual segue como último
    # nível para evitar que vários mods depositem arquivos soltos no mesmo local.
    skin_folder_name = destination_parts[-1]
    skin = canonical_skin_name(skin_folder_name, character) or skin_folder_name
    old_parts = pathlib.PureWindowsPath(str(target.get("folder") or "")).parts
    package = _safe_game_folder(old_parts[-1] if old_parts else _safe_package_folder(target.get("name")))
    new_folder = os.path.join(relative_skin_folder, package)

    old_state = {
        "folder": target.get("folder", ""),
        "character": target.get("character", ""),
        "skin": target.get("skin", ""),
        "identity_override": target.get("identity_override"),
        "storage_folder": target.get("storage_folder"),
    }
    was_enabled = bool(target.get("enabled"))
    try:
        if was_enabled:
            _apply_enable(target, mods_path, False)
        target["folder"] = new_folder
        target["character"] = character
        target["skin"] = skin
        target["identity_override"] = {"character": character, "skin": skin}
        _sync_storage_location(target)
        if was_enabled:
            _apply_enable(target, mods_path, True)
        storage.save_mods(mods)
        _record_activity(
            "move_to_skin",
            f"Movido para skin: {target.get('name', 'Mod')} → {character} / {skin}",
            {"mod_id": mod_id, "character": character, "skin": skin, "folder": new_folder},
        )
        return {"ok": True, "folder": new_folder, "character": character, "skin": skin}
    except OSError as error:
        # Caso um arquivo esteja bloqueado, voltamos tanto o caminho do jogo
        # quanto o backup para o estado anterior antes de informar a falha.
        target["folder"] = old_state["folder"]
        target["character"] = old_state["character"]
        target["skin"] = old_state["skin"]
        target["identity_override"] = old_state["identity_override"]
        try:
            _sync_storage_location(target)
            if was_enabled:
                _apply_enable(target, mods_path, True)
        except OSError:
            pass
        target["storage_folder"] = old_state["storage_folder"] or target.get("storage_folder")
        storage.save_mods(mods)
        return {"ok": False, "error": f"Não foi possível mover o mod: {error}"}


def _safe_package_folder(name):
    """Nome de pasta estável para importações antigas que perderam o ZIP."""
    name = re.sub(r"_9+_P$", "", (name or "").strip(), flags=re.IGNORECASE)
    name = re.sub(r'[<>:"/\\\\|?*]+', "_", name).strip(". ")
    return name or "Mod"


def migrate_legacy_layouts(dry_run=False):
    """Migra registros antigos para Personagem/Skin/Pacote.

    Só move os arquivos pertencentes a cada registro; nunca move uma pasta
    inteira de categoria (como 1_Audio), portanto mods vizinhos permanecem
    intactos. Para pastas antigas que já têm um pacote no último nível,
    preserva esse nome de pacote.
    """
    mods = storage.load_mods()
    mods_path = storage.load_settings().get("mods_path", "")
    if not mods_path or not os.path.isdir(mods_path):
        return {"ok": False, "error": "Configure uma pasta ~mods válida antes de migrar."}

    plan = []
    for mod in mods:
        old_folder = (mod.get("folder") or "").strip("\\/")
        parts = pathlib.PureWindowsPath(old_folder).parts
        package = parts[-1] if len(parts) >= 3 else _safe_package_folder(mod.get("name"))
        package = _safe_package_folder(package)

        # Reavalia com os assets reais. A ordem em _detect_type_from_bundle
        # garante Mesh > Audio para pacotes híbridos.
        source_dir = os.path.join(mods_path, old_folder)
        source_files = [os.path.join(source_dir, entry.get("name", "")) for entry in mod.get("files", [])]
        detected_types = _detect_types_from_bundle(source_files, old_folder)
        detected_type = detected_types[0]
        if detected_type != "Unknown":
            mod["type"] = detected_type
            mod["types"] = detected_types

        if mod.get("type") == "Audio":
            if len(parts) >= 2 and parts[0].casefold() == "1_audio":
                continue
            new_folder = os.path.join("1_Audio", package)
        else:
            character = (mod.get("character") or "").strip()
            if not character or character == "Generic":
                continue
            skin = (mod.get("skin") or "Default").strip() or "Default"
            safe_character = _safe_package_folder(character)
            safe_skin = _safe_package_folder(skin)
            # Já existe uma pasta de pacote sob o personagem: não alteramos
            # essa organização só porque a grafia da skin foi refinada depois.
            if len(parts) >= 3 and parts[0].casefold() == safe_character.casefold():
                continue
            new_folder = os.path.join(safe_character, safe_skin, package)
        if old_folder.casefold() != new_folder.casefold():
            plan.append((mod, old_folder, new_folder))

    if dry_run:
        return {"ok": True, "planned": len(plan), "moves": [
            {"id": mod["id"], "name": mod.get("name"), "from": old, "to": new}
            for mod, old, new in plan
        ]}

    moved, skipped = 0, []
    for mod, old_folder, new_folder in plan:
        source_dir = os.path.join(mods_path, old_folder)
        target_dir = os.path.join(mods_path, new_folder)
        files = [entry.get("name", "") for entry in mod.get("files", [])]
        if mod.get("enabled"):
            missing = [name for name in files if not os.path.isfile(os.path.join(source_dir, name))]
            collisions = [name for name in files if os.path.isfile(os.path.join(target_dir, name))]
            if missing or collisions:
                skipped.append({"name": mod.get("name"), "reason": "arquivos ausentes ou destino já ocupado"})
                continue
            try:
                os.makedirs(target_dir, exist_ok=True)
                for name in files:
                    shutil.move(os.path.join(source_dir, name), os.path.join(target_dir, name))
            except OSError as exc:
                skipped.append({"name": mod.get("name"), "reason": str(exc)})
                continue
        mod["folder"] = new_folder
        moved += 1

    storage.save_mods(mods)
    return {"ok": True, "moved": moved, "skipped": skipped}


def organize_mod_storage():
    """Substitui diretórios de ID por Personagem/Skin/Mod [ID]."""
    mods = storage.load_mods()
    moved, skipped = 0, []
    for mod in mods:
        desired = os.path.join(
            _safe_storage_segment(mod.get("character"), "Generic"),
            _safe_storage_segment(mod.get("skin"), "Default"),
            f"{_safe_storage_segment(mod.get('name'), 'Mod')} [{mod['id']}]",
        )
        old_relative = mod.get("storage_folder") or mod["id"]
        old_path = os.path.join(storage.STORAGE_DIR, old_relative)
        new_path = os.path.join(storage.STORAGE_DIR, desired)
        if os.path.normcase(old_path) != os.path.normcase(new_path) and os.path.exists(old_path):
            if os.path.exists(new_path):
                skipped.append({"name": mod.get("name"), "reason": "destino já existe"})
                continue
            try:
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                shutil.move(old_path, new_path)
                moved += 1
            except OSError as exc:
                skipped.append({"name": mod.get("name"), "reason": str(exc)})
                continue
        mod["storage_folder"] = desired
    storage.save_mods(mods)
    return {"ok": True, "moved": moved, "skipped": skipped}


def set_image(mod_id, image_path):
    mods = storage.load_mods()
    target = next((m for m in mods if m["id"] == mod_id), None)
    if not target or not image_path or not os.path.isfile(image_path):
        return {"ok": False, "error": "Imagem não encontrada."}
    ext = os.path.splitext(image_path)[1].lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return {"ok": False, "error": "Formato de imagem não suportado."}
    dest_dir = _storage_dir(target, create=True)
    image_name = "cover" + ext
    shutil.copy2(image_path, os.path.join(dest_dir, image_name))
    target["image"] = image_name
    storage.save_mods(mods)
    return {"ok": True}


def _handbrake_cli_path():
    """Prefere o conversor privado do Manager, sem abrir interfaces externas."""
    return next((path for path in (os.path.join(storage.RESOURCE_DIR, "tools", "handbrake", "HandBrakeCLI.exe"),
                                  shutil.which("HandBrakeCLI.exe"))
                 if path and os.path.isfile(path)), None)


def _optimize_gallery_video(source_path, destination_path):
    """Cria o MP4 com parâmetros próprios, sem perfis de outro aplicativo.

    O resultado vai direto para o armazenamento do mod; não usamos a pasta
    de saída da interface do HandBrake e não guardamos uma cópia do original.
    """
    temporary_path = destination_path + ".tmp.mp4"
    try:
        handbrake = _handbrake_cli_path()
        if handbrake:
            result = subprocess.run(
                [handbrake, "-i", source_path, "-o", temporary_path,
                 "--format", "av_mp4", "--encoder", "x264", "--quality", "23",
                 "--encoder-preset", "slow", "--maxHeight", "720",
                 "--aencoder", "av_aac", "--ab", "128", "--optimize"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=1800,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            # Reserva para não bloquear a galeria caso o HandBrake seja
            # removido ou movido depois; continua sem salvar o original.
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise RuntimeError("HandBrakeCLI e FFmpeg não foram encontrados para otimizar o vídeo.")
            result = subprocess.run(
                [
                    ffmpeg, "-hide_banner", "-y", "-i", source_path,
                    "-vf", "scale=-2:min(720,ih)",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                    temporary_path,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=900,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        if result.returncode != 0 or not os.path.isfile(temporary_path):
            error = (result.stderr or "").strip().splitlines()
            raise RuntimeError(error[-1] if error else "Não foi possível otimizar o vídeo.")
        os.replace(temporary_path, destination_path)
        # O arquivo escolhido é somente a fonte da conversão. Após termos o
        # MP4 otimizado salvo com segurança, removemos a cópia original fora
        # do mods_storage, como definido para a galeria.
        source_real = os.path.normcase(os.path.abspath(source_path))
        storage_real = os.path.normcase(os.path.abspath(storage.STORAGE_DIR))
        if source_real != os.path.normcase(os.path.abspath(destination_path)) and not (
            source_real == storage_real or source_real.startswith(storage_real + os.sep)
        ):
            os.remove(source_path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)


def add_gallery_images(mod_id, image_paths):
    """Copia imagens ou vídeos para a galeria privada do mod."""
    mods = storage.load_mods()
    target = next((m for m in mods if m["id"] == mod_id), None)
    if not target:
        return {"ok": False, "error": "Mod não encontrado."}
    allowed = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".ogv", ".mov"}
    image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    video_extensions = {".mp4", ".webm", ".ogv", ".mov"}
    dest_dir = _storage_dir(target, create=True)
    images = list(target.get("images") or ([target["image"]] if target.get("image") else []))
    added = 0
    for path in image_paths or []:
        if not path or not os.path.isfile(path) or os.path.splitext(path)[1].lower() not in allowed:
            continue
        safe_name = re.sub(r'[<>:"/\\\\|?*]+', "_", os.path.basename(path))
        is_video = os.path.splitext(path)[1].lower() in video_extensions
        # O vídeo final é sempre MP4 otimizado; o arquivo escolhido fora do
        # manager não é copiado para o armazenamento privado.
        if is_video:
            safe_name = os.path.splitext(safe_name)[0] + ".mp4"
        image_name = f"image_{len(images) + 1}_{safe_name}"
        while image_name in images:
            image_name = f"image_{len(images) + 1 + added}_{safe_name}"
        destination = os.path.join(dest_dir, image_name)
        try:
            if is_video:
                _optimize_gallery_video(path, destination)
            else:
                shutil.copy2(path, destination)
        except (OSError, subprocess.SubprocessError, RuntimeError) as error:
            return {"ok": False, "error": f"Não foi possível adicionar {os.path.basename(path)}: {error}"}
        images.append(image_name)
        added += 1
    if not added:
        return {"ok": False, "error": "Nenhuma imagem ou vídeo válido foi escolhido."}
    target["images"] = images
    # Vídeo é mídia de galeria, não capa de card. Mantemos a primeira imagem
    # como capa, ou deixamos a capa vazia quando só houver vídeos.
    if not target.get("image") or os.path.splitext(target.get("image", ""))[1].lower() not in image_extensions:
        target["image"] = next((name for name in images if os.path.splitext(name)[1].lower() in image_extensions), None)
    storage.save_mods(mods)
    return {"ok": True, "added": added}


def remove_gallery_image(mod_id, image_name):
    """Remove somente uma imagem pertencente à galeria do mod."""
    mods = storage.load_mods()
    target = next((m for m in mods if m["id"] == mod_id), None)
    if not target or not image_name:
        return {"ok": False, "error": "Imagem não encontrada."}
    images = list(target.get("images") or ([target["image"]] if target.get("image") else []))
    if image_name not in images or os.path.basename(image_name) != image_name:
        return {"ok": False, "error": "Imagem inválida."}
    path = os.path.join(_storage_dir(target), image_name)
    if os.path.isfile(path):
        os.remove(path)
    images.remove(image_name)
    target["images"] = images
    # Vídeos continuam apenas na galeria: a capa do card deve ser uma imagem.
    image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    target["image"] = next(
        (name for name in images if os.path.splitext(name)[1].lower() in image_extensions),
        None,
    )
    titles = target.get("image_titles") or {}
    titles.pop(image_name, None)
    target["image_titles"] = titles
    storage.save_mods(mods)
    return {"ok": True}


def set_gallery_cover(mod_id, image_name):
    mods = storage.load_mods()
    target = next((m for m in mods if m["id"] == mod_id), None)
    if not target:
        return {"ok": False, "error": "Mod não encontrado."}
    images = list(target.get("images") or ([target["image"]] if target.get("image") else []))
    if image_name not in images:
        return {"ok": False, "error": "Imagem não encontrada."}
    if os.path.splitext(image_name)[1].lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return {"ok": False, "error": "Vídeos não podem ser usados como capa do card."}
    images.remove(image_name)
    images.insert(0, image_name)
    target["images"] = images
    target["image"] = image_name
    storage.save_mods(mods)
    return {"ok": True}


def reorder_gallery_images(mod_id, image_names):
    """Persiste a ordem escolhida pelo usuário para as mídias da galeria."""
    mods = storage.load_mods()
    target = next((m for m in mods if m["id"] == mod_id), None)
    if not target:
        return {"ok": False, "error": "Mod não encontrado."}

    existing = list(target.get("images") or ([target["image"]] if target.get("image") else []))
    requested = [str(name) for name in (image_names or [])]
    if (
        len(requested) != len(existing)
        or len(set(requested)) != len(requested)
        or set(requested) != set(existing)
    ):
        return {"ok": False, "error": "A ordem da galeria é inválida."}

    target["images"] = requested
    image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    # Vídeo pode aparecer em qualquer posição da galeria, porém a capa do
    # card continua precisando de uma imagem estática.
    target["image"] = next(
        (name for name in requested if os.path.splitext(name)[1].lower() in image_extensions),
        None,
    )
    storage.save_mods(mods)
    return {"ok": True, "cover": target.get("image")}


def set_gallery_image_title(mod_id, image_name, title):
    mods = storage.load_mods()
    target = next((m for m in mods if m["id"] == mod_id), None)
    images = list(target.get("images") or ([target["image"]] if target and target.get("image") else []))
    if not target or image_name not in images:
        return {"ok": False, "error": "Imagem não encontrada."}
    titles = target.get("image_titles") or {}
    title = (title or "").strip()
    if title:
        titles[image_name] = title
    else:
        titles.pop(image_name, None)
    target["image_titles"] = titles
    storage.save_mods(mods)
    return {"ok": True}


def _build_mod_details(mod_id, include_previews=True):
    mod = next(iter(list_mods(include_gallery=True, only_mod_id=mod_id,
                             include_thumbnails=include_previews)), None)
    if not mod:
        return None
    if mod.get("install_target") == "marvel_content":
        # Alguns ZIPs de addons incluem uma pasta de apresentação antes de
        # MoviesBink. Repara esses registros antigos ao abrir o perfil-base.
        saved_mods = storage.load_mods()
        related_ids = {mod_id}
        related_ids.update(item.get("id") for item in saved_mods if item.get("parent_background_id") == mod_id)
        affected, changed = set(), False
        for item in saved_mods:
            if item.get("id") in related_ids:
                migrated = _normalize_background_layout(item)
                affected.update(migrated)
                changed = changed or bool(migrated)
        if changed:
            storage.save_mods(saved_mods)
            settings = storage.load_settings()
            if settings.get("mods_path") and any(item.get("enabled") for item in saved_mods if item.get("id") in related_ids):
                _refresh_background_files(saved_mods, settings["mods_path"], affected)
            mod = next(iter(list_mods(include_gallery=True, only_mod_id=mod_id,
                                     include_thumbnails=include_previews)), mod)
        current_by_file = {
            (component.get("files") or [{}])[0].get("name"): component
            for component in mod.get("components", []) if len(component.get("files", [])) == 1
        }
        refreshed_components = _background_components(mod.get("files", []))
        for component in refreshed_components:
            previous = current_by_file.get(component["files"][0]["name"])
            if previous:
                component["id"] = previous.get("id", component["id"])
                component["enabled"] = previous.get("enabled", True)
                if previous.get("audio_binding"):
                    component["audio_binding"] = previous["audio_binding"]
        if refreshed_components != mod.get("components", []):
            mod["components"] = refreshed_components
            saved_mods = storage.load_mods()
            saved = next((item for item in saved_mods if item.get("id") == mod_id), None)
            if saved:
                saved["components"] = mod["components"]
                storage.save_mods(saved_mods)
        mod["storage_path"] = _storage_dir(mod)
        mod["install_path"] = get_open_path(mod_id)
        mod["file_count"] = len(mod.get("files", []))
        mod["asset_paths"] = []
        mod["asset_count"] = 0
        mod["bundle_information"] = {}
        mod["cinematic_preview_available"] = bool(_find_bink_player())
        audio_records = _background_audio_mods(mod_id, storage.load_mods())
        def audio_component_metadata(component):
            stored_location = component.get("location")
            stored_variant = component.get("variant", "")
            if component.get("audio_bank"):
                detected = _background_audio_metadata(component["audio_bank"])
                if stored_location in (None, "", "Outros"):
                    stored_location = detected.get("location", "Outros")
                if not stored_variant:
                    stored_variant = detected.get("variant", "")
            return stored_location or "Outros", stored_variant
        audio_lookup = {
            (audio_mod.get("id"), audio_component.get("id")): {
                "mod_id": audio_mod.get("id"), "component_id": audio_component.get("id"),
                "package": audio_mod.get("name", "Áudio"), "name": _background_audio_display_name(audio_mod, audio_component),
                "location": audio_component_metadata(audio_component)[0], "variant": audio_component_metadata(audio_component)[1],
                "enabled": audio_component.get("enabled", False), "pending_enabled": audio_component.get("pending_enabled"),
            }
            for audio_mod in audio_records for audio_component in audio_mod.get("components", [])
        }
        audio_choices = list(audio_lookup.values())
        def cinematic_detail(component, owner_id=None):
            binding = component.get("audio_binding") or {}
            cinematic_meta = _cinematic_metadata(component.get("files", [{}])[0].get("name", ""))
            # Para não exibir dezenas de bancos irrelevantes, a escolha é
            # limitada ao mesmo mapa/Location da cinematic. Bancos de Lobby e
            # Interface continuam disponíveis quando a cinematic também tiver
            # esse contexto.
            matching_audio = [choice for choice in audio_choices if choice.get("location") == cinematic_meta.get("location")]
            return {
                "component_id": component["id"], "enabled": component.get("enabled", True),
                "name": component.get("name", "Cinematic"),
                "file": component.get("files", [{}])[0].get("name", ""),
                "mod_id": owner_id, "audio_binding": audio_lookup.get((binding.get("mod_id"), binding.get("component_id"))),
                "audio_choices": matching_audio, **cinematic_meta,
            }
        mod["cinematics"] = [
            cinematic_detail(component)
            for component in mod.get("components", [])
        ]
        mod["background_addons"] = [
            {"id": item.get("id"), "name": item.get("name", "Complemento"),
             "enabled": item.get("enabled", False), "file_count": len(item.get("files", [])),
            "cinematics": [
                cinematic_detail(component, item.get("id"))
                 for component in item.get("components", [])
            ]}
            for item in storage.load_mods()
            if item.get("parent_background_id") == mod_id and not item.get("background_audio")
        ]
        # Processa silenciosamente solicitações que ficaram pendentes enquanto
        # o jogo estava aberto antes de devolver o estado para a interface.
        _process_pending_background_audio_changes()
        # Limpa bancos que versões antigas podiam deixar em ~mods mesmo sem
        # nenhuma cinematic ativa vinculada. Nunca toca nos arquivos se o jogo
        # estiver aberto, pois nesse caso a fila continua sendo a autoridade.
        current_settings = storage.load_settings()
        if current_settings.get("mods_path") and not _is_marvel_rivals_running():
            _sync_background_audio_files(storage.load_mods(), current_settings["mods_path"])
        return mod
    components_changed = False
    if not mod.get("components"):
        groups = {}
        for entry in mod.get("files", []):
            groups.setdefault(os.path.splitext(entry["name"])[0], []).append(entry)
        mod["components"] = [
            {"id": storage.new_id(), "name": stem, "files": entries, "enabled": True}
            for stem, entries in groups.items()
        ]
        saved_mods = storage.load_mods()
        saved = next((item for item in saved_mods if item["id"] == mod_id), None)
        if saved:
            saved["components"] = mod["components"]
            storage.save_mods(saved_mods)
    # Registros criados antes desta regra podiam mostrar Physics como
    # "Principal". Reordenamos sem alterar o estado de cada componente.
    normalized_components = (mod.get("components", []) if mod.get("components_order_custom")
                             else _put_physics_components_last(mod.get("components", [])))
    if normalized_components != mod.get("components", []):
        mod["components"] = normalized_components
        components_changed = True
    mod["storage_path"] = _storage_dir(mod)
    # Caminho em uso: no jogo se o mod estiver ativo; no backup do programa,
    # caso ele esteja desativado.
    mod["install_path"] = get_open_path(mod_id)
    mod["file_count"] = len(_all_mod_file_entries(mod))
    source_files = _mod_source_files(mod)
    # Abrir detalhes precisa ser imediato. Não lemos UTOC/PAK aqui: essa
    # inspeção pode levar vários segundos por componente. A interface chama
    # classify_mod_components após exibir a página para completar o que falta.
    for component in mod.get("components", []):
        saved_types = component.get("types")
        if not isinstance(saved_types, list) or not saved_types:
            saved_type = component.get("type")
            saved_types = [saved_type] if saved_type else []
        component_types = _component_types_from_metadata(mod, component)
        if component_types != saved_types or component.get("type") != component_types[0]:
            components_changed = True
        component["types"] = component_types
        component["type"] = component_types[0]
    if components_changed:
        saved_mods = storage.load_mods()
        saved = next((item for item in saved_mods if item.get("id") == mod_id), None)
        if saved:
            saved["components"] = mod.get("components", [])
            storage.save_mods(saved_mods)
    asset_paths = []
    mod["asset_paths"] = asset_paths
    mod["asset_count"] = 0
    cached_paths = []
    for component in mod.get("components", []):
        paths, _ = _component_cached_asset_paths(mod, component)
        cached_paths.extend(paths)
        files = _component_source_files(mod, component, source_files)
        component["classification_status"] = (
            "missing" if len(files) != len(component.get("files", [])) else
            ("unrecognized" if component.get("types") == ["Unknown"] else "analyzed") if paths else
            "read_error" if (mod_id, component.get("id")) in _COMPONENT_ANALYSIS_RETRY else "pending")
    mod["asset_count"] = len(set(cached_paths))
    mod["bundle_information"] = _bundle_information(mod, source_files, cached_paths)
    mod["component_classification_pending"] = any(
        _component_analysis_pending(mod, component, _component_source_files(mod, component, source_files))
        for component in mod.get("components", [])
    )
    return mod


def get_mod_details(mod_id, include_previews=True):
    """Retorna detalhes e reutiliza metadados enquanto a biblioteca não mudar."""
    if include_previews:
        return _build_mod_details(mod_id, include_previews=True)
    cached = _cached_mod_details(mod_id)
    if cached is not None:
        return cached
    mod = _build_mod_details(mod_id, include_previews=False)
    if mod is not None:
        _remember_mod_details(mod_id, mod)
    return mod


def get_component_file_contents(mod_id, component_id):
    """Retorna os assets internos de um único componente sem abrir o mod inteiro.

    Reaproveita a classificação automática quando disponível. A consulta
    lê apenas o componente pedido se o cache ainda não estiver pronto.
    """
    mod = next(iter(list_mods(include_gallery=False, only_mod_id=mod_id)), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}
    component = next((item for item in mod.get("components", []) if item.get("id") == component_id), None)
    if not component:
        return {"ok": False, "error": "Componente não encontrado."}

    source_files = _mod_source_files(mod)
    component_files = _component_source_files(mod, component, source_files)
    cache_key = f"component-files-v1:{component_id}"
    classified = (mod.get("asset_path_cache") or {}).get(f"classification-v1:{component_id}", {})
    if classified.get("signature") == _component_analysis_signature(component_files) and classified.get("paths"):
        asset_paths, cache_changed = classified["paths"], False
    else:
        asset_paths, cache_changed = _cached_bundle_paths(mod, component_files, cache_key)
    if cache_changed:
        saved_mods = storage.load_mods()
        saved = next((item for item in saved_mods if item.get("id") == mod_id), None)
        if saved:
            saved["asset_path_cache"] = mod.get("asset_path_cache", {})
            storage.save_mods(saved_mods)

    return {
        "ok": True,
        "component_id": component_id,
        "component_name": component.get("name", "Componente"),
        "asset_paths": asset_paths,
        "asset_count": len(asset_paths),
        "files": component.get("files", []),
    }


def open_cinematic_preview(mod_id, component_id):
    """Abre um BK2 no Bink Player oficial incluído ou disponível no PATH."""
    mod = next((item for item in storage.load_mods() if item.get("id") == mod_id), None)
    component = next((item for item in (mod or {}).get("components", []) if item.get("id") == component_id), None)
    if not mod or not component or mod.get("install_target") != "marvel_content":
        return {"ok": False, "error": "Cinematic não encontrada."}
    entry = (component.get("files") or [{}])[0]
    source = os.path.join(_storage_dir(mod), entry.get("name", ""))
    player = _find_bink_player()
    if not player:
        return {"ok": False, "error": "O Bink Player da prévia BK2 está ausente ou foi removido da instalação do CrabVault."}
    if not os.path.isfile(source):
        return {"ok": False, "error": "O arquivo BK2 não está na biblioteca."}
    try:
        process = subprocess.Popen([player, source], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        _refresh_bink_player_window(process.pid)
        return {"ok": True}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def _refresh_bink_player_window(process_id):
    """Força o primeiro recálculo de layout do player legado após abri-lo."""
    if os.name != "nt":
        return

    def refresh():
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            hwnd_found = []
            callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def find_window(hwnd, _):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == process_id and user32.IsWindowVisible(hwnd):
                    hwnd_found.append(hwnd)
                    return False
                return True

            for _ in range(30):
                user32.EnumWindows(callback_type(find_window), 0)
                if hwnd_found:
                    break
                time.sleep(0.1)
            if not hwnd_found:
                return
            rect = wintypes.RECT()
            hwnd = hwnd_found[0]
            # O Bink Player recalcula corretamente a área de vídeo ao receber
            # a transição para maximizado, equivalente ao duplo clique manual
            # na barra de título.
            user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
            time.sleep(0.15)
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return
            flags = 0x0001 | 0x0004 | 0x0010  # NOMOVE | NOZORDER | NOACTIVATE
            width, height = rect.right - rect.left, rect.bottom - rect.top
            user32.SetWindowPos(hwnd, 0, 0, 0, width + 1, height + 1, flags)
            time.sleep(0.08)
            user32.SetWindowPos(hwnd, 0, 0, 0, width, height, flags)
        except Exception:
            pass

    threading.Thread(target=refresh, name="bink-player-layout", daemon=True).start()


def rename_mod(mod_id, new_name):
    mods = storage.load_mods()
    for m in mods:
        if m["id"] == mod_id:
            m["name"] = new_name.strip()
            storage.save_mods(mods)
            return {"ok": True}
    return {"ok": False}


def set_mod_link(mod_id, link):
    """Atualiza o link de origem associado ao mod."""
    link = (link or "").strip()
    if link and not re.match(r"^https?://", link, re.IGNORECASE):
        return {"ok": False, "error": "Use um link iniciado por http:// ou https://."}
    mods = storage.load_mods()
    for mod in mods:
        if mod["id"] == mod_id:
            mod["link"] = link
            storage.save_mods(mods)
            return {"ok": True, "link": link}
    return {"ok": False, "error": "Mod não encontrado."}


def set_priority(mod_id, delta):
    mods = storage.load_mods()
    for m in mods:
        if m["id"] == mod_id:
            current = m.get("priority", 1)
            m["priority"] = max(1, min(10, current + delta))
            storage.save_mods(mods)
            if m["priority"] != current:
                _record_activity("priority", f"Prioridade de {m.get('name', 'Mod')}: {current} → {m['priority']}", {"mod_id": mod_id, "before": current, "after": m["priority"]})
            return {"ok": True, "priority": m["priority"]}
    return {"ok": False}


def add_tag(mod_id, tag):
    tag = tag.strip()
    if tag:
        create_tag(tag)
    mods = storage.load_mods()
    for m in mods:
        if m["id"] == mod_id:
            if tag and tag not in m["tags"]:
                m["tags"].append(tag)
            storage.save_mods(mods)
            return m["tags"]
    return []


def remove_tag(mod_id, tag):
    mods = storage.load_mods()
    for m in mods:
        if m["id"] == mod_id:
            m["tags"] = [t for t in m["tags"] if t != tag]
            storage.save_mods(mods)
            return m["tags"]
    return []


def delete_tag_catalog(tag):
    """Exclui uma tag globalmente, inclusive das atribuições existentes."""
    tag = (tag or "").strip()
    if not tag:
        return {"ok": False, "error": "Informe uma tag válida."}
    settings = storage.load_settings()
    settings["tag_catalog"] = [item for item in settings.get("tag_catalog", [])
                               if not isinstance(item, str) or item.casefold() != tag.casefold()]
    mods = storage.load_mods()
    for mod in mods:
        mod["tags"] = [item for item in mod.get("tags", []) if str(item).casefold() != tag.casefold()]
    storage.save_settings(settings)
    storage.save_mods(mods)
    return {"ok": True, "tags": get_tags()}


def get_open_path(mod_id):
    mods = storage.load_mods()
    settings = storage.load_settings()
    mods_path = settings.get("mods_path", "")

    m = next((m for m in mods if m["id"] == mod_id), None)
    if not m:
        return None
    if mods_path and m["enabled"]:
        return _game_target_dir(m, mods_path)
    return _storage_dir(m)


def open_in_explorer(path):
    if not path or not os.path.exists(path):
        return {"ok": False}
    try:
        if os.name == "nt":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
