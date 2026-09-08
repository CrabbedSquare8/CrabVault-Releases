"""Benchmarks seguros dos caminhos que cercam importação, detalhes e classificação.

O modo padrão usa dados sintéticos em uma pasta temporária. ``--local-read-only``
copia somente os JSONs para a pasta temporária e lê os pacotes/mídias da
biblioteca atual sem modificá-los. O script compara os hashes dos JSONs reais
antes e depois e não abre o jogo.

Uso:
    python tests/benchmark_performance_validation.py
    python tests/benchmark_performance_validation.py --local-read-only --repeats 3
    python tests/benchmark_performance_validation.py --local-read-only --profile-classifications
"""
from __future__ import annotations

import argparse
import cProfile
import hashlib
import io
import json
import pathlib
import pstats
import re
import shutil
import statistics
import sys
import tempfile
import time
from collections import Counter
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend import library_maintenance, mod_ops, native3d_support, storage
from benchmark_library import synthetic_mods


ROOT = pathlib.Path(__file__).resolve().parents[1]


def _digest(path: pathlib.Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def _summary(values: list[float]) -> dict:
    return {
        "median_ms": round(statistics.median(values), 2),
        "min_ms": round(min(values), 2),
        "max_ms": round(max(values), 2),
        "samples_ms": [round(value, 2) for value in values],
    }


def _snapshot_measure(repeats: int) -> dict:
    builds, serialization = [], []
    payload_bytes = 0
    for _ in range(repeats):
        started = time.perf_counter()
        payload = mod_ops.get_library_snapshot()
        built = time.perf_counter()
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        finished = time.perf_counter()
        builds.append((built - started) * 1000)
        serialization.append((finished - built) * 1000)
        payload_bytes = len(encoded)
    return {
        "build": _summary(builds),
        "serialize": _summary(serialization),
        "payload_bytes": payload_bytes,
        "mods": len(payload["mods"]),
    }


def _catalog_classification_summary(mods: list[dict]) -> dict:
    saved_unknown = []
    for mod in mods:
        for component in mod.get("components", []):
            saved = component.get("types") or [component.get("type") or "Unknown"]
            if "Unknown" in saved:
                saved_unknown.append((mod, component))
    normalized = Counter()
    for mod, component in saved_unknown:
        normalized[(mod.get("install_target") or "pak",
                    tuple(mod_ops._component_types_from_metadata(mod, component)))] += 1
    return {
        "components": sum(len(mod.get("components", [])) for mod in mods),
        "saved_unknown": len(saved_unknown),
        "missing_type_metadata": sum(
            not component.get("types") and not component.get("type")
            for _, component in saved_unknown
        ),
        "explicit_unknown": sum(
            component.get("types") == ["Unknown"] or component.get("type") == "Unknown"
            for _, component in saved_unknown
        ),
        "saved_unknown_by_target": dict(Counter(mod.get("install_target") or "pak"
                                                  for mod, _ in saved_unknown)),
        "metadata_result": [
            {"target": target, "types": list(types), "count": count}
            for (target, types), count in sorted(normalized.items())
        ],
    }


def _detail_samples(mods: list[dict]) -> dict:
    candidates = sorted(
        (mod for mod in mods if not mod.get("install_target") and mod.get("components")),
        key=lambda mod: len(mod["components"]),
    )
    if not candidates:
        return {"samples": []}
    indices = sorted({round(index * (len(candidates) - 1) / 9) for index in range(10)})
    results = []
    original_save = storage.save_mods
    with patch.object(storage, "save_mods", wraps=original_save) as saves:
        for index in indices:
            record = candidates[index]
            before = saves.call_count
            started = time.perf_counter()
            detail = mod_ops.get_mod_details(record["id"], include_previews=False)
            elapsed = (time.perf_counter() - started) * 1000
            results.append({
                "components": len(record["components"]),
                "files": len(record.get("files", [])),
                "elapsed_ms": round(elapsed, 2),
                "temporary_catalog_saves": saves.call_count - before,
                "classification_pending": bool(detail.get("component_classification_pending")),
                "asset_count": detail.get("asset_count", 0),
            })
    return {
        "samples": results,
        "median_ms": round(statistics.median(item["elapsed_ms"] for item in results), 2),
        "max_ms": max(item["elapsed_ms"] for item in results),
    }


def _cover_sources(mods: list[dict]) -> list[tuple[int, pathlib.Path]]:
    result = []
    for mod in mods:
        images = mod.get("images") or ([mod["image"]] if mod.get("image") else [])
        cover = mod.get("image") or (images[0] if images else None)
        if not cover:
            continue
        path = pathlib.Path(storage.STORAGE_DIR) / mod_ops._storage_relative(mod) / cover
        try:
            result.append((path.stat().st_size, path))
        except OSError:
            continue
    return sorted(result)


def _cover_measure(mods: list[dict]) -> dict:
    sources = _cover_sources(mods)
    if not sources:
        return {"declared": sum(bool(mod.get("image") or mod.get("images")) for mod in mods), "found": 0}
    median_size = statistics.median(size for size, _ in sources)
    selected = [
        ("median", min(sources, key=lambda item: abs(item[0] - median_size))),
        ("largest", sources[-1]),
    ]
    cache_root = pathlib.Path(storage.STORAGE_DIR) / ".thumbnails"
    cached = sum(
        (cache_root / ((mod_ops._thumbnail_key(path) or "") + ".jpg")).is_file()
        for _, path in sources
    )
    samples = []
    for label, (size, source) in selected:
        with tempfile.TemporaryDirectory(prefix="marvel-cover-benchmark-") as temporary:
            root = pathlib.Path(temporary)
            private = root / "library" / "sample"
            private.mkdir(parents=True)
            destination = private / source.name
            shutil.copy2(source, destination)
            (root / "mods.json").write_text(json.dumps([{
                "id": "sample", "storage_folder": "sample", "image": source.name, "images": [source.name],
            }]), encoding="utf-8")
            (root / "settings.json").write_text(json.dumps({"settings_ui_version": 8}), encoding="utf-8")
            with patch.multiple(
                storage,
                STORAGE_DIR=str(root / "library"),
                BACKUPS_DIR=str(root / "backups"),
                MODS_JSON=str(root / "mods.json"),
                SETTINGS_FILE=str(root / "settings.json"),
            ):
                elapsed = []
                response = None
                for _ in range(3):
                    started = time.perf_counter()
                    response = mod_ops.get_mod_thumbnail("sample")
                    elapsed.append((time.perf_counter() - started) * 1000)
                samples.append({
                    "sample": label,
                    "source_bytes": size,
                    "cold_ms": round(elapsed[0], 2),
                    "warm_ms": [round(value, 2) for value in elapsed[1:]],
                    "thumbnail_payload_bytes": len((response or {}).get("image_url") or ""),
                })
    return {
        "declared": sum(bool(mod.get("image") or mod.get("images")) for mod in mods),
        "found": len(sources),
        "cached_current_revision": cached,
        "median_source_bytes": int(median_size),
        "largest_source_bytes": sources[-1][0],
        "samples": samples,
    }


def _classification_measure(profile: bool) -> dict:
    profiler = cProfile.Profile() if profile else None
    if profiler:
        profiler.enable()
    started = time.perf_counter()
    result = library_maintenance.list_pending_classifications()
    elapsed = (time.perf_counter() - started) * 1000
    if profiler:
        profiler.disable()
    output = {
        "elapsed_ms": round(elapsed, 2),
        "checked": result["checked"],
        "counts": result["counts"],
        "pending_total": len(result["components"]),
        "result_sha256": hashlib.sha256(
            json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    if profiler:
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).sort_stats("cumtime").print_stats(20)
        output["profile_top_20"] = stream.getvalue()
    return output


def _inside_resolved(path: pathlib.Path, root: pathlib.Path) -> bool:
    """Versão de benchmark: ambos os argumentos já foram resolvidos."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _cached_component_source_lookup():
    """Protótipo read-only que elimina resoluções repetidas das mesmas raízes.

    A validação continua resolvendo cada caminho final, portanto links e
    junctions ainda são verificados. Esta função não substitui código do app;
    ela mede uma correção candidata e exige resultado byte a byte equivalente.
    """
    resolved_storage = pathlib.Path(storage.STORAGE_DIR).resolve()
    roots = {}

    def safe_child(root: pathlib.Path, relative):
        raw = str(relative or "").replace("\\", "/")
        windows = pathlib.PureWindowsPath(raw)
        parts = pathlib.PurePosixPath(raw).parts
        if (not raw or windows.drive or windows.root or raw.startswith("/")
                or any(part in {"..", ""} or ":" in part for part in parts)):
            raise ValueError("O catálogo contém um caminho de arquivo inválido.")
        result = root.joinpath(*parts).resolve()
        if result == root or not _inside_resolved(result, root):
            raise ValueError("O caminho do arquivo sai da pasta permitida.")
        return result

    def component_sources(mod, component, settings):
        cache_key = id(mod)
        if cache_key not in roots:
            private = pathlib.Path(mod_ops._storage_dir(mod)).resolve()
            if private == resolved_storage or not _inside_resolved(private, resolved_storage):
                raise ValueError("A pasta privada deste mod sai da biblioteca configurada.")
            mods_path = str(settings.get("mods_path") or "")
            active = None
            if mods_path:
                resolved_mods = pathlib.Path(mods_path).resolve()
                active = pathlib.Path(mod_ops._game_target_dir(mod, mods_path)).resolve()
                if not mod.get("install_target") and not _inside_resolved(active, resolved_mods):
                    raise ValueError("A pasta ativa deste mod sai da pasta do jogo configurada.")
            roots[cache_key] = private, active
        private, active = roots[cache_key]
        sources = []
        for entry in component.get("files", []):
            name = entry.get("name", "") if isinstance(entry, dict) else ""
            backup = safe_child(private, name)
            game = safe_child(active, name) if active is not None else None
            if backup.is_file():
                sources.append(str(backup))
            elif game is not None and game.is_file():
                sources.append(str(game))
        return sources

    return component_sources


def _classification_cached_roots_prototype(expected_sha256: str) -> dict:
    with patch.object(library_maintenance, "_component_sources", new=_cached_component_source_lookup()):
        measured = _classification_measure(False)
    measured["equivalent_to_current"] = measured["result_sha256"] == expected_sha256
    if not measured["equivalent_to_current"]:
        raise RuntimeError("O protótipo de raízes resolvidas mudou o resultado funcional.")
    return measured


def _catalog_summary() -> dict:
    source = json.loads((ROOT / "backend" / "rivalskins_data.json").read_text(encoding="utf-8"))
    numeric = [skin_id for skin_id in source if re.fullmatch(r"\d{7}", skin_id)]
    recolors = [skin_id for skin_id in source if re.fullmatch(r"ps\d{7}", skin_id)]
    return {
        "total": len(source),
        "numeric": len(numeric),
        "recolors": len(recolors),
        "invalid_ids": len(source) - len(numeric) - len(recolors),
        "missing_required_fields": sum(
            not all(isinstance(item.get(field), str) and item[field].strip()
                    for field in ("name", "character", "url", "icon_url"))
            for item in source.values()
        ),
    }


def local_read_only(repeats: int, profile_classifications: bool) -> dict:
    real_mods = ROOT / "mods.json"
    real_settings = ROOT / "settings.json"
    before = {path.name: _digest(path) for path in (real_mods, real_settings)}
    raw_mods = json.loads(real_mods.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="marvel-performance-validation-") as temporary:
        temporary_root = pathlib.Path(temporary)
        temp_mods = temporary_root / "mods.json"
        temp_settings = temporary_root / "settings.json"
        shutil.copy2(real_mods, temp_mods)
        shutil.copy2(real_settings, temp_settings)
        with patch.multiple(
            storage,
            MODS_JSON=str(temp_mods),
            SETTINGS_FILE=str(temp_settings),
            BACKUPS_DIR=str(temporary_root / "backups"),
        ):
            classification_listing = _classification_measure(profile_classifications)
            result = {
                "mode": "local-read-only",
                "snapshot": _snapshot_measure(repeats),
                "details": _detail_samples(raw_mods),
                "covers": _cover_measure(raw_mods),
                "classification_listing": classification_listing,
                "classification_metadata": _catalog_classification_summary(raw_mods),
                "skin_catalog": _catalog_summary(),
                "native3d_support": native3d_support.get_status(),
            }
            if profile_classifications:
                result["classification_cached_roots_prototype"] = _classification_cached_roots_prototype(
                    classification_listing["result_sha256"]
                )
    after = {path.name: _digest(path) for path in (real_mods, real_settings)}
    if before != after:
        raise RuntimeError("Os JSONs reais mudaram durante o benchmark; resultado descartado.")
    result["real_json_hashes_unchanged"] = True
    return result


def synthetic(repeats: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="marvel-performance-synthetic-") as temporary:
        root = pathlib.Path(temporary)
        mods = synthetic_mods(500)
        with patch.multiple(
            storage,
            MODS_JSON=str(root / "mods.json"),
            SETTINGS_FILE=str(root / "settings.json"),
            STORAGE_DIR=str(root / "library"),
            BACKUPS_DIR=str(root / "backups"),
        ):
            storage.ensure_dirs()
            storage.save_mods(mods)
            return {
                "mode": "synthetic",
                "snapshot": _snapshot_measure(repeats),
                "classification_metadata": _catalog_classification_summary(mods),
            }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-read-only", action="store_true", help="Mede a biblioteca atual sem gravá-la.")
    parser.add_argument("--profile-classifications", action="store_true",
                        help="Inclui as 20 funções mais caras da listagem de pendências.")
    parser.add_argument("--repeats", type=int, default=3, help="Repetições da montagem da home (1–10).")
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10:
        parser.error("Use entre 1 e 10 repetições.")
    if args.profile_classifications and not args.local_read_only:
        parser.error("O perfil de classificações requer --local-read-only.")
    result = (local_read_only(args.repeats, args.profile_classifications)
              if args.local_read_only else synthetic(args.repeats))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
