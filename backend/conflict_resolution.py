"""Resolução assistida sobre a política de conflitos já usada pelo Manager.

A prévia é somente leitura e não muda prioridades. A aplicação exige a mesma
prévia, recalcula os conflitos e registra arquivos e catálogo para recuperação.
"""
import copy
import hashlib
import json
import os
import pathlib
import secrets
import threading
import time

from . import component_rules, mod_ops, storage


_PREVIEWS = {}
_PREVIEW_LOCK = threading.RLock()
_PREVIEW_TTL = 15 * 60
_WHOLE_MOD = {"whole-mod", "manual-conflict"}


def _safe_child(root, name):
    base = pathlib.Path(root).resolve()
    path = (base / name).resolve()
    if path == base or not path.is_relative_to(base):
        raise ValueError("Um arquivo do mod aponta para fora da pasta permitida.")
    return str(path)


def _file_key(path):
    return os.path.normcase(os.path.abspath(path))


def _component_rows(mod):
    return mod.get("components") or [{
        "id": "whole-mod", "name": mod.get("name", "Mod"),
        "enabled": True, "files": mod_ops._all_mod_file_entries(mod),
    }]


def _active_files(mod, mods_path):
    if not mod.get("enabled") or not mods_path:
        return set()
    target = mod_ops._game_target_dir(mod, mods_path)
    return {
        _safe_child(target, entry["name"])
        for component in _component_rows(mod) if component.get("enabled", True)
        for entry in component.get("files", []) if entry.get("name")
    }


def _change_row(mod, component, reason, assets=()):
    return {
        "mod_id": mod["id"], "mod": mod.get("name", "Mod"),
        "component_id": component.get("id", "whole-mod"),
        "component": component.get("name", "Mod inteiro"),
        "reason": reason, "assets": sorted(set(assets)),
        "enabled_before": True, "enabled_after": False,
    }


def _state_for_fingerprint(mod):
    keys = ("id", "name", "enabled", "character", "skin", "priority", "folder",
            "storage_folder", "external", "install_target", "files", "manual_conflicts")
    result = {key: mod.get(key) for key in keys}
    result["components"] = [{key: component.get(key) for key in (
        "id", "name", "enabled", "description", "requires", "exclusive_group", "files",
        "type", "types",
    )} for component in mod.get("components", [])]
    return result


def _file_signature(path):
    try:
        stat = os.stat(path)
        return [path, stat.st_size, stat.st_mtime_ns]
    except FileNotFoundError:
        return [path, None, None]


