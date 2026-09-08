"""Atualiza o catálogo local de skins a partir do Rivalskins.

Uso:
    python -m backend.update_rivalskins_catalog

A fonte é filtrada por ``type=costume``. Assim MVPs, sprays, emotes e outros
itens do site nunca entram no catálogo usado para identificar mods.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ROOT_URL = "https://rivalskins.com/?type=costume"
SITE_ROOT = "https://rivalskins.com"
GENERATED_CATALOG_URL = "https://rivalskins.com/wp-content/themes/astra-child/js/generated/item-data.js"
DATA_PATH = Path(__file__).with_name("rivalskins_data.json")
USER_AGENT = "CrabVault/1.0 (local skin catalog updater)"
# Heróis novos que ainda não existiam no scrape inicial. O índice 47 é o
# identificador compacto usado pelo catálogo do site, não o ID do jogo.
SITE_HERO_SLUG_OVERRIDES = {"47": "elsa-bloodstone"}


def fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def costume_urls(index_html: str) -> list[str]:
    """Retorna os cards de Costume na ordem apresentada pelo site (mais novos primeiro)."""
    urls: list[str] = []
    seen: set[str] = set()
    for href in re.findall(r'''href=["']([^"']*/item/\d+/[^"']+-costume-[^"']+)["']''', index_html, re.I):
        url = urljoin(SITE_ROOT, unescape(href))
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def generated_costumes(script: str) -> list[dict]:
    """Decodifica o catálogo público que a página já carrega no navegador.

    ``rows`` usa um formato compacto. A posição 5 é o tipo; ``0`` representa
    Costume. A posição 1 é justamente o ID usado nos arquivos do jogo.
    """
    match = re.search(r"var D=(\{.*?\});var p=", script, re.S)
    if not match:
        raise RuntimeError("O formato do catálogo gerado pelo Rivalskins mudou.")
    data = json.loads(match.group(1))
    types = data["t"]
    asset_prefix = urljoin(SITE_ROOT, data.get("p", "/wp-content/uploads/marvel-assets/"))
    records: list[dict] = []
    for row in data["rows"]:
        if types[row[5]] != "costume":
            continue
        records.append(
            {
                "site_id": str(row[0]),
                "skin_id": str(row[1]).lower(),
                "name": str(row[2]),
                "slug": str(row[3]) if row[3] else "",
                "hero_id": str(row[6]) if row[6] else None,
                # A miniatura usada nos cards de Costume do próprio site.
                "icon_url": urljoin(asset_prefix, str(row[11])) if len(row) > 11 and row[11] else "",
            }
        )
    return records


def display_skin_name(value: str) -> str:
    """Normaliza o rótulo de exibição sem alterar o ID oficial do site."""
    value = re.sub(r"\s+", " ", str(value or "").strip())
    if re.search(r"(?:^|\s)default$", value, re.I):
        return "Default"
    return value.title() if value and value.upper() == value else value


def slug_value(url: str, marker: str, suffix: str = "") -> str | None:
    match = re.search(marker + r"([a-z0-9_-]+)" + suffix, url, re.I)
    return match.group(1).replace("_", "-") if match else None


def page_record(url: str) -> tuple[str, dict] | None:
    """Lê ID, personagem e nome na página individual de uma skin Costume."""
    html = fetch(url)
    # A página exibe "ID: 1030503" próximo ao bloco de informações.
    match = re.search(
        r'<tr[^>]*class=["\']item-details-marvel-id["\'][^>]*>[\s\S]*?'
        r'<td[^>]*>\s*([a-z]{0,2}\d{7})\b',
        html,
        re.I,
    )
    if not match:
        return None
    skin_id = match.group(1).lower()

    character = slug_value(url, r"/item/\d+/", r"-costume-")
    name = None
    # O título principal costuma ser o primeiro H1. Fallback para og:title.
    heading = re.search(r"<h1[^>]*>\s*(.*?)\s*</h1>", html, re.I | re.S)
    if heading:
        name = re.sub(r"<[^>]+>", "", heading.group(1)).strip()
    if not name:
        og_title = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', html, re.I)
        if og_title:
            name = og_title.group(1).split("|")[0].strip()
    if not name:
        # O slug é melhor que descartar uma skin cujo HTML tenha mudado.
        name = slug_value(url, r"-costume-")
        name = name.replace("-", " ").title() if name else None
    if not character or not name:
        return None
    # A página individual sempre aponta para o mesmo ícone pequeno usado no
    # catálogo. Este fallback cobre itens recentes ainda ausentes do arquivo
    # JS gerado pelo site.
    icon_url = ""
    views_match = re.search(r'''data-views=["']([^"']+)["']''', html, re.I)
    if views_match:
        try:
            views = json.loads(unescape(views_match.group(1)))
            icon_url = urljoin(SITE_ROOT, views.get("icon", {}).get("url", ""))
        except (ValueError, TypeError):
            pass
    if not icon_url:
        icon_match = re.search(r'''(?:https?:)?[^"'\\ ]*img_icon_[^"'\\ ]+?\.png''', html, re.I)
        icon_url = urljoin(SITE_ROOT, unescape(icon_match.group(0))) if icon_match else ""
    if not icon_url:
        # Uma skin legada não possui miniatura própria; a imagem social da
        # página ainda é uma representação correta e funciona em 26px.
        og_image = re.search(
            r'''<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)''',
            html,
            re.I,
        )
        if og_image:
            icon_url = urljoin(SITE_ROOT, unescape(og_image.group(1)))
    return skin_id, {
        "name": display_skin_name(unescape(name)), "character": character, "url": url,
        "icon_url": icon_url,
    }


def update_catalog(limit: int | None = None, workers: int = 8) -> dict:
    index = fetch(ROOT_URL)
    urls = costume_urls(index)
    if not urls:
        raise RuntimeError("Não encontrei cards de Costume na página do Rivalskins.")

    existing = json.loads(DATA_PATH.read_text(encoding="utf-8")) if DATA_PATH.exists() else {}
    generated = generated_costumes(fetch(GENERATED_CATALOG_URL))

    # Descobre a relação entre o índice compacto de herói do site e o slug já
    # usado pelo projeto. Como o catálogo local contém centenas de skins
    # antigas, esta inferência cobre todos os heróis atuais sem 684 requests.
    generated_by_skin = {item["skin_id"]: item for item in generated}
    character_votes: dict[str, dict[str, int]] = {}
    for skin_id, record in existing.items():
        hero_id = generated_by_skin.get(skin_id, {}).get("hero_id")
        character = record.get("character")
        if hero_id and character:
            votes = character_votes.setdefault(hero_id, {})
            votes[character] = votes.get(character, 0) + 1
    character_by_hero = {
        hero_id: max(votes, key=votes.get) for hero_id, votes in character_votes.items()
    }
    character_by_hero.update(SITE_HERO_SLUG_OVERRIDES)

    # A listagem vem na ordem mais recente. Só estas N páginas individuais
    # são consultadas: é uma validação extra de personagem/ID para lançamentos
    # novos, sem transformar cada atualização em centenas de acessos.
    selected = urls[:limit] if limit else urls[:15]
    collected: dict[str, dict] = {}
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        jobs = {pool.submit(page_record, url): url for url in selected}
        for job in as_completed(jobs):
            url = jobs[job]
            try:
                result = job.result()
            except Exception:
                failed.append(url)
                continue
            if result is None:
                failed.append(url)
                continue
            skin_id, record = result
            collected[skin_id] = record

    generated_changed = 0
    missing_character_heroes: set[str] = set()
    for item in generated:
        skin_id = item["skin_id"]
        current = existing.get(skin_id, {})
        character = current.get("character") or character_by_hero.get(item["hero_id"] or "")
        if not character:
            if item["hero_id"]:
                missing_character_heroes.add(item["hero_id"])
            # Sem personagem não é seguro criar uma URL falsa. A skin ainda
            # fica disponível para a validação das páginas mais recentes.
            continue
        generated_record = {
            "name": display_skin_name(item["name"]),
            "character": character,
            "url": current.get("url") or f"{SITE_ROOT}/item/{item['site_id']}/{character}-costume-{item['slug']}/",
            "icon_url": item.get("icon_url", ""),
        }
        if existing.get(skin_id) != generated_record:
            existing[skin_id] = generated_record
            generated_changed += 1

    # Alguns itens (normalmente os recém-publicados) ainda não estão no
    # arquivo compactado do catálogo com a URL do ícone. São poucos; buscar
    # apenas estes evita um scan lento de todas as páginas.
    missing_icon_urls = [
        record.get("url") for record in existing.values()
        if record.get("url") and (
            not record.get("icon_url")
            or str(record.get("icon_url")).startswith(f"{SITE_ROOT}/img_icon_")
        )
    ]
    icon_records: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        jobs = {pool.submit(page_record, url): url for url in missing_icon_urls}
        for job in as_completed(jobs):
            try:
                result = job.result()
            except Exception:
                continue
            if result and result[1].get("icon_url"):
                icon_records[result[0]] = result[1]["icon_url"]

    for skin_id, icon_url in icon_records.items():
        if skin_id in existing and existing[skin_id].get("icon_url") != icon_url:
            existing[skin_id]["icon_url"] = icon_url
            generated_changed += 1

    changed = 0
    for skin_id, record in collected.items():
        if existing.get(skin_id) != record:
            existing[skin_id] = record
            changed += 1
    DATA_PATH.write_text(json.dumps(dict(sorted(existing.items(), key=lambda pair: pair[0])), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "listed_costumes": len(generated),
        "checked": len(selected),
        "collected": len(collected),
        "changed": generated_changed + changed,
        "failed": failed,
        "hero_ids_without_character_mapping": sorted(missing_character_heroes),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latest", type=int, default=None, help="Consulta apenas as N skins mais recentes.")
    parser.add_argument("--workers", type=int, default=8, help="Consultas simultâneas (padrão: 8).")
    args = parser.parse_args()
    result = update_catalog(limit=args.latest, workers=args.workers)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["failed"] else 2


if __name__ == "__main__":
    sys.exit(main())
