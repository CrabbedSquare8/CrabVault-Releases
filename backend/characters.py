"""Identidade de personagens e skins usada em toda a aplicação.

O JSON incluído garante funcionamento offline. ``character_catalog`` pode
carregar uma cópia mais recente obtida do GitHub, enquanto o Rivalskins segue
responsável pelos complementos e pelas imagens que o Manager já possui.
"""
import os
import re

from . import character_catalog
from .skin_catalog import RIVALSKINS_ITEMS, RIVALSKINS_RECOLORS, RIVALSKINS_SKIN_NAMES, RIVALSKINS_SKIN_ICONS


_BASE_MARVEL_CHARACTERS = (
    "Adam Warlock", "Angela", "Black Cat", "Black Panther", "Black Widow",
    "Blade", "Captain America", "Cloak & Dagger", "Cyclops", "Daredevil",
    "Deadpool", "Devil Dinosaur", "Doctor Strange", "Elsa Bloodstone",
    "Emma Frost", "Gambit", "Groot", "Hawkeye", "Hela", "Hulk",
    "Human Torch", "Invisible Woman", "Iron Fist", "Iron Man",
    "Jeff the Land Shark", "Jubilee", "Loki", "Luna Snow", "Magik",
    "Magneto", "Mantis", "Mister Fantastic", "Moon Knight", "Namor",
    "Peni Parker", "Phoenix", "Psylocke", "Rocket Raccoon", "Rogue",
    "Scarlet Witch", "Spider-Man", "Squirrel Girl", "Star-Lord", "Storm",
    "The Hood", "Punisher", "Thing", "Thor", "Ultron", "Venom",
    "White Fox", "Winter Soldier", "Wolverine",
)

_DATA_PATH = os.path.join(os.path.dirname(__file__), "character_data.json")

# Estes objetos permanecem os mesmos durante toda a sessão. Outros módulos
# importam suas referências, portanto uma atualização troca o conteúdo in
# place e passa a valer imediatamente sem reiniciar nem reanalisar mods.
CHARACTER_DATA = []
MARVEL_CHARACTERS = []
CHARACTER_BY_ID = {}
SKIN_BY_ID = {}
SKIN_ICON_BY_ID = {}
_ROSTER_BY_SLUG = {}

_DISPLAY_ALIASES = {
    "The Punisher": "Punisher", "The Thing": "Thing", "White Fox**": "White Fox",
    "Mr. Fantastic": "Mister Fantastic", "Iron Fist (Lin Lie)": "Iron Fist",
}
_SKIN_NAME_ALIASES = {
    "new millenia might": "New Millennia Might",
    "ven#m": "Ven#M",
}


def canonical_skin_name(name: str, character: str | None = None) -> str:
    """Converte um rótulo bruto em um único nome exibível."""
    value = re.sub(r"\s+", " ", str(name or "").strip())
    if not value:
        return ""
    alias = _SKIN_NAME_ALIASES.get(value.casefold())
    if alias:
        return alias
    if re.search(r"(?:^|\s)default$", value, re.IGNORECASE):
        return "Default"
    if character:
        comparable = lambda text: re.sub(r"[^a-z0-9]", "", text.casefold())
        if comparable(value) == comparable(character):
            return "Default"
    if value.upper() == value:
        value = value.title()
    return re.sub(r"\b(Of|The|And|Or|For|In|On|At|To)\b",
                  lambda match: match.group(1).lower(), value)


def _slug(character: str) -> str:
    return character.lower().replace(" ", "-").replace("&", "and")


def _build_catalog(entries) -> tuple[list, dict, dict, dict, dict]:
    roster = set(_BASE_MARVEL_CHARACTERS)
    remote_character_ids = {
        str(value) for value in character_catalog.get_status(_DATA_PATH).get("remote_character_ids", [])
        if str(value).isdigit()
    }
    normalized_entries = []
    for raw in entries:
        entry = dict(raw)
        entry["name"] = _DISPLAY_ALIASES.get(entry["name"], entry["name"])
        if entry["id"] in remote_character_ids:
            roster.add(entry["name"])
        normalized_entries.append(entry)

    roster_by_slug = {_slug(entry): entry for entry in roster}
    roster_by_slug.update({"cloak-and-dagger": "Cloak & Dagger", "spider-man": "Spider-Man",
                           "the-punisher": "Punisher", "the-thing": "Thing", "the-hood": "The Hood"})

    character_by_id = {}
    skin_by_id = {}
    skin_icon_by_id = {}
    for entry in normalized_entries:
        character = entry["name"]
        if character not in roster:
            continue
        character_by_id[entry["id"]] = character
        skin_by_id.setdefault(entry["skinid"],
                              (character, canonical_skin_name(entry["skin_name"], character)))

    character_by_id.setdefault("1059", "Elsa Bloodstone")

    for skin_id, skin_name in RIVALSKINS_SKIN_NAMES.items():
        item = RIVALSKINS_ITEMS[skin_id]
        character = character_by_id.get(skin_id[:4]) or roster_by_slug.get(item.get("character", ""))
        if character:
            character_by_id.setdefault(skin_id[:4], character)
            existing = skin_by_id.get(skin_id)
            if not existing or "placeholder" in existing[1].casefold():
                skin_by_id[skin_id] = (character, canonical_skin_name(skin_name, character))
            if RIVALSKINS_SKIN_ICONS.get(skin_id):
                skin_icon_by_id[skin_id] = RIVALSKINS_SKIN_ICONS[skin_id]

    for recolor_id, recolor in RIVALSKINS_RECOLORS.items():
        skin_id = recolor_id[2:]
        character = character_by_id.get(skin_id[:4]) or roster_by_slug.get(recolor.get("character", ""))
        if character:
            character_by_id.setdefault(skin_id[:4], character)
            parent = canonical_skin_name(recolor.get("recolor_of_name", ""), character)
            base_name = canonical_skin_name(recolor["name"], character)
            name = base_name + (f" (Recolor of {parent})" if parent else " (Recolor)")
            skin_by_id.setdefault(skin_id, (character, name))
            if recolor.get("icon_url"):
                skin_icon_by_id[skin_id] = recolor["icon_url"]

    return sorted(roster), character_by_id, skin_by_id, skin_icon_by_id, roster_by_slug


def refresh_character_data() -> int:
    """Recarrega o cache atualizado e publica os índices na sessão atual."""
    entries = character_catalog.load_character_data(_DATA_PATH)
    roster, characters, skins, icons, slugs = _build_catalog(entries)
    CHARACTER_DATA[:] = entries
    MARVEL_CHARACTERS[:] = roster
    CHARACTER_BY_ID.clear(); CHARACTER_BY_ID.update(characters)
    SKIN_BY_ID.clear(); SKIN_BY_ID.update(skins)
    SKIN_ICON_BY_ID.clear(); SKIN_ICON_BY_ID.update(icons)
    _ROSTER_BY_SLUG.clear(); _ROSTER_BY_SLUG.update(slugs)
    return len(CHARACTER_DATA)


refresh_character_data()
