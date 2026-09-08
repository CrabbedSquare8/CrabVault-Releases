import json
import pathlib
import tempfile
import unittest
from collections import defaultdict
from urllib.parse import urlsplit
from unittest.mock import patch

from backend import character_catalog, characters, skin_catalog, update_rivalskins_catalog


class CatalogIntegrityTests(unittest.TestCase):
    def test_remote_character_id_extends_roster_without_admitting_internal_bundle_names(self):
        entry = {"name": "Future Hero", "id": "1099", "skinid": "1099001", "skin_name": "Default"}
        with patch.object(character_catalog, "get_status", return_value={"remote_character_ids": ["1099"]}):
            roster, character_ids, skins, _, _ = characters._build_catalog([entry])
        self.assertIn("Future Hero", roster)
        self.assertEqual(character_ids["1099"], "Future Hero")
        self.assertEqual(skins["1099001"], ("Future Hero", "Default"))

    def test_local_catalog_has_valid_ids_and_complete_source_fields(self):
        self.assertTrue(skin_catalog.RIVALSKINS_ITEMS)
        for skin_id, item in skin_catalog.RIVALSKINS_ITEMS.items():
            with self.subTest(skin_id=skin_id):
                self.assertRegex(skin_id, r"^(?:ps)?\d{7}$")
                self.assertIsInstance(item, dict)
                for field in ("name", "character", "url", "icon_url"):
                    self.assertIsInstance(item.get(field), str)
                    self.assertTrue(item[field].strip())
                self.assertEqual(urlsplit(item["url"]).scheme, "https")
                self.assertEqual(urlsplit(item["url"]).hostname, "rivalskins.com")
                self.assertEqual(urlsplit(item["icon_url"]).scheme, "https")
                self.assertEqual(urlsplit(item["icon_url"]).hostname, "rivalskins.com")

    def test_every_numeric_costume_resolves_to_the_same_playable_character(self):
        for skin_id, item in skin_catalog.RIVALSKINS_ITEMS.items():
            if skin_id.startswith("ps"):
                continue
            with self.subTest(skin_id=skin_id):
                expected_character = characters._ROSTER_BY_SLUG.get(item["character"])
                self.assertIsNotNone(expected_character)
                self.assertIn(skin_id, characters.SKIN_BY_ID)
                self.assertEqual(characters.SKIN_BY_ID[skin_id][0], expected_character)
                self.assertIn(skin_id, characters.SKIN_ICON_BY_ID)

    def test_recolor_ids_are_unambiguous_and_resolve_without_overwriting_costumes(self):
        numeric_ids = {skin_id for skin_id in skin_catalog.RIVALSKINS_ITEMS if not skin_id.startswith("ps")}
        recolor_ids = {skin_id[2:] for skin_id in skin_catalog.RIVALSKINS_ITEMS if skin_id.startswith("ps")}
        self.assertTrue(recolor_ids)
        self.assertTrue(numeric_ids.isdisjoint(recolor_ids))
        self.assertEqual(len(recolor_ids), len(skin_catalog.RIVALSKINS_RECOLORS))
        for skin_id in recolor_ids:
            with self.subTest(skin_id=skin_id):
                self.assertIn(skin_id, characters.SKIN_BY_ID)
                self.assertIn(skin_id, characters.SKIN_ICON_BY_ID)

    def test_character_dump_duplicates_never_cross_character_boundaries(self):
        grouped = defaultdict(list)
        for entry in characters.CHARACTER_DATA:
            grouped[entry["skinid"]].append(entry)
            self.assertRegex(entry["id"], r"^\d{4}$")
            self.assertRegex(entry["skinid"], r"^\d{7}$")
        for skin_id, entries in grouped.items():
            with self.subTest(skin_id=skin_id):
                canonical_characters = {
                    characters._DISPLAY_ALIASES.get(entry["name"], entry["name"])
                    for entry in entries
                }
                self.assertEqual(len(canonical_characters), 1)

    def test_resolved_characters_stay_inside_the_public_roster(self):
        self.assertEqual(characters.MARVEL_CHARACTERS, sorted(set(characters.MARVEL_CHARACTERS)))
        roster = set(characters.MARVEL_CHARACTERS)
        self.assertTrue(set(characters.CHARACTER_BY_ID.values()) <= roster)
        self.assertTrue({character for character, _ in characters.SKIN_BY_ID.values()} <= roster)


