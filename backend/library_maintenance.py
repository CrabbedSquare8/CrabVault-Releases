"""Manutenção explícita da biblioteca, sem varreduras pesadas ao abrir a UI.

Diagnósticos e sugestões nunca alteram arquivos. O reparo oferece somente
cópias para destinos ausentes, mediante um plano guardado no backend; arquivos
divergentes e conteúdo sem registro são apresentados para revisão, não apagados.
"""
import copy
import hashlib
import json
import os
import pathlib
import re
import secrets
import tempfile
import threading
import time
import unicodedata

from . import mod_ops, storage, operation_jobs


_REPAIR_PLANS = {}
_RELATION_PLANS = {}
_PLAN_LOCK = threading.Lock()
_PLAN_LIFETIME = 15 * 60
_PACKAGE_EXTENSIONS = {".pak", ".utoc", ".ucas"}
_STATUS_MESSAGES = {
    "missing": "Há arquivos ausentes; restaure o pacote antes de reanalisar.",
    "pending": "Este componente ainda não tem análise atual dos assets.",
    "read_error": "A última leitura não retornou assets; verifique o pacote e a ferramenta.",
    "unrecognized": "Os assets foram lidos, mas não há evidência para um tipo reconhecido.",
    "analyzed": "Os tipos possuem evidência disponível no cache do componente.",
}


def _within_resolved(path, root):
    """Compara caminhos já resolvidos sem repetir chamadas ao sistema."""
    path, root = pathlib.Path(path), pathlib.Path(root)
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _within(path, root):
    return _within_resolved(pathlib.Path(path).resolve(), pathlib.Path(root).resolve())


def _safe_child_from_resolved_root(root, relative):
    """Valida um filho e resolve seu destino final sob uma raiz já resolvida."""
    raw = str(relative or "").replace("\\", "/")
    windows = pathlib.PureWindowsPath(raw)
    parts = pathlib.PurePosixPath(raw).parts
    if (not raw or windows.drive or windows.root or raw.startswith("/")
            or any(part in {"..", ""} or ":" in part for part in parts)):
        raise ValueError("O catálogo contém um caminho de arquivo inválido.")
    root = pathlib.Path(root)
    result = root.joinpath(*parts).resolve()
    if result == root or not _within_resolved(result, root):
        raise ValueError("O caminho do arquivo sai da pasta permitida.")
    return result


def _safe_child(root, relative):
    """Recusa caminhos absolutos, travessias, ADS e links que escapem da raiz."""
    return _safe_child_from_resolved_root(pathlib.Path(root).resolve(), relative)


def _roots(mod, settings, *, resolved_storage_root=None, resolved_mods_root=None):
    storage_root = (pathlib.Path(storage.STORAGE_DIR).resolve() if resolved_storage_root is None
                    else pathlib.Path(resolved_storage_root))
    private = pathlib.Path(mod_ops._storage_dir(mod)).resolve()
    if private == storage_root or not _within_resolved(private, storage_root):
        raise ValueError("A pasta privada deste mod sai da biblioteca configurada.")
    mods_path = str(settings.get("mods_path") or "")
    active = pathlib.Path(mod_ops._game_target_dir(mod, mods_path)).resolve() if mods_path else None
    if active is not None and not mod.get("install_target"):
        mods_root = (pathlib.Path(mods_path).resolve() if resolved_mods_root is None
                     else pathlib.Path(resolved_mods_root))
        if not _within_resolved(active, mods_root):
            raise ValueError("A pasta ativa deste mod sai da pasta do jogo configurada.")
    return private, active


def _entries(mod):
    return mod_ops._all_library_file_entries(mod)


def _expected_hash(entry):
    value = str(entry.get("sha256") or "").lower()
    return value if re.fullmatch(r"[0-9a-f]{64}", value) else ""


def _expected_size(entry):
    value = entry.get("size")
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _stamp(stat):
    # No Windows, stat e fstat podem expor criação/alteração diferentes em
    # st_ctime. Identidade, tamanho e mtime são consistentes nos dois caminhos.
    common = stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns
    return common if os.name == "nt" else (*common, stat.st_ctime_ns)


def _hash_file(path, cache=None):
    """SHA-256 em blocos; recusa um arquivo alterado durante a leitura."""
    before = os.stat(path)
    operation_jobs.check()
    key = _stamp(before)
    # Em sistemas sem inode confiável, o caminho também separa os arquivos.
    if not before.st_ino:
        key = (str(path), *key)
    if cache is not None and key in cache:
        return cache[key]
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        if _stamp(os.fstat(stream.fileno())) != _stamp(before):
            raise OSError("O arquivo mudou durante a verificação.")
        read_bytes = 0
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            operation_jobs.check()
            digest.update(chunk)
            read_bytes += len(chunk)
            operation_jobs.progress("hash", f"Comparando conteúdo: {os.path.basename(path)}",
                                    read_bytes, before.st_size, "bytes")
        if _stamp(os.fstat(stream.fileno())) != _stamp(before):
            raise OSError("O arquivo mudou durante a verificação.")
    if _stamp(os.stat(path)) != _stamp(before):
        raise OSError("O arquivo mudou durante a verificação.")
    result = {"sha256": digest.hexdigest(), "size": before.st_size, "stamp": _stamp(before)}
    if cache is not None:
        cache[key] = result
    return result


