"""Atualiza o CrabVault exclusivamente a partir de releases verificadas do projeto."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

CURRENT_VERSION = "0.45.0"
REPOSITORY = "CrabbedSquare8/CrabVault-Releases"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=100"
VERSION_RE = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")
SHA256_RE = re.compile(r"^([0-9a-fA-F]{64})\s+\*?([^\r\n]+)$")
MAX_INSTALLER_BYTES = 1024 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
INSTALLER_ASSET_RE = re.compile(r"^CrabVault-v\d+\.\d+\.\d+-windows-x64-setup\.exe$")
_download_stats_cache = None
_download_stats_cached_at = 0.0
_download_stats_lock = threading.Lock()
DOWNLOAD_STATS_TTL_SECONDS = 15 * 60


def _version(value: str) -> tuple[int, int, int]:
    value = str(value or "").removeprefix("v")
    if not VERSION_RE.fullmatch(value):
        raise ValueError("A release não possui uma versão X.Y.Z válida.")
    return tuple(map(int, value.split(".")))


def _read_url(url: str, limit: int, *, accept: str = "application/octet-stream") -> bytes:
    request = Request(url, headers={"Accept": accept, "User-Agent": f"CrabVault/{CURRENT_VERSION}"})
    with urlopen(request, timeout=30) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname not in {
            "api.github.com", "github.com", "objects.githubusercontent.com",
            "release-assets.githubusercontent.com",
        }:
            raise ValueError("O GitHub redirecionou o download para um endereço não permitido.")
        length = response.headers.get("Content-Length")
        if length and int(length) > limit:
            raise ValueError("O arquivo da atualização excede o limite permitido.")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("O arquivo da atualização excede o limite permitido.")
    return data


def _release() -> dict:
    try:
        raw = _read_url(LATEST_RELEASE_API, MAX_METADATA_BYTES, accept="application/vnd.github+json")
        release = json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        if exc.code in {401, 403, 404}:
            raise RuntimeError("A release não está publicada ou o repositório privado não permite acesso sem autenticação.") from exc
        raise RuntimeError(f"O GitHub respondeu com o código HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("Não foi possível conectar ao GitHub.") from exc
    if release.get("draft") or release.get("prerelease"):
        raise RuntimeError("A release mais recente ainda não é uma versão pública estável.")
    latest = str(release.get("tag_name", "")).removeprefix("v")
    _version(latest)
    assets = {item.get("name"): item for item in release.get("assets", []) if isinstance(item, dict)}
    installer_name = f"CrabVault-v{latest}-windows-x64-setup.exe"
    checksum_name = f"CrabVault-v{latest}-windows-x64-setup.sha256"
    installer, checksum = assets.get(installer_name), assets.get(checksum_name)
    if not installer or not checksum:
        raise RuntimeError("A release não contém o instalador e o arquivo SHA-256 esperados.")
    for asset in (installer, checksum):
        parsed = urlparse(str(asset.get("browser_download_url", "")))
        if parsed.scheme != "https" or parsed.hostname != "github.com" or not parsed.path.startswith(f"/{REPOSITORY}/releases/download/"):
            raise RuntimeError("A release contém um endereço de download inesperado.")
    return {"release": release, "version": latest, "installer": installer, "checksum": checksum}


def check() -> dict:
    try:
        info = _release()
        available = _version(info["version"]) > _version(CURRENT_VERSION)
        return {
            "ok": True, "current_version": CURRENT_VERSION, "latest_version": info["version"],
            "available": available, "release_url": info["release"].get("html_url", ""),
            "notes": str(info["release"].get("body") or "")[:4000],
            "download_size": int(info["installer"].get("size") or 0),
        }
    except Exception as exc:
        return {"ok": False, "current_version": CURRENT_VERSION, "error": str(exc)}


def github_download_stats() -> dict:
    """Return GitHub asset downloads, not a count of unique people."""
    global _download_stats_cache, _download_stats_cached_at
    now = time.monotonic()
    with _download_stats_lock:
        if _download_stats_cache is not None and now - _download_stats_cached_at < DOWNLOAD_STATS_TTL_SECONDS:
            return dict(_download_stats_cache)
    try:
        raw = _read_url(RELEASES_API, MAX_METADATA_BYTES, accept="application/vnd.github+json")
        releases = json.loads(raw.decode("utf-8"))
        if not isinstance(releases, list):
            raise ValueError("O GitHub retornou uma lista de releases inválida.")
        downloads = 0
        release_count = 0
        for release in releases:
            if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
                continue
            matched = False
            for asset in release.get("assets", []):
                if not isinstance(asset, dict) or not INSTALLER_ASSET_RE.fullmatch(str(asset.get("name") or "")):
                    continue
                downloads += max(0, int(asset.get("download_count") or 0))
                matched = True
            release_count += int(matched)
        result = {
            "ok": True,
            "downloads": downloads,
            "release_count": release_count,
            "repository_url": f"https://github.com/{REPOSITORY}",
            "label": "GitHub downloads",
        }
        with _download_stats_lock:
            _download_stats_cache = dict(result)
            _download_stats_cached_at = now
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def download_and_install(base_dir: str, close_callback) -> dict:
    """Baixa, valida e agenda o instalador. Nenhuma URL vem da interface."""
    try:
        info = _release()
        if _version(info["version"]) <= _version(CURRENT_VERSION):
            return {"ok": False, "error": "Nenhuma atualização mais recente está disponível."}
        installer_name = info["installer"]["name"]
        checksum_data = _read_url(info["checksum"]["browser_download_url"], MAX_METADATA_BYTES).decode("ascii").strip()
        match = SHA256_RE.fullmatch(checksum_data)
        if not match or match.group(2).strip() != installer_name:
            raise RuntimeError("O arquivo SHA-256 da release é inválido.")
        payload = _read_url(info["installer"]["browser_download_url"], MAX_INSTALLER_BYTES)
        if not payload.startswith(b"MZ") or hashlib.sha256(payload).hexdigest().lower() != match.group(1).lower():
            raise RuntimeError("O instalador baixado não passou na verificação SHA-256.")
        cache = Path(base_dir) / ".cache" / "updates"
        cache.mkdir(parents=True, exist_ok=True)
        target = cache / installer_name
        partial = target.with_suffix(target.suffix + ".partial")
        partial.write_bytes(payload)
        os.replace(partial, target)

        def launch():
            time.sleep(1.2)
            subprocess.Popen([str(target), "/SILENT", "/CLOSEAPPLICATIONS", f"/DIR={Path(base_dir).resolve()}"], cwd=cache)
            close_callback()

        threading.Thread(target=launch, name="crabvault-update", daemon=True).start()
        return {"ok": True, "version": info["version"], "installer": str(target)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
