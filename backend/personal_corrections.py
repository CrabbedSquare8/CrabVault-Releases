"""Correções escolhidas pelo usuário, reutilizáveis somente por conteúdo igual.

A busca usa hashes já calculados na importação. Não abre arquivos da biblioteca,
não tenta identificar conteúdo por nomes e nunca aplica uma oferta sozinha.
"""
import copy
import hashlib
import json
import pathlib
import re
import secrets
import threading
import time
from collections import Counter

from . import component_rules, storage
from .characters import MARVEL_CHARACTERS


_OFFERS = {}
_LOCK = threading.RLock()
_TTL = 60 * 60
_FIELDS = ("name", "description", "exclusive_group", "requires")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def component_fingerprint(component):
    """Todos os arquivos contam; nomes, caminhos e IDs não identificam conteúdo."""
    entries = component.get("files") or []
    if not entries:
        return None
    parts = []
    for entry in entries:
        digest = str(entry.get("sha256") or "").lower()
        suffix = pathlib.PureWindowsPath(str(entry.get("name") or "")).suffix.lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or not suffix:
            return None
        # SHA-256 já identifica todos os bytes; exigir tamanho impediria o
        # reaproveitamento de registros antigos que guardaram somente hashes.
        parts.append((suffix, digest))
    return _digest(sorted(parts))


def _component_values(component, fields):
    values = {}
    for field in fields:
        if field not in _FIELDS:
            continue
        if field == "requires":
            requires = component.get(field) or []
            if not isinstance(requires, list) or not all(isinstance(item, str) for item in requires):
                continue
            values[field] = list(dict.fromkeys(requires))
        else:
            value = str(component.get(field) or "").strip()
            if field in {"description", "exclusive_group"} and len(value) > 80:
                continue
            if field == "name" and not value:
                continue
            values[field] = value
    return values


def _snapshot_mod(mod, previous=None, identity=False, component_fields=None):
    if mod.get("install_target") or not mod.get("id"):
        return None
    previous = previous or {}
    old_components = {c.get("id"): c for c in previous.get("components", [])}
    component_fields = component_fields or {}
    components = []
    for component in mod.get("components", []):
        cid = component.get("id")
        if not cid:
            continue
        fields = set((old_components.get(cid) or {}).get("values", {}))
        fields.update(component_fields.get(cid, []))
        # Bancos antigos não registravam a origem de cada nome. Só reutilizamos
        # nomes que diferem do nome original do pacote, sempre após escolha.
        names = {pathlib.PureWindowsPath(str(entry.get("original_name") or entry.get("name") or "")).stem
                 for entry in component.get("files", [])}
        if component.get("name") and component["name"] not in names:
            fields.add("name")
        if component.get("description"):
            fields.add("description")
        if component.get("exclusive_group") or component.get("requires"):
            fields.update(("exclusive_group", "requires"))
        components.append({"id": cid, "fingerprint": component_fingerprint(component),
                           "name": component.get("name") or "Componente",
                           "values": _component_values(component, fields)})
    explicit_identity = bool(identity or previous.get("identity_explicit") or isinstance(mod.get("identity_override"), dict))
    chosen_identity = ({"character": mod.get("character") or "Generic", "skin": mod.get("skin") or ""}
                       if explicit_identity else None)
    return {"id": str(mod["id"]), "source_name": mod.get("name") or "Mod",
            "identity": chosen_identity, "identity_explicit": explicit_identity, "components": components}


def remember_mod(mod, *, identity=False, component_fields=None):
    """Guarda após uma edição bem-sucedida; falha do histórico não desfaz a edição."""
    if mod.get("install_target"):
        return []
    try:
        data = storage.load_personal_corrections()
        previous = next((r for r in data["records"] if r.get("id") == str(mod.get("id"))), None)
        record = _snapshot_mod(mod, previous, identity, component_fields)
        if not record:
            return []
        if not any(c["fingerprint"] for c in record["components"]):
            return ["A alteração foi salva. Não há hashes suficientes para reconhecê-la em uma reimportação."]
        record["updated_at"] = storage.now_iso()
        data["records"] = [r for r in data["records"] if r.get("id") != record["id"]] + [record]
        storage.save_personal_corrections(data)
        return []
    except (OSError, ValueError, storage.ConcurrentUpdateError) as error:
        return [f"A alteração foi salva, mas não foi possível guardar a correção para reimportação: {error}"]