def _file_health(path, entry, verify_hashes, cache):
    if not os.path.lexists(path):
        return {"status": "missing"}
    if not path.is_file():
        return {"status": "unreadable", "message": "O caminho não é um arquivo regular."}
    try:
        size = path.stat().st_size
        expected_size, expected_sha = _expected_size(entry), _expected_hash(entry)
        result = {"status": "ok", "size": size}
        if verify_hashes:
            result.update(_hash_file(path, cache))
        if expected_size is not None and size != expected_size:
            result.update(status="mismatch", expected_size=expected_size)
        if verify_hashes and expected_sha and result["sha256"] != expected_sha:
            result.update(status="mismatch", expected_sha256=expected_sha)
        return result
    except OSError as error:
        return {"status": "unreadable", "message": str(error)}


def _find_orphans(mods):
    """Lista pastas sem registro e temporários, preservando arquivos removidos."""
    root = pathlib.Path(storage.STORAGE_DIR).resolve()
    registered = set()
    warnings = []
    for mod in mods:
        try:
            candidate = pathlib.Path(mod_ops._storage_dir(mod)).resolve()
            if candidate != root and _within(candidate, root):
                registered.add(candidate)
        except (OSError, ValueError):
            continue
    groups = {}

    def walk_error(error):
        warnings.append(f"Não foi possível verificar uma pasta da biblioteca: {error}")

    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        operation_jobs.progress("orphans", "Verificando pastas sem vínculo com o catálogo…")
        base = pathlib.Path(directory)
        dirs[:] = [name for name in dirs if not (base / name).is_symlink()
                   and not getattr(os.path, "isjunction", lambda path: False)(base / name)]
        owner = next((parent for parent in (base, *base.parents) if parent in registered), None)
        for name in files:
            operation_jobs.check()
            path = base / name
            if path.is_symlink():
                continue
            temporary = name.startswith(".repair-") and name.endswith(".tmp")
            if owner and not temporary:
                continue
            relative = path.relative_to(root)
            if temporary:
                group_path, kind = relative, "temporary_residue"
            else:
                parts = relative.parts
                marker = next((i for i, part in enumerate(parts[:-1])
                               if re.search(r"\[[^\]]+\]$", part) or re.fullmatch(r"[0-9a-fA-F]{32}", part)), None)
                length = marker + 1 if marker is not None else max(1, len(parts) - 1)
                group_path, kind = pathlib.Path(*parts[:length]), "unregistered_storage"
            key = str(group_path).replace("\\", "/")
            item = groups.setdefault(key, {"relative_path": key, "kind": kind, "count": 0,
                                           "package_count": 0, "size": 0, "recoverable": False})
            item["count"] += 1
            if path.suffix.lower() in _PACKAGE_EXTENSIONS:
                item["package_count"] += 1
                item["recoverable"] = True
            try:
                item["size"] += path.stat().st_size
            except OSError as error:
                warnings.append(f"Não foi possível ler o tamanho de {relative}: {error}")
    for item in groups.values():
        item["message"] = ("Temporário de um reparo incompleto. Nenhum arquivo será apagado automaticamente."
                           if item["kind"] == "temporary_residue" else
                           "Pasta sem registro ativo; pode conter arquivos preservados por Remover mod "
                           "ou uma importação interrompida. Revise antes de importar novamente.")
    return sorted(groups.values(), key=lambda item: item["relative_path"].casefold()), warnings