def _build_plan(mods, settings, mod_id, component_id):
    by_id = {str(mod.get("id")): mod for mod in mods}
    keep = by_id.get(str(mod_id))
    if not keep or not keep.get("enabled"):
        raise ValueError("O mod escolhido não existe ou está desativado.")
    if keep.get("install_target"):
        raise ValueError("Use os switches próprios de Background/ReShade para resolver esses conflitos.")
    components = _component_rows(keep)
    closures = component_rules.validate(components)
    keep_component = next((c for c in components if str(c.get("id")) == str(component_id)), None)
    whole = str(component_id) in _WHOLE_MOD
    if not whole and (not keep_component or not keep_component.get("enabled", True)):
        raise ValueError("O componente escolhido não existe ou está desativado.")
    protected = ({c["id"] for c in components if c.get("enabled", True)} if whole
                 else closures[keep_component["id"]])
    if not protected <= {c["id"] for c in components if c.get("enabled", True)}:
        raise ValueError("O componente escolhido tem uma dependência desativada; corrija a relação antes de continuar.")

    # O detector pode preencher caches na cópia, mas a prévia não os persiste.
    report = mod_ops.get_conflicts(persist_cache=False, _mods=[dict(mod) for mod in mods])
    if not report.get("ok"):
        raise ValueError(report.get("error") or "Não foi possível verificar os conflitos.")
    targets, relevant = {}, []
    for conflict in report.get("conflicts", []):
        selected = [owner for owner in conflict.get("owners", [])
                    if str(owner.get("mod_id")) == str(mod_id)
                    and (whole or owner.get("component_id") in protected
                         or owner.get("component_id") in _WHOLE_MOD)]
        if not selected:
            continue
        if conflict.get("kind") != "manual" and any(
            mod_ops._conflict_owners_overlap(left, right)
            for index, left in enumerate(selected) for right in selected[index + 1:]
        ):
            raise ValueError("Os componentes que precisam permanecer ativos conflitam entre si. Revise as relações ou escolha somente uma variante.")
        rivals = []
        for owner in conflict.get("owners", []):
            if owner in selected:
                continue
            if not any(conflict.get("kind") == "manual" or mod_ops._conflict_owners_overlap(chosen, owner)
                       for chosen in selected):
                continue
            owner_mod = str(owner.get("mod_id"))
            cid = str(owner.get("component_id"))
            target = targets.setdefault(owner_mod, {"whole": False, "components": {}, "assets": set()})
            target["whole"] |= cid in _WHOLE_MOD or conflict.get("kind") == "manual"
            target["components"].setdefault(cid, set()).add(conflict["asset_path"])
            target["assets"].add(conflict["asset_path"])
            rivals.append({"mod_id": owner_mod, "component_id": cid})
        if rivals:
            relevant.append({"asset_path": conflict["asset_path"], "kind": conflict.get("kind", "automatic"),
                             "rivals": rivals})

    if not targets:
        raise ValueError("O detector atual não encontrou conflitos para essa escolha.")
    before, after, changes, warnings = [], [], [], []
    for target_id, target in targets.items():
        mod = by_id.get(target_id)
        if not mod or mod.get("install_target"):
            raise ValueError("Há um Background/ReShade entre os concorrentes. Use seus switches próprios antes de continuar.")
        proposed = copy.deepcopy(mod)
        if target["whole"]:
            if target_id == str(mod_id):
                raise ValueError("A resolução desativaria o mod escolhido. Nenhuma alteração foi feita.")
            proposed["enabled"] = False
            changes.append(_change_row(mod, {"id": "whole-mod", "name": "Mod inteiro"},
                                       "manual_conflict" if any(cid == "manual-conflict" for cid in target["components"])
                                       else "conflict", target["assets"]))
            if mod.get("components"):
                warnings.append(f"{mod.get('name', 'Mod')}: o mod inteiro será desativado; as escolhas de variantes serão preservadas.")
        else:
            local_closures = component_rules.validate(proposed.get("components", []))
            direct = set(target["components"])
            if not direct <= set(local_closures):
                raise ValueError("Um componente concorrente foi removido. Atualize os conflitos.")
            for component in proposed.get("components", []):
                cid = component["id"]
                if not component.get("enabled", True) or not (local_closures[cid] & direct):
                    continue
                if target_id == str(mod_id) and cid in protected:
                    raise ValueError("A resolução desativaria o componente escolhido ou uma dependência necessária. Revise as relações antes de continuar.")
                component["enabled"] = False
                changes.append(_change_row(mod, component, "conflict" if cid in direct else "dependency",
                                           target["components"].get(cid, ())))
            component_rules.assert_valid_state(proposed.get("components", []))
        if proposed.get("external"):
            proposed["external"] = False
        before.append(copy.deepcopy(mod))
        after.append(proposed)

    mods_path = str(settings.get("mods_path") or "")
    if not mods_path:
        raise ValueError("Configure a pasta de mods do jogo antes de resolver conflitos.")
    if not os.path.isdir(mods_path):
        raise ValueError("A pasta de mods configurada não está disponível.")
    after_by_id = {str(mod["id"]): mod for mod in after}
    surviving_paths = set()
    for mod in mods:
        current = after_by_id.get(str(mod.get("id")), mod)
        if current.get("install_target"):
            continue
        surviving_paths.update(_file_key(path) for path in _active_files(current, mods_path))

    file_pairs, source_checks = {}, set()
    for old, new in zip(before, after):
        game_dir = mod_ops._game_target_dir(old, mods_path)
        private_dir = mod_ops._storage_dir(old)
        old_active_names = mod_ops._expected_active_file_names(old)
        new_active_names = mod_ops._expected_active_file_names(new) if new.get("enabled") else set()
        removed_names = old_active_names - new_active_names
        if not new.get("enabled"):
            removed_names |= {entry["name"] for entry in mod_ops._all_mod_file_entries(old)}
        removed = {_safe_child(game_dir, name) for name in removed_names}
        # Dois registros antigos podem apontar fisicamente para o mesmo arquivo.
        # Desativar um deles não pode remover um pacote de quem vai permanecer.
        if any(_file_key(path) in surviving_paths for path in removed):
            raise ValueError("Registros antigos compartilham o mesmo arquivo ativo. Separe suas pastas antes de usar esta resolução.")
        for name in removed_names:
            active = _safe_child(game_dir, name)
            private = _safe_child(private_dir, name)
            _safe_child(mods_path, os.path.relpath(active, mods_path))
            _safe_child(storage.STORAGE_DIR, os.path.relpath(private, storage.STORAGE_DIR))
            file_pairs[_file_key(active)] = (active, mods_path)
            source_checks.add(private)
            if name in old_active_names and not old.get("external") and not os.path.isfile(private):
                raise ValueError(f"Backup privado ausente em {old.get('name', 'Mod')}: {name}. Repare a biblioteca antes de desativar.")
            if name in old_active_names and old.get("external") and not os.path.isfile(active):
                raise ValueError(f"Arquivo ativo ausente em {old.get('name', 'Mod')}: {name}.")
        if old.get("external"):
            for entry in mod_ops._all_mod_file_entries(old):
                active = _safe_child(game_dir, entry["name"])
                private = _safe_child(private_dir, entry["name"])
                if os.path.isfile(active):
                    file_pairs[_file_key(private)] = (private, storage.STORAGE_DIR)

    before_by_id = {str(mod["id"]): mod for mod in before}
    before_by_id[str(mod_id)] = keep
    keep_files = _active_files(keep, mods_path)
    if not keep_files or any(not os.path.isfile(path) for path in keep_files):
        raise ValueError("O mod escolhido tem arquivos ativos ausentes. Repare a biblioteca antes de resolver conflitos.")
    inspect_paths = {path for path, _ in file_pairs.values()} | source_checks | keep_files
    fingerprint_data = {
        "mods_path": mods_path, "keep": [str(mod_id), str(component_id)],
        "states": [_state_for_fingerprint(before_by_id[key]) for key in sorted(before_by_id)],
        "conflicts": sorted(relevant, key=lambda item: (item["asset_path"], item["kind"])),
        "files": [_file_signature(path) for path in sorted(inspect_paths)],
    }
    fingerprint = hashlib.sha256(json.dumps(fingerprint_data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    keep_public = {"mod_id": keep["id"], "mod": keep.get("name", "Mod"),
                   "component_id": str(component_id), "component": "Mod inteiro" if whole else keep_component.get("name", "Componente")}
    if report.get("unreadable"):
        warnings.append(f"{len(report['unreadable'])} componente(s) não puderam ser analisados. A resolução cobre somente os conflitos detectados.")
    return {
        "fingerprint": fingerprint, "before": before, "after": after,
        "file_pairs": list(file_pairs.values()), "mods_path": mods_path,
        "public": {"ok": True, "keep": keep_public, "changes": changes,
                   "conflicts": relevant, "warnings": warnings,
                   "note": "Somente os concorrentes listados serão desativados. As prioridades não serão alteradas."},
    }


@mod_ops._serialized_files
def preview_resolution(mod_id, component_id):
    """Lista a consequência da escolha, sem salvar catálogo nem tocar arquivos."""
    try:
        plan = _build_plan(storage.load_mods(), storage.load_settings(), mod_id, component_id)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {"ok": False, "error": str(error), "changes": []}
    now = time.monotonic()
    token = secrets.token_urlsafe(24)
    with _PREVIEW_LOCK:
        expired = [key for key, value in _PREVIEWS.items() if value["expires"] <= now]
        for key in expired:
            _PREVIEWS.pop(key, None)
        while len(_PREVIEWS) >= 30:
            _PREVIEWS.pop(next(iter(_PREVIEWS)))
        _PREVIEWS[token] = {"expires": now + _PREVIEW_TTL, "mod_id": str(mod_id),
                            "component_id": str(component_id), "fingerprint": plan["fingerprint"]}
    return {**plan["public"], "token": token}


@mod_ops._serialized_files
def apply_resolution(token):
    """Revalida a prévia e aplica uma única alteração recuperável do catálogo."""
    with _PREVIEW_LOCK:
        preview = _PREVIEWS.pop(str(token), None)
    if not preview or preview["expires"] <= time.monotonic():
        return {"ok": False, "stale": True, "error": "A prévia expirou. Gere uma nova antes de aplicar.", "changed": []}
    mods = storage.load_mods()
    try:
        plan = _build_plan(mods, storage.load_settings(), preview["mod_id"], preview["component_id"])
        if plan["fingerprint"] != preview["fingerprint"]:
            return {"ok": False, "stale": True, "error": "A biblioteca mudou desde a prévia. Confira uma nova prévia antes de aplicar.", "changed": []}
        mod_ops._ensure_game_operation_allowed()
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {"ok": False, "error": str(error), "changed": []}

    from . import operation_recovery
    journal = None
    committed = False
    try:
        journal = operation_recovery.Journal.create(
            "resolve_conflicts", "Resolver conflitos por escolha", before_records=plan["before"],
            after_records=plan["after"], mods_path=plan["mods_path"],
        )
        journal.capture_files(plan["file_pairs"])
        journal.mark("applying")
        by_id = {str(mod["id"]): mod for mod in mods}
        for before, after in zip(plan["before"], plan["after"]):
            mod = by_id[str(before["id"])]
            if before.get("external"):
                game_dir = mod_ops._game_target_dir(before, plan["mods_path"])
                private_dir = mod_ops._storage_dir(before)
                for entry in mod_ops._all_mod_file_entries(before):
                    source = _safe_child(game_dir, entry["name"])
                    if os.path.isfile(source):
                        destination = _safe_child(private_dir, entry["name"])
                        mod_ops._install_file_fast(source, destination)
                mod["external"] = False
            if not after.get("enabled"):
                # Os registros legados podem ter arquivos apenas em components.
                operation_mod = copy.deepcopy(mod)
                operation_mod["files"] = mod_ops._all_mod_file_entries(mod)
                mod_ops._apply_enable(operation_mod, plan["mods_path"], False)
            else:
                mod["components"] = copy.deepcopy(after.get("components", []))
                mod_ops._apply_component_states(mod, before.get("components", []), plan["mods_path"])
            mod["enabled"] = after.get("enabled", False)
        storage.save_mods(mods)
        committed = True
        journal.mark("catalog_saved")
        journal.finish("completed")
    except (OSError, ValueError, KeyError, storage.ConcurrentUpdateError) as error:
        if committed:
            if journal:
                try:
                    journal.fail(error)
                except (OSError, storage.ConcurrentUpdateError):
                    pass
            return {"ok": True, "changed": [mod["id"] for mod in plan["after"]],
                    "changes": plan["public"]["changes"],
                    "warnings": [f"A resolução foi aplicada, mas o registro de recuperação precisa de revisão: {error}"], "errors": []}
        rollback_errors = []
        if journal:
            try:
                if journal.data.get("mutation_started"):
                    mod_ops._ensure_game_operation_allowed()
                operation_recovery.rollback(journal)
            except (OSError, ValueError, storage.ConcurrentUpdateError) as recovery_error:
                rollback_errors.append(str(recovery_error))
                try:
                    journal.fail(recovery_error)
                except (OSError, storage.ConcurrentUpdateError) as journal_error:
                    rollback_errors.append(str(journal_error))
        return {"ok": False, "error": str(error), "changed": [], "errors": rollback_errors,
                "recovery_pending": bool(rollback_errors), "rolled_back": not rollback_errors}

    warnings = []
    changed = [mod["id"] for mod in plan["after"]]
    try:
        mod_ops._record_activity("resolve_conflicts", f"Conflitos resolvidos mantendo {plan['public']['keep']['mod']}",
                                 {"mod_ids": changed, "keep": plan["public"]["keep"]})
    except (OSError, storage.ConcurrentUpdateError) as error:
        warnings.append(f"A resolução foi aplicada, mas não foi possível salvar o histórico: {error}")
    return {"ok": True, "changed": changed, "changes": plan["public"]["changes"], "warnings": warnings, "errors": []}