def _candidates():
    data = storage.load_personal_corrections()
    records = {}
    for record in data["records"]:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
            continue
        components = record.get("components")
        if not isinstance(components, list) or any(
                not isinstance(c, dict) or not isinstance(c.get("id"), str) or not c["id"]
                or not isinstance(c.get("values"), dict) or not isinstance(c.get("name"), str)
                or (c.get("fingerprint") is not None and not re.fullmatch(r"[0-9a-f]{64}", str(c["fingerprint"])))
                for c in components):
            continue
        if len({c["id"] for c in components}) != len(components):
            continue
        record = copy.deepcopy(record)
        record["source_name"] = str(record.get("source_name") or "Mod")
        for component in record["components"]:
            component["values"] = _component_values(component["values"], component["values"].keys())
        chosen_identity = record.get("identity")
        if chosen_identity is not None and (not isinstance(chosen_identity, dict)
                or chosen_identity.get("character") not in [*MARVEL_CHARACTERS, "Generic"]
                or not isinstance(chosen_identity.get("skin"), str)):
            record["identity"] = None
            record["identity_explicit"] = False
        records[record["id"]] = record
    for mod in storage.load_mods():
        record = _snapshot_mod(mod, records.get(str(mod.get("id"))))
        if record:
            records[record["id"]] = record
    return records


def _candidate_signature(record):
    # Horário do histórico não é uma mudança de conteúdo ou de preferência.
    return _digest({key: value for key, value in record.items() if key != "updated_at"})


def _plan_offer(plan, record):
    original = plan.get("components") or []
    incoming = Counter(component_fingerprint(c) for c in original)
    saved = Counter(c.get("fingerprint") for c in record.get("components", []))
    known_incoming = incoming.copy()
    known_incoming.pop(None, None)
    exact = bool(incoming) and None not in incoming and None not in saved and incoming == saved
    by_signature = {component_fingerprint(c): c for c in original if component_fingerprint(c)
                    and incoming[component_fingerprint(c)] == 1}
    mapping = {c["id"]: by_signature[c["fingerprint"]]["id"] for c in record.get("components", [])
               if c.get("fingerprint") in by_signature and saved[c["fingerprint"]] == 1}
    if not mapping and not (exact and record.get("identity")):
        return None
    restored = copy.deepcopy(original)
    by_id = {c["id"]: c for c in restored}
    source_by_id = {c["id"]: c for c in record.get("components", [])}
    warnings, updates = [], {}
    if any(saved[key] > 1 or incoming[key] > 1 for key in known_incoming if key in saved):
        warnings.append("Há componentes com conteúdo repetido. Os nomes, rótulos e relações ambíguos não serão copiados.")
    if not exact and record.get("identity"):
        warnings.append("A seleção não contém exatamente o mesmo conjunto de componentes; personagem e skin não serão copiados.")
    for source_id, destination_id in mapping.items():
        values = source_by_id[source_id].get("values") or {}
        update = {key: copy.deepcopy(value) for key, value in values.items() if key in {"name", "description"}}
        if "exclusive_group" in values:
            group = str(values["exclusive_group"] or "").strip()
            members = {c["id"] for c in source_by_id.values()
                       if str((c.get("values") or {}).get("exclusive_group") or "").strip().casefold() == group.casefold()}
            if not group or members <= mapping.keys():
                update["exclusive_group"] = group
            else:
                warnings.append(f"O grupo de alternativas de {source_by_id[source_id]['name']} tem componentes ausentes ou ambíguos e será ignorado.")
        if "requires" in values:
            dependencies = values["requires"]
            if isinstance(dependencies, list) and all(d in mapping for d in dependencies):
                update["requires"] = [mapping[d] for d in dependencies]
            else:
                warnings.append(f"As dependências de {source_by_id[source_id]['name']} têm componentes ausentes ou ambíguos e serão ignoradas.")
        updates[destination_id] = update
        by_id[destination_id].update(update)
    try:
        component_rules.validate(restored)
    except ValueError as error:
        warnings.append(f"Relações salvas inválidas não serão copiadas: {error}")
        for cid, update in updates.items():
            for field in ("exclusive_group", "requires"):
                update.pop(field, None)
                before = next(c for c in original if c["id"] == cid)
                if field in before:
                    by_id[cid][field] = copy.deepcopy(before[field])
                else:
                    by_id[cid].pop(field, None)
    try:
        component_rules.assert_valid_state(restored)
    except ValueError:
        # A preferência determinística é a primeira variante que já começaria
        # ativa. As diferenças são mostradas e fazem parte da oferta aceita.
        active = [c["id"] for c in original if c.get("enabled", True)]
        for component in restored:
            component["enabled"] = False
        for cid in reversed(active):
            restored = component_rules.changed_state(restored, cid, True)
    before_by_id = {c["id"]: c for c in original}
    changes, state_changes = [], []
    for component in restored:
        before = before_by_id[component["id"]]
        update = updates.get(component["id"], {})
        fields = [field for field in update if _component_values(before, [field]).get(field) != update[field]]
        if fields:
            changes.append({"component_id": component["id"], "component_name": before.get("name") or "Componente",
                            "fields": fields, "before": _component_values(before, fields),
                            "after": _component_values(component, fields)})
        if bool(before.get("enabled", True)) != bool(component.get("enabled", True)):
            state_changes.append({"component_id": component["id"], "name": component.get("name") or "Componente",
                                  "before": bool(before.get("enabled", True)), "after": bool(component.get("enabled", True))})
    identity = record.get("identity") if exact else None
    if not changes and not identity:
        return None
    if state_changes:
        warnings.append("As relações recuperadas também ajustam os componentes inicialmente ativos, conforme a lista de alterações.")
    return {"source_name": record["source_name"], "matched_components": len(mapping),
            "total_components": len(original), "exact_match": exact, "identity": copy.deepcopy(identity),
            "component_names": {c["id"]: c.get("name") or "Componente" for c in original},
            "changes": changes, "state_changes": state_changes, "warnings": list(dict.fromkeys(warnings)),
            "_components": restored}


