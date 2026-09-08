"""Mede a montagem da home com dados sintéticos, sem acessar a biblioteca real.

Uso: python tests/benchmark_library.py --sizes 500 3000 --repeats 3
O caso legacy reproduz as cinco chamadas e seis leituras de catálogo da v0.29.0;
após a otimização, a segunda leitura antiga de list_mods é simulada explicitamente.
Tempos são sequenciais no backend e não incluem WebView, desenho, miniaturas ou jogo.
"""
import argparse
import inspect
import json
import pathlib
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from backend import mod_ops, storage


def synthetic_mods(count):
    mods = []
    heroes = ("Hela", "Storm", "Magik", "White Fox", "Invisible Woman")
    for index in range(count):
        components, cache = [], {}
        for variant in range(3):
            cid = f"{index:06d}_{variant}"
            files = [{"name": f"Components/{cid}/Package.{ext}", "size": 1000000, "sha256": "a" * 64}
                     for ext in ("pak", "utoc", "ucas")]
            components.append({"id": cid, "name": f"Variante {variant}", "types": ["Mesh", "Texture"],
                               "enabled": variant == 0, "files": files})
            cache[f"classification-v1:{cid}"] = {
                "signature": "b" * 64,
                "paths": [f"Marvel/Content/Characters/{1000 + index}/Costumes/{variant}/Meshes/Subfolder/SK_Model_{asset}.uasset"
                          for asset in range(40)]}
        mods.append({"id": f"mod{index:06d}", "name": f"Mod sintético {index}",
                     "character": heroes[index % len(heroes)], "skin": "Default", "type": "Mesh",
                     "types": ["Mesh", "Texture"], "enabled": index % 3 != 0, "size_mb": 9,
                     "folder": f"{heroes[index % len(heroes)]}/Default/Package{index}",
                     "tags": [f"Tag {index % 12}"], "components": components,
                     "files": [entry for c in components for entry in c["files"]], "asset_path_cache": cache})
    return mods


def legacy_home():
    if "_mods" in inspect.signature(mod_ops.list_mods).parameters:
        records = storage.load_mods()
        storage.load_mods()  # Segunda leitura de list_mods na v0.29.0.
        mods = mod_ops.list_mods(include_thumbnails=False, _mods=records)
    else:
        mods = mod_ops.list_mods(include_thumbnails=False)
    return {"mods": mods, "characters": mod_ops.get_characters(), "types": mod_ops.get_types(),
            "tags": mod_ops.get_tags(), "folders": mod_ops.get_folders()}


def measure(function, repeats):
    timings, serialization = [], []
    loads, settings_loads, payload_bytes = 0, 0, 0
    for _ in range(repeats):
        with patch.object(storage, "load_mods", wraps=storage.load_mods) as loaded, \
             patch.object(storage, "load_settings", wraps=storage.load_settings) as settings:
            started = time.perf_counter()
            payload = function()
            built = time.perf_counter()
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            finished = time.perf_counter()
            timings.append((built - started) * 1000)
            serialization.append((finished - built) * 1000)
            loads, settings_loads, payload_bytes = loaded.call_count, settings.call_count, len(encoded)
        del payload, encoded
    return {"build_ms_median": round(statistics.median(timings), 2),
            "serialize_ms_median": round(statistics.median(serialization), 2),
            "catalog_reads": loads, "settings_reads": settings_loads, "payload_bytes": payload_bytes}


def run(sizes=(500, 3000), repeats=3, mode="both"):
    results = []
    with tempfile.TemporaryDirectory(prefix="marvel-benchmark-") as temporary:
        root = pathlib.Path(temporary)
        with patch.multiple(storage, MODS_JSON=str(root / "mods.json"), SETTINGS_FILE=str(root / "settings.json"),
                            STORAGE_DIR=str(root / "library"), BACKUPS_DIR=str(root / "backups")):
            storage.ensure_dirs()
            for count in sizes:
                storage.save_mods(synthetic_mods(count))
                row = {"mods": count, "components_per_mod": 3, "cached_paths_per_component": 40,
                       "catalog_bytes": pathlib.Path(storage.MODS_JSON).stat().st_size, "repeats": repeats}
                if mode in {"both", "legacy"}:
                    row["legacy"] = measure(legacy_home, repeats)
                if mode in {"both", "snapshot"} and hasattr(mod_ops, "get_library_snapshot"):
                    row["snapshot"] = measure(mod_ops.get_library_snapshot, repeats)
                results.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[500, 3000])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--mode", choices=("both", "legacy", "snapshot"), default="both")
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10 or any(not 1 <= size <= 10000 for size in args.sizes):
        parser.error("Use 1–10 repetições e 1–10000 registros.")
    run(args.sizes, args.repeats, args.mode)