def inspect_library_health(verify_hashes=True, mod_ids=None):
    """Verificação explícita de cópias e hashes; não grava hashes em legados."""
    if mod_ids is not None and (not isinstance(mod_ids, list)
                               or not all(isinstance(value, str) for value in mod_ids)):
        return {"ok": False, "error": "Lista de mods inválida."}
    all_mods, settings = storage.load_mods(), storage.load_settings()
    selected = set(mod_ids) if mod_ids is not None else None
    mods = [mod for mod in all_mods if selected is None or mod.get("id") in selected]
    cache, issues, warnings = {}, [], []
    for index, mod in enumerate(mods):
        operation_jobs.progress("checking", f"Verificando mod {index + 1}/{len(mods)}: {mod.get('name', 'Mod')}", index, len(mods))
        issue = {"id": mod.get("id"), "mod_id": mod.get("id"), "name": mod.get("name") or "Mod sem nome",
                 "missing_backup": [], "missing_active": [], "missing_media": [], "hash_mismatches": [],
                 "unreadable": [], "unverifiable": [], "external_disabled": False}
        try:
            private, active = _roots(mod, settings)
        except (ValueError, OSError) as error:
            issue["unreadable"].append({"name": "Pasta do mod", "location": "library", "message": str(error)})
            issues.append(issue)
            continue
        expected_active = mod_ops._expected_active_file_names(mod) if mod.get("enabled") else set()
        if mod.get("install_target") and verify_hashes:
            warnings.append(f"{issue['name']}: os hashes ativos de Background/ReShade não são comparados; "
                            "complementos podem substituir esses arquivos intencionalmente.")
        for entry in _entries(mod):
            name = entry["name"]
            found = {}
            try:
                paths = {"library": _safe_child(private, name)}
                if active is not None and name in expected_active:
                    paths["game"] = _safe_child(active, name)
            except ValueError as error:
                issue["unreadable"].append({"name": name, "location": "library", "message": str(error)})
                continue
            for location, path in paths.items():
                compare = bool(verify_hashes) and (location == "library" or not mod.get("install_target"))
                # As camadas de Background não correspondem necessariamente a este mod.
                reference = entry if location == "library" or not mod.get("install_target") else {}
                health = _file_health(path, reference, compare, cache)
                found[location] = health
                if health["status"] == "missing":
                    issue["missing_backup" if location == "library" else "missing_active"].append(name)
                elif health["status"] == "unreadable":
                    issue["unreadable"].append({"name": name, "location": location, "message": health["message"]})
                elif health["status"] == "mismatch":
                    issue["hash_mismatches"].append({"name": name, "location": location,
                        **{key: value for key, value in health.items() if key not in {"status", "stamp"}}})
            if verify_hashes and not _expected_hash(entry):
                issue["unverifiable"].append(name)
                library, game = found.get("library", {}), found.get("game", {})
                if library.get("sha256") and game.get("sha256") and library["sha256"] != game["sha256"]:
                    issue["hash_mismatches"].append({"name": name, "location": "copies",
                        "library_sha256": library["sha256"], "game_sha256": game["sha256"],
                        "message": "As cópias divergem e não há hash original para escolher a correta."})
        issue["external_disabled"] = bool(mod.get("external") and not mod.get("enabled") and issue["missing_backup"])
        ignored = set(mod.get("ignored_missing_media") or [])
        media = list(dict.fromkeys([*(mod.get("images") or []), *([mod["image"]] if mod.get("image") else [])]))
        for name in media:
            if not name or name in ignored:
                continue
            try:
                if not _safe_child(private, name).is_file():
                    issue["missing_media"].append(name)
            except (ValueError, OSError) as error:
                issue["unreadable"].append({"name": name, "location": "media", "message": str(error)})
        if any(issue[key] for key in ("missing_backup", "missing_active", "missing_media", "hash_mismatches",
                                     "unreadable", "unverifiable", "external_disabled")):
            issues.append(issue)
    orphans, orphan_warnings = _find_orphans(all_mods) if selected is None else ([], [])
    operation_jobs.progress("checked", "Verificação concluída.", len(mods), len(mods))
    return {"ok": True, "checked": len(mods), "hashed_files": len(cache), "issues": issues, "orphans": orphans,
            "warnings": [*warnings, *orphan_warnings], "mods_path_configured": bool(settings.get("mods_path")),
            "hashes_checked": bool(verify_hashes),
            "legacy_note": "Arquivos antigos sem SHA-256 permanecem sem baseline; a verificação não modifica o catálogo."}


def _repair_fingerprint(mod, settings):
    private, active = _roots(mod, settings)
    value = {"id": mod.get("id"), "enabled": mod.get("enabled"), "external": mod.get("external"),
             "files": _entries(mod), "private": str(private), "active": str(active) if active is not None else None,
             "target": mod.get("install_target"), "expected_active": sorted(mod_ops._expected_active_file_names(mod)),
             "components": [{key: component.get(key) for key in ("id", "files", "enabled", "requires", "exclusive_group")}
                            for component in mod.get("components", [])]}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def preview_library_repair(mod_id):
    """Prepara cópias ausentes. Hash divergente nunca é aceito como origem."""
    mod = next((item for item in storage.load_mods() if item.get("id") == mod_id), None)
    if not mod:
        return {"ok": False, "error": "Mod não encontrado."}
    settings = storage.load_settings()
    try:
        private, active = _roots(mod, settings)
        fingerprint = _repair_fingerprint(mod, settings)
    except (ValueError, OSError) as error:
        return {"ok": False, "error": str(error)}
    actions, private_actions, blocked, warnings, cache = [], [], [], [], {}
    expected_active = mod_ops._expected_active_file_names(mod) if mod.get("enabled") else set()
    for entry in _entries(mod):
        name = entry["name"]
        try:
            backup = _safe_child(private, name)
            game = _safe_child(active, name) if active is not None else None
        except ValueError as error:
            blocked.append({"name": name, "reason": str(error)})
            continue
        candidates = []
        if not os.path.lexists(backup):
            candidates.append(("backup", game, backup))
        if game is not None and name in expected_active and not os.path.lexists(game):
            candidates.append(("active", backup, game))
        for direction, source, destination in candidates:
            if mod.get("install_target"):
                blocked.append({"name": name, "reason": "Use a reinstalação de Background/ReShade para preservar suas camadas."})
                continue
            if source is None or not source.is_file():
                blocked.append({"name": name, "reason": "Não há outra cópia disponível para restaurar este arquivo."})
                continue
            health = _file_health(source, entry, True, cache)
            if health["status"] != "ok":
                blocked.append({"name": name, "reason": "A cópia de origem está divergente, incompleta ou ilegível."})
                continue
            verification = "sha256" if _expected_hash(entry) else "size" if _expected_size(entry) is not None else "copy_only"
            if verification != "sha256":
                warnings.append(f"{name}: registro antigo sem hash original; confira a cópia disponível antes de restaurar.")
            public = {"id": secrets.token_hex(12), "name": name, "direction": direction,
                      "source_label": "Pasta do jogo" if direction == "backup" else "Biblioteca privada",
                      "destination_label": "Biblioteca privada" if direction == "backup" else "Pasta do jogo",
                      "verification": verification, "size": health["size"], "sha256": health["sha256"]}
            actions.append(public)
            private_actions.append({**public, "source": str(source), "destination": str(destination),
                                    "source_stamp": health["stamp"]})
    token = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _PLAN_LOCK:
        for key in list(_REPAIR_PLANS):
            if now - _REPAIR_PLANS[key]["created"] > _PLAN_LIFETIME:
                _REPAIR_PLANS.pop(key)
        while len(_REPAIR_PLANS) >= 32:
            _REPAIR_PLANS.pop(next(iter(_REPAIR_PLANS)))
        _REPAIR_PLANS[token] = {"created": now, "mod_id": mod_id, "fingerprint": fingerprint,
                                "actions": private_actions, "warnings": warnings}
    return {"ok": True, "token": token, "mod_id": mod_id, "actions": actions, "blocked": blocked,
            "warnings": warnings, "expires_in_seconds": _PLAN_LIFETIME,
            "note": "Somente destinos ausentes serão criados. Arquivos divergentes, mídias e sobras não serão removidos."}