def suggest_for_import(plan):
    """Ofertas opacas vinculadas à seleção e ao estado atual das correções."""
    try:
        candidates = _candidates()
    except (OSError, ValueError) as error:
        return {"ok": True, "offers": [], "warnings": [f"Não foi possível consultar as correções pessoais: {error}"]}
    offers, seen = [], set()
    now = time.monotonic()
    with _LOCK:
        for token in list(_OFFERS):
            if _OFFERS[token]["expires"] <= now:
                del _OFFERS[token]
        for source_id, candidate in candidates.items():
            offer = _plan_offer(plan, candidate)
            if not offer:
                continue
            signature = _digest({key: value for key, value in offer.items() if key != "source_name"})
            if signature in seen:
                continue
            seen.add(signature)
            token = secrets.token_urlsafe(24)
            _OFFERS[token] = {"expires": now + _TTL, "plan": _digest(plan), "source_id": source_id,
                              "source": _candidate_signature(candidate), "offer": copy.deepcopy(offer)}
            offers.append({key: value for key, value in offer.items() if not key.startswith("_")} | {"id": token})
    return {"ok": True, "offers": offers,
            "note": "Opcional: recuperar escolhas salvas para conteúdo idêntico. A identificação por tipos continua sendo feita pelos arquivos."}


def apply_import_choice(plan, meta):
    """Retorna cópias validadas do plano e metadados; não escreve nem move nada."""
    token = meta.get("personal_correction_choice")
    if not token:
        return plan, meta
    with _LOCK:
        pending = _OFFERS.pop(str(token), None)
    if not pending or pending["expires"] <= time.monotonic():
        raise ValueError("A oferta de correções expirou. Selecione os arquivos novamente para revisá-la.")
    if pending["plan"] != _digest(plan):
        raise ValueError("A seleção da importação mudou após a oferta de correções. Revise os arquivos novamente.")
    candidate = _candidates().get(pending["source_id"])
    if not candidate or _candidate_signature(candidate) != pending["source"]:
        raise ValueError("As correções salvas mudaram após a oferta. Selecione os arquivos novamente para revisá-las.")
    offer = _plan_offer(plan, candidate)
    if offer != pending["offer"]:
        raise ValueError("O plano de recuperação das correções mudou. Revise a importação novamente.")
    identity = offer.get("identity")
    if identity and (str(meta.get("character") or "Generic") != identity["character"]
                     or str(meta.get("skin") or "") != identity["skin"]):
        raise ValueError("A identidade foi editada depois da oferta. Desmarque as correções salvas ou selecione a oferta novamente.")
    corrected_plan = copy.deepcopy(plan)
    corrected_plan["components"] = copy.deepcopy(offer["_components"])
    corrected_meta = dict(meta)
    if identity:
        corrected_meta.update(identity)
    selected = corrected_meta.get("enabled_component_ids")
    if selected is not None:
        if not isinstance(selected, list) or not all(isinstance(cid, str) for cid in selected):
            raise ValueError("A seleção de componentes ativos da importação é inválida.")
        if set(selected) != {c["id"] for c in corrected_plan["components"] if c.get("enabled", True)}:
            raise ValueError("A seleção de componentes ativos mudou após a oferta de correções. Revise a importação.")
    component_rules.assert_valid_state(corrected_plan["components"])
    return corrected_plan, corrected_meta
