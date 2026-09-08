"""Catálogo local de skins obtido pelo scrape do Rivalskins.

Fonte primária: https://rivalskins.com/heroes/
Dados: ``backend/rivalskins_data.json`` (fornecido pelo usuário em 2026-08-11).
Cada item contém nome, personagem, URL da página e o ID exibido pelo site.
Nenhuma consulta à internet é necessária quando o CrabVault está aberto.
"""
import json
import os


_DATA_PATH = os.path.join(os.path.dirname(__file__), "rivalskins_data.json")
with open(_DATA_PATH, "r", encoding="utf-8") as _catalog_file:
    RIVALSKINS_ITEMS = json.load(_catalog_file)

# IDs numéricos são os usados nos caminhos internos do jogo.
RIVALSKINS_SKIN_NAMES = {
    skin_id: item["name"]
    for skin_id, item in RIVALSKINS_ITEMS.items()
    if not skin_id.startswith("ps")
}

# Miniaturas oficiais exibidas nos cards de Costume do Rivalskins. São URLs
# leves e só são carregadas pelo navegador quando o usuário abre as skins de
# um personagem na barra lateral.
RIVALSKINS_SKIN_ICONS = {
    skin_id: item.get("icon_url", "")
    for skin_id, item in RIVALSKINS_ITEMS.items()
    if not skin_id.startswith("ps") and item.get("icon_url")
}

# ``ps`` identifica uma recoloração no Rivalskins. A página de origem não
# traz o ID da skin-pai; por isso a associação abaixo é uma inferência local:
# a skin-base numérica imediatamente anterior do mesmo personagem. O nome e
# a URL originais continuam preservados para revisão futura, sem afetar a
# identificação de mods (que usa somente IDs numéricos do jogo).
RIVALSKINS_RECOLORS = {}
for _recolor_id, _item in RIVALSKINS_ITEMS.items():
    if not _recolor_id.startswith("ps"):
        continue
    _numeric_id = int(_recolor_id[2:])
    _candidates = [
        skin_id for skin_id, base in RIVALSKINS_ITEMS.items()
        if not skin_id.startswith("ps")
        and base.get("character") == _item.get("character")
        and int(skin_id) < _numeric_id
    ]
    _parent_id = max(_candidates, key=int) if _candidates else None
    RIVALSKINS_RECOLORS[_recolor_id] = {
        **_item,
        "recolor_of": _parent_id,
        "recolor_of_name": RIVALSKINS_ITEMS.get(_parent_id, {}).get("name") if _parent_id else None,
    }
