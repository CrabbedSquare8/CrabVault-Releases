"""Verify the distributed extractor can start without a separately installed .NET.

This is a bootstrap check, not a model-conversion test. It never reads the
catalog, settings, FModel, or game files. Its only writes are inside a temporary
directory that is removed on exit.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def check_runtime(runtime):
    runtime = Path(runtime).resolve()
    config_path = runtime / "Marvel3DExtractor.runtimeconfig.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))["runtimeOptions"]
    if config.get("framework") or config.get("frameworks") or not config.get("includedFrameworks"):
        raise ValueError("O extrator publicado ainda exige uma instalação separada do .NET.")
    for filename in ("Marvel3DExtractor.exe", "Marvel3DExtractor.dll", "hostfxr.dll", "hostpolicy.dll", "coreclr.dll"):
        if not (runtime / filename).is_file():
            raise FileNotFoundError(f"Runtime incompleto: {filename}")

    with tempfile.TemporaryDirectory(prefix="runtime-check-", dir=runtime.parent) as temporary:
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("DOTNET_", "COREHOST_"))}
        environment.update(PATH="", DOTNET_ROOT=temporary, DOTNET_ROOT_X64=temporary,
                           DOTNET_MULTILEVEL_LOOKUP="0", DOTNET_DISABLE_GUI_ERRORS="1")
        # A managed, structured argument error proves Main was reached. A native
        # host error (missing .NET) cannot satisfy this assertion.
        result = subprocess.run([str(runtime / "Marvel3DExtractor.exe")],
                                cwd=temporary, env=environment, capture_output=True,
                                text=True, timeout=30)
        try:
            response = json.loads(result.stdout.strip())
        except (ValueError, TypeError):
            raise RuntimeError(f"O extrator não iniciou: {result.stderr or result.stdout}")
        if result.returncode != 1 or response.get("ok") is not False or "--archives" not in response.get("error", ""):
            raise RuntimeError(f"Resposta inesperada do extrator: {response}")
    return {"ok": True, "runtime": str(runtime), "frameworks": config["includedFrameworks"],
            "scope": "bootstrap sem PATH/.NET externo; não valida conversão de modelos"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", nargs="?", default=str(Path(__file__).resolve().parent / "runtime"))
    args = parser.parse_args()
    try:
        result = check_runtime(args.runtime)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