def _copy_missing(source, destination, expected_sha256, revalidate):
    """Publica uma cópia completa sem substituir um destino criado depois da prévia."""
    destination = pathlib.Path(destination)
    revalidate()
    destination.parent.mkdir(parents=True, exist_ok=True)
    revalidate()
    descriptor, temporary = tempfile.mkstemp(prefix=".repair-", suffix=".tmp", dir=destination.parent)
    try:
        digest = hashlib.sha256()
        with os.fdopen(descriptor, "wb") as output, open(source, "rb") as input_file:
            before = _stamp(os.fstat(input_file.fileno()))
            for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
                output.write(chunk)
                digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
            if _stamp(os.fstat(input_file.fileno())) != before or digest.hexdigest() != expected_sha256:
                raise OSError("A cópia de origem mudou desde a prévia. Faça uma nova verificação.")
        revalidate()
        try:
            # A criação do hardlink falha se houver qualquer destino existente.
            os.link(temporary, destination)
        except FileExistsError:
            raise OSError("O destino passou a existir. Nenhum arquivo foi sobrescrito.") from None
        except OSError:
            if os.name != "nt":
                raise
            # No Windows rename também recusa destinos existentes, inclusive em FAT.
            os.rename(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


@mod_ops._serialized_files
def apply_library_repair(token, action_ids=None):
    if not isinstance(token, str):
        return {"ok": False, "error": "Plano de reparo inválido."}
    with _PLAN_LOCK:
        plan = _REPAIR_PLANS.pop(token, None)
    if not plan or time.monotonic() - plan["created"] > _PLAN_LIFETIME:
        return {"ok": False, "error": "A prévia expirou ou já foi usada. Gere uma nova prévia."}
    allowed = {action["id"] for action in plan["actions"]}
    if action_ids is not None and (not isinstance(action_ids, list)
            or not all(isinstance(value, str) and value in allowed for value in action_ids)):
        return {"ok": False, "error": "A seleção contém ações que não pertencem à prévia."}
    selected = set(action_ids) if action_ids is not None else allowed
    actions = [action for action in plan["actions"] if action["id"] in selected]
    result = {"ok": True, "repaired_backup": [], "repaired_active": [], "actions": [],
              "unavailable": [], "warnings": list(plan["warnings"])}

    def revalidate(action):
        settings = storage.load_settings()
        mod = next((item for item in storage.load_mods() if item.get("id") == plan["mod_id"]), None)
        if not mod or _repair_fingerprint(mod, settings) != plan["fingerprint"]:
            raise ValueError("O mod ou seu destino mudou desde a prévia. Gere uma nova prévia.")
        private, active = _roots(mod, settings)
        source_root, destination_root = ((active, private) if action["direction"] == "backup" else (private, active))
        if source_root is None or destination_root is None:
            raise ValueError("A pasta do jogo deixou de estar configurada.")
        if (str(_safe_child(source_root, action["name"])) != action["source"]
                or str(_safe_child(destination_root, action["name"])) != action["destination"]):
            raise ValueError("O caminho do arquivo mudou desde a prévia.")
        if os.path.lexists(action["destination"]):
            raise OSError("O destino passou a existir. Nenhum arquivo foi sobrescrito.")
        if action["direction"] == "active":
            mod_ops._ensure_game_operation_allowed()

    try:
        # Toda a seleção deve ser válida antes da primeira cópia.
        for action in actions:
            revalidate(action)
            source = _hash_file(action["source"])
            if source["sha256"] != action["sha256"] or source["size"] != action["size"]:
                raise OSError("A cópia de origem mudou desde a prévia. Gere uma nova prévia.")
        for action in actions:
            revalidate(action)
            _copy_missing(action["source"], action["destination"], action["sha256"], lambda: revalidate(action))
            result["repaired_backup" if action["direction"] == "backup" else "repaired_active"].append(action["name"])
            result["actions"].append({key: action[key] for key in ("id", "name", "direction", "verification")})
    except (OSError, ValueError, storage.ConcurrentUpdateError) as error:
        result.update(ok=False, error=str(error))
        repaired_ids = {action["id"] for action in result["actions"]}
        result["unavailable"] = [action["name"] for action in actions if action["id"] not in repaired_ids]
    if result["actions"]:
        try:
            mod_ops._record_activity("library_repair", "Arquivos ausentes restaurados após revisão",
                                     {"mod_id": plan["mod_id"], "files": len(result["actions"])})
        except (OSError, storage.ConcurrentUpdateError):
            result["warnings"].append("Os arquivos foram restaurados, mas não foi possível gravar o histórico.")
    return result


def _component_sources(mod, component, settings, roots=None):
    private, active = roots if roots is not None else _roots(mod, settings)
    sources = []
    for entry in component.get("files", []):
        name = entry.get("name", "") if isinstance(entry, dict) else ""
        backup = _safe_child_from_resolved_root(private, name)
        game = _safe_child_from_resolved_root(active, name) if active is not None else None
        if backup.is_file():
            sources.append(str(backup))
        elif game is not None and game.is_file():
            sources.append(str(game))
    return sources


def _classification_state(mod, component, settings, roots=None):
    try:
        files = _component_sources(mod, component, settings, roots)
        if not component.get("files") or len(files) != len(component["files"]):
            return "missing", [], _STATUS_MESSAGES["missing"]
    except (OSError, ValueError) as error:
        return "missing", [], str(error)
    signature = mod_ops._component_analysis_signature(files)
    cached = (mod.get("asset_path_cache") or {}).get(f"classification-v1:{component.get('id')}", {})
    paths, _ = mod_ops._component_cached_asset_paths(mod, component)
    types = mod_ops._component_types_from_metadata(mod, component)
    if cached.get("signature") == signature and cached.get("error"):
        status = "read_error"
    elif cached.get("signature") and cached.get("signature") != signature:
        status = "pending"
    elif not paths:
        previous_signature, _ = mod_ops._COMPONENT_ANALYSIS_RETRY.get(
            (mod.get("id"), component.get("id")), (None, 0))
        attempted = previous_signature == signature
        status = "read_error" if attempted else "pending"
    elif types == ["Unknown"]:
        status = "unrecognized"
    else:
        status = "analyzed"
    return status, types, _STATUS_MESSAGES[status]


def list_pending_classifications():
    """Lê catálogo, caches e stat; nunca chama o extrator de contêineres."""
    mods, settings = storage.load_mods(), storage.load_settings()
    components, counts = [], {key: 0 for key in _STATUS_MESSAGES if key != "analyzed"}
    checked = 0
    resolved_storage_root = pathlib.Path(storage.STORAGE_DIR).resolve()
    mods_path = str(settings.get("mods_path") or "")
    resolved_mods_root = pathlib.Path(mods_path).resolve() if mods_path else None
    for mod in mods:
        if mod.get("install_target"):
            continue
        package_components = [component for component in mod.get("components", [])
            if any(pathlib.PureWindowsPath(str(entry.get("name", ""))).suffix.lower() in _PACKAGE_EXTENSIONS
                   for entry in component.get("files", []) if isinstance(entry, dict))]
        if not package_components:
            continue
        try:
            roots, root_error = _roots(mod, settings, resolved_storage_root=resolved_storage_root,
                                       resolved_mods_root=resolved_mods_root), None
        except (OSError, ValueError) as error:
            roots, root_error = None, str(error)
        for component in package_components:
            checked += 1
            status, types, message = (("missing", [], root_error) if root_error is not None else
                                      _classification_state(mod, component, settings, roots))
            if status == "analyzed":
                continue
            counts[status] += 1
            components.append({"mod_id": mod.get("id"), "component_id": component.get("id"),
                "mod_name": mod.get("name") or "Mod sem nome", "component_name": component.get("name") or "Componente",
                "status": status, "types": types, "message": message,
                "identity_override": copy.deepcopy(mod.get("identity_override")), "enabled": component.get("enabled", True)})
    return {"ok": True, "components": components, "counts": counts, "checked": checked}


def reanalyze_selected_components(selections):
    """Reanalisa somente os IDs pedidos e mescla apenas tipos/cache em dados atuais."""
    if (not isinstance(selections, list) or not selections or any(not isinstance(item, dict)
            or not isinstance(item.get("mod_id"), str) or not isinstance(item.get("component_id"), str)
            for item in selections)):
        return {"ok": False, "error": "Selecione componentes válidos para reanalisar."}
    requested = list(dict.fromkeys((item["mod_id"], item["component_id"]) for item in selections))
    results, changed = [], 0
    with mod_ops._COMPONENT_ANALYSIS_LOCK:
        for mod_id, component_id in requested:
            result = {"mod_id": mod_id, "component_id": component_id, "ok": False, "changed": False}
            original = next((item for item in storage.load_mods() if item.get("id") == mod_id), None)
            component = next((item for item in (original or {}).get("components", []) if item.get("id") == component_id), None)
            if not component or original.get("install_target"):
                result["error"] = "Componente de PAK não encontrado."
                results.append(result)
                continue
            try:
                files = _component_sources(original, component, storage.load_settings())
                if not files or len(files) != len(component.get("files", [])):
                    result.update(status="missing", error=_STATUS_MESSAGES["missing"])
                    results.append(result)
                    continue
                signature = mod_ops._component_analysis_signature(files)
                error = ""
                try:
                    paths = mod_ops._paths_from_bundle(files)
                    if not paths:
                        error = _STATUS_MESSAGES["read_error"]
                except Exception as read_error:
                    paths, error = [], str(read_error)
                if mod_ops._component_analysis_signature(files) != signature:
                    raise ValueError("O pacote mudou durante a leitura; o resultado não foi aplicado.")
                mods = storage.load_mods()
                current = next((item for item in mods if item.get("id") == mod_id), None)
                target = next((item for item in (current or {}).get("components", []) if item.get("id") == component_id), None)
                if not target or target.get("files") != component.get("files"):
                    raise ValueError("O componente foi removido ou seus arquivos mudaram durante a análise.")
                live_files = _component_sources(current, target, storage.load_settings())
                if mod_ops._component_analysis_signature(live_files) != signature:
                    raise ValueError("Os arquivos atuais não correspondem à análise concluída.")
                if (target.get("type"), target.get("types")) != (component.get("type"), component.get("types")):
                    raise ValueError("A classificação foi alterada durante a leitura; sua alteração foi preservada.")
                cache = current.setdefault("asset_path_cache", {})
                key = f"classification-v1:{component_id}"
                if paths:
                    types = mod_ops._classify_component(dict(target, asset_paths=paths, type=None, types=[]))
                    target["types"], target["type"] = types, types[0]
                    cache[key] = {"signature": signature, "paths": paths}
                    mod_ops._COMPONENT_ANALYSIS_RETRY.pop((mod_id, component_id), None)
                    mod_ops._update_mod_component_types(current)
                    result.update(ok=True, changed=True, types=types,
                                  status="unrecognized" if types == ["Unknown"] else "analyzed")
                else:
                    # O erro persiste sem apagar a identidade, os tipos anteriores ou caches de outros componentes.
                    cache[key] = {"signature": signature, "paths": [], "error": error, "attempted_at": storage.now_iso()}
                    mod_ops._COMPONENT_ANALYSIS_RETRY[(mod_id, component_id)] = (signature, time.monotonic())
                    result.update(status="read_error", error=error)
                storage.save_mods(mods)
                if result["changed"]:
                    changed += 1
            except (OSError, ValueError, storage.ConcurrentUpdateError) as error:
                result.update(ok=False, changed=False, error=str(error))
            results.append(result)
    return {"ok": True, "results": results, "changed": changed,
            "failed": sum(not item["ok"] for item in results)}


def _words(value):
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(value or ""))
    value = "".join(char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)).casefold()
    value = re.sub(r"(?:[_\s-]*9{4,}[_\s-]*p)\b", "", value)
    return re.findall(r"[a-z0-9]+", value)


