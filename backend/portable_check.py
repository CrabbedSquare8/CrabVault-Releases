"""Diagnóstico do pacote distribuído, sem abrir a janela ou ler a biblioteca."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from . import storage


def check_distribution():
    root = Path(storage.RESOURCE_DIR)
    required = (
        "frontend/index.html", "frontend/app.js", "frontend/i18n.js", "frontend/model-viewer.js",
        "frontend/vendor/three/three.module.min.js", "backend/character_data.json",
        "tools/native3d/runtime/Marvel3DExtractor.exe",
        "tools/native3d/runtime/Marvel3DExtractor.runtimeconfig.json",
        "tools/native3d/runtime/coreclr.dll", "tools/native3d/runtime/hostfxr.dll",
        "tools/uassettool/UAssetTool.exe", "tools/dotnet8/dotnet.exe",
        "tools/7zip/7z.exe", "tools/7zip/7z.dll",
        "tools/vgmstream/vgmstream-cli.exe", "tools/handbrake/HandBrakeCLI.exe",
    )
    missing = [name for name in required if not (root / name).is_file()]
    report = {"ok": not missing, "frozen": bool(getattr(sys, "frozen", False)),
              "root": str(root), "missing": missing, "native_bootstrap": False,
              "uassettool_bootstrap": False,
              "scope": "Arquivos do pacote e início dos leitores 3D/assets; não valida GPU, modelos ou o jogo."}
    if missing:
        return report
    try:
        config = json.loads((root / "tools/native3d/runtime/Marvel3DExtractor.runtimeconfig.json").read_text())
        runtime = config["runtimeOptions"]
        if runtime.get("framework") or runtime.get("frameworks") or not runtime.get("includedFrameworks"):
            raise ValueError("O extrator ainda exige .NET externo.")
        with tempfile.TemporaryDirectory(prefix="marvel-portable-check-") as temporary:
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(("DOTNET_", "COREHOST_"))}
            env.update(PATH="", DOTNET_ROOT=temporary, DOTNET_ROOT_X64=temporary,
                       DOTNET_MULTILEVEL_LOOKUP="0", DOTNET_DISABLE_GUI_ERRORS="1")
            process = subprocess.run([str(root / "tools/native3d/runtime/Marvel3DExtractor.exe")],
                                     cwd=temporary, env=env, capture_output=True, text=True,
                                     timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            response = json.loads(process.stdout.strip())
            if process.returncode != 1 or response.get("ok") is not False or "--archives" not in response.get("error", ""):
                raise ValueError("O extrator não iniciou com o runtime próprio.")
            report["native_bootstrap"] = True
            # UAssetTool is a framework-dependent single-file application. Its
            # private .NET 8 directory must work even with no system installation.
            asset_env = dict(env)
            asset_env.update(DOTNET_ROOT=str(root / "tools/dotnet8"),
                             DOTNET_ROOT_X64=str(root / "tools/dotnet8"))
            asset_process = subprocess.run([str(root / "tools/uassettool/UAssetTool.exe"), "--help"],
                                           cwd=temporary, env=asset_env, capture_output=True,
                                           text=True, timeout=30,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if (asset_process.returncode != 0 or "Usage: UAssetTool" not in asset_process.stdout
                    or "list_iostore" not in asset_process.stdout):
                raise ValueError("O leitor de assets não iniciou com o .NET 8 do pacote.")
            report["uassettool_bootstrap"] = True
    except (OSError, ValueError, TypeError, AttributeError, KeyError, subprocess.SubprocessError) as error:
        report.update(ok=False, error=str(error))
    return report


def write_report(destination=None):
    report = check_distribution()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if destination:
        # Exclusive creation: diagnostics must never replace existing user data.
        with open(destination, "x", encoding="utf-8") as stream:
            stream.write(text)
    elif sys.stdout is not None:
        print(text)
    return 0 if report["ok"] else 1
