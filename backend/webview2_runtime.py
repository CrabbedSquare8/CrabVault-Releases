"""Detecção e preparação transparente do WebView2 Evergreen no Windows."""
from __future__ import annotations

import ctypes
import locale
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.request import Request, urlopen

MINIMUM_VERSION = (120, 0, 0, 0)
BOOTSTRAPPER_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
MAX_BOOTSTRAPPER_BYTES = 8 * 1024 * 1024


def _version(value):
    try:
        parts = tuple(int(part) for part in value.split("."))
    except (AttributeError, ValueError):
        return None
    return (parts + (0, 0, 0, 0))[:4]


def installed_version(environ=None):
    env = os.environ if environ is None else environ
    roots = []
    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = env.get(variable)
        if base:
            roots.append(Path(base) / "Microsoft/EdgeWebView/Application")
    found = []
    for root in roots:
        if not root.is_dir():
            continue
        for child in root.iterdir():
            parsed = _version(child.name)
            if parsed and (child / "msedgewebview2.exe").is_file():
                found.append(parsed)
    return max(found, default=None)


def is_compatible(version=None):
    current = installed_version() if version is None else version
    return current is not None and current >= MINIMUM_VERSION


def _portuguese():
    language = (locale.getlocale()[0] or "").lower()
    return language.startswith("pt")


def _message(text_pt, text_en, flags):
    text = text_pt if _portuguese() else text_en
    return ctypes.windll.user32.MessageBoxW(None, text, "CrabVault", flags)


def _download(destination):
    request = Request(BOOTSTRAPPER_URL, headers={"User-Agent": "CrabVault-WebView2-Setup"})
    total = 0
    with urlopen(request, timeout=60) as response, destination.open("xb") as output:
        if response.url.lower().split(":", 1)[0] != "https":
            raise ValueError("O download foi redirecionado para uma conexão insegura.")
        while chunk := response.read(256 * 1024):
            total += len(chunk)
            if total > MAX_BOOTSTRAPPER_BYTES:
                raise ValueError("O instalador do WebView2 excedeu o limite esperado.")
            output.write(chunk)
    if total < 64 * 1024 or destination.read_bytes()[:2] != b"MZ":
        raise ValueError("O arquivo recebido não é um instalador Windows válido.")


def _verify_microsoft_signature(path):
    command = (
        "$s=Get-AuthenticodeSignature -LiteralPath $args[0];"
        "if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Microsoft'){exit 1}"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command, str(path)],
        timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise ValueError("A assinatura digital Microsoft do instalador não pôde ser confirmada.")


def ensure_runtime():
    current = installed_version()
    if is_compatible(current):
        return True
    detail_pt = "não foi encontrado" if current is None else "está desatualizado"
    detail_en = "was not found" if current is None else "is outdated"
    answer = _message(
        "O Microsoft Edge WebView2 Runtime " + detail_pt + ".\n\n"
        "O CrabVault precisa desse componente oficial da Microsoft para exibir sua interface. "
        "Ele será baixado da Microsoft e instalado para o seu usuário. Deseja continuar?",
        "Microsoft Edge WebView2 Runtime " + detail_en + ".\n\n"
        "CrabVault needs this official Microsoft component to display its interface. "
        "It will be downloaded from Microsoft and installed for your user. Continue?",
        0x00000004 | 0x00000030,
    )
    if answer != 6:
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="crabvault-webview2-") as temporary:
            installer = Path(temporary) / "MicrosoftEdgeWebview2Setup.exe"
            _download(installer)
            _verify_microsoft_signature(installer)
            result = subprocess.run(
                [str(installer), "/silent", "/install"], timeout=600,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode not in (0, 3010):
                raise RuntimeError(f"O instalador retornou o código {result.returncode}.")
        if not is_compatible():
            raise RuntimeError("O WebView2 continua indisponível após a instalação.")
        return True
    except Exception as error:
        _message(
            f"Não foi possível preparar o WebView2.\n\n{error}\n\nVerifique sua conexão e tente abrir o CrabVault novamente.",
            f"WebView2 could not be prepared.\n\n{error}\n\nCheck your connection and open CrabVault again.",
            0x00000010,
        )
        return False