def _mask_variant(component):
    words = _words(component.get("name"))
    pairs = {("mask", "on"): "on", ("mask", "off"): "off", ("with", "mask"): "on",
             ("without", "mask"): "off", ("com", "mascara"): "on", ("sem", "mascara"): "off"}
    for index in range(len(words) - 1):
        pair = tuple(words[index:index + 2])
        if pair in pairs:
            return tuple(words[:index] + words[index + 2:]), pairs[pair]
    for index, word in enumerate(words):
        if word in {"masked", "unmasked"}:
            return tuple(words[:index] + words[index + 1:]), "on" if word == "masked" else "off"
    return None


def suggest_component_relations(mod_id, component_id=None):
    """Sugestões justificadas para revisão; não lê PAKs nem aplica dependências."""
    mod = next((item for item in storage.load_mods() if item.get("id") == mod_id), None)
    return _describe_relation_suggestions(mod, component_id)


def _describe_relation_suggestions(mod, component_id=None):
    """Usa um único retrato do catálogo também ao preparar a prévia."""
    if not mod or mod.get("install_target"):
        return {"ok": False, "error": "Sugestões disponíveis apenas para componentes de PAKs."}
    if component_id is not None and not isinstance(component_id, str):
        return {"ok": False, "error": "Componente inválido."}
    components = [component for component in mod.get("components", []) if component.get("id")]
    if component_id is not None and component_id not in {item["id"] for item in components}:
        return {"ok": False, "error": "Componente não encontrado."}
    by_id = {component["id"]: component for component in components}
    suggestions, seen = [], set()
    try:
        closures = mod_ops.component_rules.validate(components)
    except ValueError as error:
        return {"ok": False, "error": f"Revise as relações existentes antes de gerar sugestões: {error}"}
    reserved_groups = {str(item.get("exclusive_group") or "").strip().casefold() for item in components} - {""}

    def alternative(ids, reason, confidence, proposed_group):
        ids = [item["id"] for item in components if item["id"] in set(ids)]
        key = frozenset(ids)
        if len(ids) < 2 or key in seen:
            return
        if any((closures[cid] - {cid}) & key for cid in ids):
            return
        groups = {str(by_id[cid].get("exclusive_group") or "").strip() for cid in ids}
        if len(groups) == 1 and "" not in groups:
            return
        if len(groups - {""}) > 1:
            return
        existing = groups - {""}
        if existing:
            proposed_group = next(iter(existing))
        else:
            base, suffix = proposed_group, 2
            while proposed_group.casefold() in reserved_groups:
                proposed_group = f"{base} {suffix}"
                suffix += 1
        reserved_groups.add(proposed_group.casefold())
        seen.add(key)
        suggestions.append({"kind": "alternative_group", "component_ids": ids,
            "component_names": [by_id[cid].get("name") or cid for cid in ids],
            "proposed_group": proposed_group, "reason": reason, "confidence": confidence,
            "warnings": ["Revise as variantes e escolha qual ficará ativa antes de salvar. Nenhuma regra foi aplicada."]})

    families = {}
    for component in components:
        signature = _mask_variant(component)
        if signature:
            family, variant = signature
            families.setdefault(family, {}).setdefault(variant, []).append(component["id"])
    for variants in families.values():
        if "on" in variants and "off" in variants:
            alternative([*variants["on"], *variants["off"]],
                        "Os nomes identificam versões com e sem máscara da mesma família.", "name_pair", "Máscara")

    types = {item["id"]: mod_ops._component_types_from_metadata(mod, item) for item in components}
    meshes = [item for item in components if "Mesh" in types[item["id"]]]
    mesh_assets = {}
    for component in meshes:
        paths, _ = mod_ops._component_cached_asset_paths(mod, component)
        for path in paths:
            if mod_ops._is_mesh_asset_path(path):
                mesh_assets.setdefault(mod_ops._conflict_asset_key(path), []).append(component["id"])
    for asset, ids in mesh_assets.items():
        alternative(ids, f"O cache mostra substituição da mesma malha: {asset}", "cached_asset", "Variação visual")

    # Física pura pode acompanhar uma base, mas o nome sozinho não prova a dependência.
    for component in components:
        cid = component["id"]
        if "Physics" not in types[cid] or "Mesh" in types[cid] or component.get("requires"):
            continue
        ignored_words = {"physics", "phys", "jiggle", "addon", "add", "on", "p", "pak"}
        meaningful = lambda name: {word for word in _words(name) if word not in ignored_words
                                   and not re.fullmatch(r"v?\d+", word)}
        physics_words = meaningful(component.get("name"))
        candidates = [base for base in meshes if meaningful(base.get("name"))
                      and meaningful(base.get("name")) <= physics_words]
        if len(candidates) != 1:
            continue
        base = candidates[0]
        if cid in closures[base["id"]]:
            continue
        suggestions.append({"kind": "dependency_candidate", "component_id": cid,
            "component_ids": [cid, base["id"]], "component_names": [component.get("name"), base.get("name")],
            "requires": [base["id"]], "proposed_group": "", "confidence": "review_required",
            "reason": "O componente contém física e seu nome se relaciona a uma única base visual deste mod.",
            "warnings": ["Confirme na documentação do mod se esta base é necessária. Nomes e tipos não comprovam dependência.",
                         "A sugestão não será aplicada automaticamente."]})
    if component_id is not None:
        suggestions = [item for item in suggestions if component_id in item["component_ids"]]
    for item in suggestions:
        identity = {"kind": item["kind"], "components": sorted(item["component_ids"]),
                    "group": item.get("proposed_group"), "requires": item.get("requires")}
        item["id"] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    return {"ok": True, "suggestions": suggestions,
            "note": "São sugestões para revisão. Regras existentes e switches permanecem inalterados."}


