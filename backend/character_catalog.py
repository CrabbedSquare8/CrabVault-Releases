"""Catálogo atualizável de IDs de personagens e skins.

A aplicação sempre inclui ``character_data.json`` como fallback offline. Uma
cópia mais recente pode ser obtida do mesmo repositório público usado pelo
Repak X e fica em ``.cache/character_catalog``; imagens continuam pertencendo
ao catálogo Rivalskins já usado pelo Manager.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
import threading
from pathlib import Path
from urllib.request import Request, urlopen

from . import storage


SOURCE_REPOSITORY = "https://github.com/donutman07/MarvelRivalsCharacterIDs"
SOURCE_URL = (
    "https://raw.githubusercontent.com/donutman07/MarvelRivalsCharacterIDs/"
    "main/MarvelRivalsCharacterIDs.md"
)
CHECK_INTERVAL = timedelta(days=1)
USER_AGENT = "CrabVault/0.39 (character catalog updater)"
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024
_UPDATE_LOCK = threading.RLock()

_CHARACTER_ALIASES = {
    "the punisher": "Punisher",
    "the thing": "Thing",
    "mr. fantastic": "Mister Fantastic",
    "mr fantastic": "Mister Fantastic",
    "mister fantastic": "Mister Fantastic",
    "jeff the land shark": "Jeff the Land Shark",
    "jeff the landshark": "Jeff the Land Shark",
    "cloak & dagger": "Cloak & Dagger",
    "cloak and dagger": "Cloak & Dagger",
    "spider-man": "Spider-Man",
    "spider man": "Spider-Man",
    "spiderman": "Spider-Man",
    "star-lord": "Star-Lord",
    "star lord": "Star-Lord",
    "white fox": "White Fox",
    "iron fist (lin lie)": "Iron Fist",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_markdown(value: str) -> str:
    value = re.sub(r"[*_`]+", "", str(value or ""))
    return re.sub(r"\s+", " ", value).strip()


def _character_name(value: str) -> str:
    cleaned = _clean_markdown(value)
    alias = _CHARACTER_ALIASES.get(cleaned.casefold())
    if alias:
        return alias
    return cleaned.title() if cleaned and cleaned.upper() == cleaned else cleaned


def _skin_name(value: str) -> str:
    cleaned = _clean_markdown(value)
    return cleaned.title() if cleaned and cleaned.upper() == cleaned else cleaned


def validate_entries(entries) -> list[dict]:
    """Valida e normaliza o formato persistido usado por ``characters.py``."""
    if not isinstance(entries, list):
        raise ValueError("O catálogo de personagens precisa ser uma lista.")
    result = []
    owners = {}
    for position, raw in enumerate(entries, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"Entrada {position} do catálogo é inválida.")
        character = _character_name(raw.get("name", ""))
        character_id = str(raw.get("id", "")).strip()
        skin_id = str(raw.get("skinid", "")).strip()
        skin_name = _skin_name(raw.get("skin_name", ""))
        if not re.fullmatch(r"\d{4}", character_id):
            raise ValueError(f"ID de personagem inválido na entrada {position}: {character_id!r}.")
        if not re.fullmatch(r"\d{7}", skin_id) or not skin_id.startswith(character_id):
            raise ValueError(f"ID de skin inválido na entrada {position}: {skin_id!r}.")
        if not character or not skin_name:
            raise ValueError(f"Nome vazio na entrada {position} do catálogo.")
        previous_owner = owners.get(skin_id)
        if previous_owner and previous_owner != character_id:
            raise ValueError(f"A skin {skin_id} aparece em dois personagens diferentes.")
        owners[skin_id] = character_id
        result.append({"name": character, "id": character_id,
                       "skinid": skin_id, "skin_name": skin_name})
    return result


def parse_markdown(content: str) -> list[dict]:
    """Converte a tabela Markdown, incluindo linhas que repetem o herói anterior."""
    current_id = ""
    current_name = ""
    parsed = []
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or ":--:" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        character_id, character_name, skin_id, skin_name = cells[:4]
        if re.fullmatch(r"\d{4}", character_id):
            current_id = character_id
        if _clean_markdown(character_name).casefold() not in {"", "name"}:
            current_name = character_name
        if not re.fullmatch(r"\d{7}", skin_id) or not _clean_markdown(skin_name):
            continue
        candidate = {"name": current_name, "id": current_id,
                     "skinid": skin_id, "skin_name": skin_name}
        try:
            parsed.extend(validate_entries([candidate]))
        except ValueError:
            # A fonte ocasionalmente contém um typo de ID. Uma linha ruim não
            # invalida as centenas de relações corretas, mas nunca é persistida.
            continue
    if not parsed:
        raise ValueError("Nenhum ID de personagem ou skin foi encontrado na fonte.")
    # O comportamento da fonte é por ID: a ocorrência mais recente corrige
    # uma anterior, desde que continue pertencendo ao mesmo personagem.
    by_id = {}
    for entry in parsed:
        previous = by_id.get(entry["skinid"])
        if previous and previous["id"] != entry["id"]:
            raise ValueError(f"A skin {entry['skinid']} mudou de personagem na fonte.")
        by_id[entry["skinid"]] = entry
    return sorted(by_id.values(), key=lambda item: (int(item["id"]), int(item["skinid"]), item["skin_name"]))


def _read_json(path: Path) -> list[dict]:
    return validate_entries(json.loads(path.read_text(encoding="utf-8")))


def load_character_data(bundled_path) -> list[dict]:
    """Carrega cache validado; falha ou ausência sempre volta ao bundle."""
    try:
        cached = storage.load_character_catalog_cache()
        if cached is not None:
            return validate_entries(cached)
    except (OSError, ValueError, TypeError):
        pass
    return _read_json(Path(bundled_path))


def _fetch() -> str:
    request = Request(SOURCE_URL, headers={"User-Agent": USER_AGENT, "Accept": "text/markdown,text/plain"})
    with urlopen(request, timeout=30) as response:
        length = int(response.headers.get("Content-Length") or 0)
        if length > MAX_DOWNLOAD_BYTES:
            raise ValueError("A resposta do catálogo excede o limite esperado.")
        payload = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(payload) > MAX_DOWNLOAD_BYTES:
        raise ValueError("A resposta do catálogo excede o limite esperado.")
    return payload.decode("utf-8", errors="strict")


def _merge(existing: list[dict], remote: list[dict]) -> tuple[list[dict], int, int]:
    merged = {entry["skinid"]: dict(entry) for entry in validate_entries(existing)}
    added = updated = 0
    for entry in validate_entries(remote):
        previous = merged.get(entry["skinid"])
        if previous is None:
            added += 1
        elif previous != entry:
            updated += 1
        merged[entry["skinid"]] = dict(entry)
    values = sorted(merged.values(), key=lambda item: (int(item["id"]), int(item["skinid"]), item["skin_name"]))
    return values, added, updated


def get_status(bundled_path) -> dict:
    metadata = storage.load_character_catalog_status()
    using_cache = False
    try:
        cached = storage.load_character_catalog_cache()
        using_cache = cached is not None and bool(validate_entries(cached))
        total = len(validate_entries(cached)) if using_cache else len(_read_json(Path(bundled_path)))
    except (OSError, ValueError, TypeError):
        try:
            total = len(_read_json(Path(bundled_path)))
        except (OSError, ValueError, TypeError):
            total = 0
    return {"source_repository": SOURCE_REPOSITORY, "source_url": SOURCE_URL,
            **metadata, "total": total, "using_cache": using_cache}


def _update_from_github(bundled_path, *, fetcher=None) -> dict:
    """Baixa, valida e publica atomicamente o catálogo; nunca apaga o anterior."""
    checked_at = _now_iso()
    current = load_character_data(bundled_path)
    try:
        remote = parse_markdown((fetcher or _fetch)())
        # Um truncamento válido sintaticamente não pode substituir a base real.
        minimum = min(100, max(1, len(current) // 3))
        if len(remote) < minimum:
            raise ValueError(f"A fonte retornou somente {len(remote)} entradas; esperado pelo menos {minimum}.")
        merged, added, updated = _merge(current, remote)
        changed = merged != current
        if changed or storage.load_character_catalog_cache() is None:
            storage.save_character_catalog_cache(merged)
        status = {"checked_at": checked_at, "updated_at": checked_at,
                  "total": len(merged), "remote_total": len(remote),
                  "remote_character_ids": sorted({entry["id"] for entry in remote}, key=int),
                  "added": added, "updated": updated, "changed": changed,
                  "ok": True, "error": ""}
        storage.save_character_catalog_status(status)
        return {**status, "source_repository": SOURCE_REPOSITORY, "source_url": SOURCE_URL}
    except Exception as error:
        previous = storage.load_character_catalog_status()
        status = {**previous, "checked_at": checked_at, "ok": False,
                  "changed": False, "error": str(error), "total": len(current)}
        storage.save_character_catalog_status(status)
        return {**status, "source_repository": SOURCE_REPOSITORY, "source_url": SOURCE_URL}


def update_from_github(bundled_path, *, fetcher=None) -> dict:
    with _UPDATE_LOCK:
        return _update_from_github(bundled_path, fetcher=fetcher)


def check_for_update(bundled_path, *, force=False, fetcher=None) -> dict:
    with _UPDATE_LOCK:
        status = storage.load_character_catalog_status()
        last = status.get("checked_at")
        if not force and last:
            try:
                checked = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - checked.astimezone(timezone.utc) < CHECK_INTERVAL:
                    return {**get_status(bundled_path), "checked": False, "changed": False}
            except (ValueError, TypeError):
                pass
        result = update_from_github(bundled_path, fetcher=fetcher)
        result["checked"] = True
        return result