class CatalogParserTests(unittest.TestCase):
    def test_daily_check_does_not_open_network_twice(self):
        recent = {"checked_at": character_catalog._now_iso(), "ok": True, "total": 12}
        with (patch.object(character_catalog.storage, "load_character_catalog_status", return_value=recent),
              patch.object(character_catalog, "get_status", return_value=recent),
              patch.object(character_catalog, "update_from_github") as update):
            result = character_catalog.check_for_update("unused.json")
        self.assertFalse(result["checked"])
        self.assertFalse(result["changed"])
        update.assert_not_called()

    def test_github_character_parser_handles_continuation_rows_and_aliases(self):
        markdown = """# Marvel Rivals Character IDs
| ID | NAME | SKIN IDs | SKIN NAMES |
| :--: | :--: | :--: | :--: |
| 1040 | Mr. Fantastic | 1040100 | FIRST FAMILY |
| | | 1040300 | The Life Fantastic |
| 1060 | White Fox** | 1060100 | Default |
| 1060 | White Fox | 9999999 | Invalid owner |
"""
        self.assertEqual(character_catalog.parse_markdown(markdown), [
            {"name": "Mister Fantastic", "id": "1040", "skinid": "1040100", "skin_name": "First Family"},
            {"name": "Mister Fantastic", "id": "1040", "skinid": "1040300", "skin_name": "The Life Fantastic"},
            {"name": "White Fox", "id": "1060", "skinid": "1060100", "skin_name": "Default"},
        ])

    def test_iron_fist_lin_lie_alias_stays_in_one_character(self):
        entries = character_catalog.validate_entries([
            {"name": "Iron Fist", "id": "1052", "skinid": "1052001", "skin_name": "Default"},
            {"name": "Iron Fist (Lin Lie)", "id": "1052", "skinid": "1052100",
             "skin_name": "Martial Arts Savant"},
        ])
        self.assertEqual({entry["name"] for entry in entries}, {"Iron Fist"})
        with patch.object(character_catalog, "get_status", return_value={"remote_character_ids": ["1052"]}):
            roster, character_ids, skins, _, _ = characters._build_catalog(entries)
        self.assertEqual(roster.count("Iron Fist"), 1)
        self.assertEqual(character_ids["1052"], "Iron Fist")
        self.assertEqual(skins["1052100"], ("Iron Fist", "Martial Arts Savant"))

    def test_github_update_merges_without_dropping_bundled_entries(self):
        existing = [
            {"name": "Hulk", "id": "1011", "skinid": "1011001", "skin_name": "Default"},
            {"name": "Hulk", "id": "1011", "skinid": "1011100", "skin_name": "Old Name"},
            {"name": "Loki", "id": "1016", "skinid": "1016001", "skin_name": "Default"},
        ]
        markdown = """| ID | NAME | SKIN IDs | SKIN NAMES |
| :--: | :--: | :--: | :--: |
| 1011 | Hulk | 1011100 | Mighty G-Bomb |
| | | 1011500 | Punk Rage |
"""
        saved = {}
        with tempfile.TemporaryDirectory() as directory:
            bundled = pathlib.Path(directory) / "character_data.json"
            bundled.write_text(json.dumps(existing), encoding="utf-8")
            with (patch.object(character_catalog.storage, "load_character_catalog_cache", return_value=None),
                  patch.object(character_catalog.storage, "save_character_catalog_cache",
                               side_effect=lambda value: saved.update(data=value)),
                  patch.object(character_catalog.storage, "load_character_catalog_status", return_value={}),
                  patch.object(character_catalog.storage, "save_character_catalog_status",
                               side_effect=lambda value: saved.update(status=value))):
                result = character_catalog.update_from_github(bundled, fetcher=lambda: markdown)
        self.assertTrue(result["ok"])
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["updated"], 1)
        by_id = {entry["skinid"]: entry for entry in saved["data"]}
        self.assertEqual(by_id["1011001"]["skin_name"], "Default")
        self.assertEqual(by_id["1011100"]["skin_name"], "Mighty G-Bomb")
        self.assertEqual(by_id["1011500"]["skin_name"], "Punk Rage")
        self.assertEqual(saved["status"]["remote_character_ids"], ["1011"])

    def test_generated_catalog_parser_keeps_only_costumes(self):
        payload = {
            "t": ["costume", "mvp"],
            "p": "/wp-content/uploads/marvel-assets/",
            "rows": [
                ["10", "1011001", "HULK Default", "default", None, 0, "1", None, None, None, None,
                 "items/costume/1/hulk.png"],
                ["11", "1011500001", "Victory", "victory", None, 1, "1", None, None, None, None,
                 "items/mvp/1/victory.png"],
            ],
        }
        script = "var D=" + json.dumps(payload, separators=(",", ":")) + ";var p=[];"
        self.assertEqual(update_rivalskins_catalog.generated_costumes(script), [{
            "site_id": "10",
            "skin_id": "1011001",
            "name": "HULK Default",
            "slug": "default",
            "hero_id": "1",
            "icon_url": "https://rivalskins.com/wp-content/uploads/marvel-assets/items/costume/1/hulk.png",
        }])

    def test_catalog_files_parse_as_json_without_duplicate_object_keys(self):
        for path in (
            pathlib.Path(characters._DATA_PATH),
            pathlib.Path(skin_catalog._DATA_PATH),
        ):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIsNotNone(json.loads(text, object_pairs_hook=self._reject_duplicate_keys))

    @staticmethod
    def _reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise AssertionError(f"Chave JSON duplicada: {key}")
            result[key] = value
        return result


if __name__ == "__main__":
    unittest.main()
