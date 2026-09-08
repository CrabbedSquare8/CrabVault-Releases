"""Convert one library model with no FModel setting, PATH tools, or .NET install.

Reads the selected source containers and game dependencies in place. Catalog and
settings writes are forbidden. Generated previews and staging lists use a fresh
temporary directory, removed on exit. The normal support manager may acquire
its own support files on first use; it never uses the configured FModel path.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import mod_ops, native3d_jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mod_id")
    parser.add_argument("component_id")
    parser.add_argument("--gpu", action="store_true", help="Preserva blocos BC compatíveis em vez de converter tudo para PNG")
    args = parser.parse_args()
    settings = json.loads(Path(mod_ops.storage.SETTINGS_FILE).read_text(encoding="utf-8"))
    settings.pop("fmodel_path", None)
    catalog = json.loads(Path(mod_ops.storage.MODS_JSON).read_text(encoding="utf-8"))
    workspace = Path(mod_ops.storage.BASE_DIR)
    work_parent = workspace / ".cache" / "native3d"
    work_parent.mkdir(parents=True, exist_ok=True)
    process_run = native3d_jobs.PreviewJob.run
    extractor = {}

    def run(job, command, *positional, **kwargs):
        if Path(command[0]).name.casefold() != "marvel3dextractor.exe":
            raise AssertionError("A prévia tentou usar o SDK ou um extrator externo.")
        result = process_run(job, command, *positional, **kwargs)
        for line in reversed(result.stdout.splitlines()):
            try:
                response = json.loads(line)
            except ValueError:
                continue
            if isinstance(response, dict) and "ok" in response:
                extractor.update(response)
                break
        return result

    with tempfile.TemporaryDirectory(prefix="independent-smoke-", dir=work_parent) as temporary:
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("DOTNET_", "COREHOST_"))}
        environment.update(PATH="", DOTNET_ROOT=temporary, DOTNET_ROOT_X64=temporary,
                           DOTNET_MULTILEVEL_LOOKUP="0", DOTNET_DISABLE_GUI_ERRORS="1")
        start = time.perf_counter()
        with patch.dict(os.environ, environment, clear=True), \
                patch.object(mod_ops.storage, "load_mods", side_effect=lambda: copy.deepcopy(catalog)), \
                patch.object(mod_ops.storage, "load_settings", side_effect=lambda: copy.deepcopy(settings)), \
                patch.object(mod_ops.storage, "save_mods", side_effect=AssertionError("Catálogo não pode mudar")), \
                patch.object(mod_ops.storage, "save_settings", side_effect=AssertionError("Configurações não podem mudar")), \
                patch.object(mod_ops, "_record_activity"), \
                patch.object(mod_ops, "_NATIVE3D_CACHE_ROOT", str(Path(temporary) / "preview")), \
                patch.object(mod_ops, "_NATIVE3D_WORK_ROOT", str(Path(temporary) / "stage")), \
                patch.object(native3d_jobs.PreviewJob, "run", run):
            result = mod_ops.prepare_component_3d_preview(args.mod_id, args.component_id,
                gpu_formats=["dxt1", "dxt3", "dxt5", "bc7"] if args.gpu else [])
        output_files = list((Path(temporary) / "preview").rglob("*"))
        summary = {"ok": bool(result.get("ok")), "error": result.get("error"),
                   "elapsed": round(time.perf_counter() - start, 3),
                   "models": len(result.get("models", [])),
                   "generated_bytes": sum(path.stat().st_size for path in output_files if path.is_file()),
                   "timings": extractor.get("timings"),
                   "selected_packages": extractor.get("selected_packages"),
                   "failures": extractor.get("failures"), "temporary_files_removed_on_exit": True}
    print(json.dumps(summary, ensure_ascii=False))
    raise SystemExit(0 if summary["ok"] else 1)


if __name__ == "__main__":
    main()