def _relation_fingerprint(mod, settings):
    # Nomes/tipos influenciam a sugestão; etiquetas, galeria e outros campos não.
    private, active = _roots(mod, settings)
    for entry in _entries(mod):
        _safe_child(private, entry["name"])
        if active is not None:
            _safe_child(active, entry["name"])
    value = {"files": _repair_fingerprint(mod, settings), "components": [
        {**{key: component.get(key) for key in ("id", "name", "type", "types")},
         "asset_paths": mod_ops._component_cached_asset_paths(mod, component)[0]}
        for component in mod.get("components", [])]}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def preview_relation_suggestion(mod_id, suggestion_id, preferred_component_id=None):
    """Mostra regras e switches afetados antes de aplicar uma sugestão inteira."""
    if not isinstance(suggestion_id, str) or (preferred_component_id is not None
                                             and not isinstance(preferred_component_id, str)):
        return {"ok": False, "error": "Sugestão ou variante inválida."}
    mod = next((item for item in storage.load_mods() if item.get("id") == mod_id), None)
    described = _describe_relation_suggestions(mod)
    if not described.get("ok"):
        return described
    suggestion = next((item for item in described["suggestions"] if item["id"] == suggestion_id), None)
    if not suggestion:
        return {"ok": False, "error": "A sugestão mudou ou não existe mais. Atualize as sugestões."}
    proposed = copy.deepcopy(mod.get("components", []))
    participants = set(suggestion["component_ids"])
    try:
        if suggestion["kind"] == "alternative_group":
            if preferred_component_id is not None and preferred_component_id not in participants:
                raise ValueError("A variante preferida não pertence à sugestão.")
            for component in proposed:
                if component["id"] in participants:
                    component["exclusive_group"] = suggestion["proposed_group"]
            active = [component["id"] for component in proposed if component["id"] in participants
                      and component.get("enabled", True)]
            preferred = preferred_component_id or next(iter(active), None)
            if preferred is not None:
                proposed = mod_ops.component_rules.changed_state(proposed, preferred, True)
            else:
                mod_ops.component_rules.assert_valid_state(proposed)
        else:
            target = next(item for item in proposed if item["id"] == suggestion["component_id"])
            target["requires"] = list(dict.fromkeys([*(target.get("requires") or []), *suggestion["requires"]]))
            proposed = mod_ops.component_rules.changed_state(proposed, target["id"], target.get("enabled", True))
            preferred = None
        settings = storage.load_settings()
        fingerprint = _relation_fingerprint(mod, settings)
    except (OSError, ValueError, StopIteration) as error:
        return {"ok": False, "error": str(error)}
    previous = {item["id"]: item for item in mod.get("components", [])}
    rule_changes, state_changes = [], []
    for item in proposed:
        old = previous[item["id"]]
        before = {"exclusive_group": old.get("exclusive_group") or "", "requires": old.get("requires") or []}
        after = {"exclusive_group": item.get("exclusive_group") or "", "requires": item.get("requires") or []}
        if before != after:
            rule_changes.append({"component_id": item["id"], "name": item.get("name") or item["id"],
                                 "before": before, "after": after})
        if old.get("enabled", True) != item.get("enabled", True):
            state_changes.append({"component_id": item["id"], "name": item.get("name") or item["id"],
                                  "before": old.get("enabled", True), "after": item.get("enabled", True)})
    token, now = secrets.token_urlsafe(32), time.monotonic()
    with _PLAN_LOCK:
        for key in list(_RELATION_PLANS):
            if now - _RELATION_PLANS[key]["created"] > _PLAN_LIFETIME:
                _RELATION_PLANS.pop(key)
        while len(_RELATION_PLANS) >= 32:
            _RELATION_PLANS.pop(next(iter(_RELATION_PLANS)))
        _RELATION_PLANS[token] = {"mod_id": mod_id, "created": now, "fingerprint": fingerprint,
                                  "rule_changes": rule_changes, "state_changes": state_changes}
    return {"ok": True, "token": token, "mod_id": mod_id, "suggestion": suggestion,
            "rule_changes": rule_changes, "state_changes": state_changes, "warnings": suggestion["warnings"],
            "preferred_component_id": preferred,
            "affects_game": bool(mod.get("enabled") and settings.get("mods_path") and state_changes),
            "note": "Salvar aplica todas as regras juntas. Revise também componentes desativados por dependências."}


