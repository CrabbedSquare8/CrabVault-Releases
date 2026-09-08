"""Non-destructive cold-cache benchmark. Generated data stays on the project drive."""
import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from backend import mod_ops, native3d_jobs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mod_id")
    parser.add_argument("component_id")
    parser.add_argument("--gpu", action="store_true", help="Test original BC textures supported by the viewer GPU")
    args = parser.parse_args()
    root = tempfile.mkdtemp(prefix="benchmark-", dir=mod_ops._NATIVE3D_CACHE_ROOT)
    original_run = native3d_jobs.PreviewJob.run
    extractor = {}

    def run(*positional, **kwargs):
        result = original_run(*positional, **kwargs)
        for line in reversed((result.stdout or "").splitlines()):
            try:
                data = json.loads(line)
                if isinstance(data, dict) and "ok" in data:
                    extractor.update(data)
                    break
            except (ValueError, TypeError):
                pass
        return result

    start = time.perf_counter()
    with patch.object(mod_ops, "_NATIVE3D_CACHE_ROOT", root), \
            patch.object(mod_ops.storage, "save_mods"), \
            patch.object(mod_ops, "_record_activity"), \
            patch.object(native3d_jobs.PreviewJob, "run", run):
        result = mod_ops.prepare_component_3d_preview(args.mod_id, args.component_id,
            gpu_formats=["dxt1", "dxt3", "dxt5", "bc7"] if args.gpu else [])
    summary = {"ok": result.get("ok"), "error": result.get("error"),
               "elapsed": round(time.perf_counter() - start, 3),
               "models": len(result.get("models", [])), "cache_root": root,
               "timings": extractor.get("timings"),
               "selected_packages": extractor.get("selected_packages"),
               "failures": extractor.get("failures")}
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    with open(pathlib.Path(root) / "benchmark.json", "w", encoding="utf-8") as output:
        json.dump({"summary": summary, "result": result, "extractor": extractor}, output, indent=2)


if __name__ == "__main__":
    main()