@mod_ops._serialized_files
def apply_relation_suggestion(token):
    if not isinstance(token, str):
        return {"ok": False, "error": "Plano de relações inválido."}
    with _PLAN_LOCK:
        plan = _RELATION_PLANS.pop(token, None)
    if not plan or time.monotonic() - plan["created"] > _PLAN_LIFETIME:
        return {"ok": False, "error": "A prévia expirou ou já foi aplicada. Revise novamente."}
    mods, settings = storage.load_mods(), storage.load_settings()
    mod = next((item for item in mods if item.get("id") == plan["mod_id"]), None)
    applied = False
    try:
        if not mod or _relation_fingerprint(mod, settings) != plan["fingerprint"]:
            raise ValueError("Os componentes ou destinos mudaram desde a prévia. Revise novamente.")
        previous = copy.deepcopy(mod.get("components", []))
        by_id = {item["id"]: item for item in mod.get("components", [])}
        for change in plan["rule_changes"]:
            by_id[change["component_id"]].update(copy.deepcopy(change["after"]))
        for change in plan["state_changes"]:
            by_id[change["component_id"]]["enabled"] = change["after"]
        mod_ops.component_rules.assert_valid_state(mod["components"])
        mod_ops._apply_component_states(mod, previous, str(settings.get("mods_path") or ""))
        applied = True
        storage.save_mods(mods)
    except (OSError, ValueError, storage.ConcurrentUpdateError) as error:
        warnings = []
        if applied:
            attempted, mod["components"] = mod["components"], previous
            try:
                mod_ops._apply_component_states(mod, attempted, str(settings.get("mods_path") or ""))
            except (OSError, ValueError) as rollback_error:
                warnings.append(f"Falhou a restauração dos switches; confira a integridade: {rollback_error}")
        return {"ok": False, "error": str(error), "warnings": warnings}
    warnings = []
    try:
        mod_ops._record_activity("component_rules", "Sugestão de relações aplicada após revisão", {"mod_id": mod["id"]})
    except (OSError, storage.ConcurrentUpdateError):
        warnings.append("As relações foram salvas, mas não foi possível gravar o histórico.")
    return {"ok": True, "mod_id": mod["id"], "rule_changes": plan["rule_changes"],
            "state_changes": plan["state_changes"], "warnings": warnings}
