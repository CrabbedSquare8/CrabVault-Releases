"""Suporte 3D gerido pelo Manager, sem procurar instalações de outros programas.

Os codecs são versões fixas do upstream usado pelo CUE4Parse. A Oodle é obtida
sob demanda do WorkingRobot/OodleUE e não acompanha o CrabVault; todos os
downloads e arquivos extraídos têm SHA-256 fixados. Mappings são dados da comunidade, validados pelo Git blob
informado pelo GitHub. Nada é executado durante a preparação.
"""
import contextlib
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from . import operation_jobs, storage


SUPPORT_DIR = Path(storage.BASE_DIR) / ".cache" / "native3d" / "support"
MAPPING_INDEX = "https://api.github.com/repos/SpaceDepot/rivals-depot/contents/usmap?ref=main"
MAPPING_BASE = "https://raw.githubusercontent.com/SpaceDepot/rivals-depot/main/usmap/"
MAPPING_NAME = re.compile(r"^\d+\.\d+\.\d+-(\d+)\+\+\+depot_marvel\+S[\d._]+_release-Marvel\.usmap$")
MAX_MAPPING = 16 * 1024 * 1024
MAX_DLL = 8 * 1024 * 1024
_HEX256 = re.compile(r"^[0-9a-f]{64}$")
_HEX160 = re.compile(r"^[0-9a-f]{40}$")
_LOCK = threading.RLock()

# Release digests confirmed through GitHub's release metadata, 31/08/2026.
# DLL digests confirmed after unpacking those exact archives, without executing.
CODECS = {
    "oodle": {
        "version": "2.9.10",
        "sha256": "6f5d41a7892ea6b2db420f2458dad2f84a63901c9a93ce9497337b16c195f457",
        "url": "https://raw.githubusercontent.com/WorkingRobot/OodleUE/5e38cb6c99c588b51cde0cae4a6420d6bc865605/Engine/Source/Programs/Shared/EpicGames.Oodle/Sdk/2.9.10/win/redist/oo2core_9_win64.dll",
        "archive_sha256": "6f5d41a7892ea6b2db420f2458dad2f84a63901c9a93ce9497337b16c195f457",
        "format": "raw", "max_download": MAX_DLL,
    },
    "zlib": {
        "version": "Zlib-ng.NET 1.0.0",
        "url": "https://github.com/NotOfficer/Zlib-ng.NET/releases/download/1.0.0/zlib-ng2.dll.gz",
        "archive_sha256": "e11f814f64821c482fb81c05fb20d9e5a3be0feb0e2f8fd9480d1f341163e2c1",
        "sha256": "454be2f3d10f804ace577198401431db5e95d0286b59589bc28a40085388e7c2",
        "format": "gzip", "max_download": 1024 * 1024,
    },
}

# Aceito somente para migrar caches criados pelas versões v0.31.0–v0.38.2.
# Nunca volta a ser publicado no manifesto ativo depois que ensure_support roda.
LEGACY_CODEC_DIGESTS = {
    "oodle": {"cba19529d0a3b5ec9c630e95652af01e123ae29a34a8a5f7507f5bcf23d9e82b"},
}


class SupportError(RuntimeError):
    pass


def _check(check):
    if check is not None:
        check()


def _validate_url(url, allow_cdn=False):
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise SupportError("O endereço do suporte 3D é inválido.") from error
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or port not in (None, 443) or parsed.fragment):
        raise SupportError("O endereço do suporte 3D não é um HTTPS permitido.")
    codec_urls = {item["url"] for item in CODECS.values() if item.get("url")}
    permitted = (url == MAPPING_INDEX or url in codec_urls
                 or (parsed.hostname == "raw.githubusercontent.com"
                     and parsed.path.startswith("/SpaceDepot/rivals-depot/main/usmap/")
                     and MAPPING_NAME.fullmatch(urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1]))))
    if allow_cdn and parsed.hostname == "release-assets.githubusercontent.com":
        permitted = True
    if not permitted:
        raise SupportError("O download do suporte 3D tentou acessar uma origem não permitida.")


class _RestrictedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allow_cdn):
        super().__init__()
        self.allow_cdn = allow_cdn

    def redirect_request(self, request, response, code, message, headers, new_url):
        _validate_url(new_url, self.allow_cdn)
        return super().redirect_request(request, response, code, message, headers, new_url)


def _read_limited(stream, limit, check=None, deadline=None):
    blocks, count = [], 0
    while True:
        _check(check)
        if deadline is not None and time.monotonic() >= deadline:
            raise SupportError("O download do suporte 3D demorou demais. Tente novamente.")
        block = stream.read(min(64 * 1024, limit - count + 1))
        if not block:
            return b"".join(blocks)
        count += len(block)
        if count > limit:
            raise SupportError("Um arquivo do suporte 3D excedeu o tamanho permitido.")
        blocks.append(block)


def _download(url, limit, check=None):
    _validate_url(url)
    _check(check)
    allow_cdn = url in {item["url"] for item in CODECS.values() if item.get("url")}
    opener = urllib.request.build_opener(_RestrictedRedirect(allow_cdn))
    request = urllib.request.Request(url, headers={
        "User-Agent": "CrabVault-Native3D", "Accept": "application/vnd.github+json" if url == MAPPING_INDEX else "application/octet-stream",
        "Accept-Encoding": "identity",
    })
    try:
        deadline = time.monotonic() + 90
        with opener.open(request, timeout=15) as response:
            _validate_url(response.geturl(), allow_cdn)
            expected = response.headers.get("Content-Length")
            if expected is not None:
                try:
                    expected = int(expected)
                except ValueError as error:
                    raise SupportError("O tamanho anunciado pelo download é inválido.") from error
            if expected is not None and not 0 <= expected <= limit:
                raise SupportError("Um arquivo do suporte 3D excedeu o tamanho permitido.")
            data = _read_limited(response, limit, check, deadline)
            if expected is not None and len(data) != expected:
                raise SupportError("O download do suporte 3D ficou incompleto. Tente novamente.")
            return data
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise SupportError("Não foi possível baixar o suporte 3D. Verifique a conexão com o GitHub e tente novamente.") from error


def _safe_path(path):
    """Não ler/gravar DLLs por symlinks ou junctions no cache privado."""
    path = Path(path).absolute()
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise SupportError("A pasta do suporte 3D contém um link ou junction não permitido.")
    return path


def _record_path(kind, digest):
    if kind not in {"mapping", "oodle", "zlib"} or not isinstance(digest, str) or not _HEX256.fullmatch(digest):
        raise SupportError("O registro do suporte 3D é inválido.")
    suffix = ".usmap" if kind == "mapping" else ".dll"
    return _safe_path(Path(SUPPORT_DIR) / "files" / f"{kind}-{digest}{suffix}")


def _validate_mapping(data):
    if len(data) < 16 or len(data) > MAX_MAPPING or data[:2] != b"\xc4\x30" or data[2] > 4:
        raise SupportError("O mapping recebido não é um arquivo USMAP compatível.")
    # Bound the decompression allocation even for an authentic but bad mapping.
    offset = 3
    if data[2] >= 1:
        has_versioning = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        if has_versioning not in (0, 1):
            raise SupportError("O cabeçalho do mapping é inválido.")
        if has_versioning:
            if len(data) < offset + 12:
                raise SupportError("O cabeçalho do mapping ficou incompleto.")
            count = struct.unpack_from("<i", data, offset + 8)[0]
            if not 0 <= count <= 8192:
                raise SupportError("O cabeçalho do mapping é inválido.")
            offset += 16 + count * 20
    if len(data) < offset + 9:
        raise SupportError("O cabeçalho do mapping ficou incompleto.")
    compression, compressed, expanded = struct.unpack_from("<BII", data, offset)
    if compression > 3 or not 0 < expanded <= 256 * 1024 * 1024 or compressed != len(data) - offset - 9:
        raise SupportError("O tamanho declarado pelo mapping é inválido.")
    if compression == 0 and compressed != expanded:
        raise SupportError("O tamanho declarado pelo mapping é inválido.")


def _validate_dll(data):
    if len(data) < 256 or len(data) > MAX_DLL or data[:2] != b"MZ":
        raise SupportError("O codec recebido não é uma biblioteca Windows válida.")
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    if offset + 26 > len(data) or data[offset:offset + 4] != b"PE\0\0" or struct.unpack_from("<H", data, offset + 4)[0] != 0x8664:
        raise SupportError("O codec recebido não é uma biblioteca Windows x64 válida.")
    if not struct.unpack_from("<H", data, offset + 22)[0] & 0x2000:
        raise SupportError("O arquivo recebido não é uma DLL.")


def _validate_content(kind, data, digest):
    if hashlib.sha256(data).hexdigest() != digest:
        raise SupportError("A verificação de integridade do suporte 3D falhou. Nenhum arquivo novo foi ativado.")
    (_validate_mapping if kind == "mapping" else _validate_dll)(data)


def _read_record(kind, record):
    if not isinstance(record, dict):
        raise SupportError("O registro do suporte 3D está incompleto.")
    digest = record.get("sha256")
    path = _record_path(kind, digest)
    trusted = {CODECS[kind]["sha256"], *LEGACY_CODEC_DIGESTS.get(kind, ())} if kind in CODECS else None
    if trusted is not None and digest not in trusted:
        raise SupportError("O codec do suporte 3D precisa ser atualizado.")
    with path.open("rb") as stream:
        data = _read_limited(stream, MAX_MAPPING if kind == "mapping" else MAX_DLL)
    _validate_content(kind, data, digest)
    return path


def _load_current():
    path = _safe_path(Path(SUPPORT_DIR) / "current.json")
    with path.open("rb") as stream:
        manifest = json.loads(_read_limited(stream, 16 * 1024))
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise SupportError("O registro do suporte 3D é inválido.")
    paths = tuple(_read_record(kind, manifest.get(kind)) for kind in ("mapping", "oodle", "zlib"))
    return manifest, paths


def get_status():
    """Consulta local: não baixa nada nem depende de configurações legadas."""
    try:
        manifest, _ = _load_current()
        return {"ready": True, "managed": True, "mapping": manifest["mapping"].get("name", ""),
                "mapping_build": manifest["mapping"].get("build"), "updated_at": manifest.get("updated_at"),
                "directory": str(SUPPORT_DIR), "error": ""}
    except (OSError, ValueError, SupportError, TypeError) as error:
        message = "Suporte 3D ainda não preparado. O Manager baixa os arquivos necessários no primeiro uso."
        if not isinstance(error, FileNotFoundError):
            message = "O suporte 3D precisa ser preparado novamente para verificar seus arquivos."
        return {"ready": False, "managed": True, "mapping": "", "directory": str(SUPPORT_DIR), "error": message}


def _store_file(kind, data, digest):
    _validate_content(kind, data, digest)
    destination = _record_path(kind, digest)
    try:
        _read_record(kind, {"sha256": digest})
        return
    except (OSError, SupportError):
        pass
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".download-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _safe_path(destination)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _latest_mapping(check):
    operation_jobs.progress("native3d_mapping", "Consultando o mapping do Marvel Rivals…", 0, 3)
    try:
        listing = json.loads(_download(MAPPING_INDEX, 1024 * 1024, check))
    except (ValueError, UnicodeError) as error:
        raise SupportError("A lista de mappings recebida é inválida.") from error
    if not isinstance(listing, list):
        raise SupportError("A lista de mappings recebida é inválida.")
    candidates = []
    for item in listing:
        if not isinstance(item, dict) or item.get("type") != "file":
            continue
        name = item.get("name", "")
        match = MAPPING_NAME.fullmatch(name) if isinstance(name, str) and len(name) <= 200 else None
        digest, size = item.get("sha", ""), item.get("size")
        if match and isinstance(digest, str) and _HEX160.fullmatch(digest) and type(size) is int and 16 <= size <= MAX_MAPPING:
            candidates.append((int(match[1]), name, digest, size))
    if not candidates:
        raise SupportError("A fonte de mappings não forneceu uma versão de lançamento compatível.")
    build, name, git_sha, size = max(candidates)
    operation_jobs.progress("native3d_mapping", "Baixando e verificando o mapping…", 0, 3)
    data = _download(MAPPING_BASE + urllib.parse.quote(name, safe=""), MAX_MAPPING, check)
    blob = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    if len(data) != size or hashlib.sha1(blob).hexdigest() != git_sha:
        raise SupportError("O mapping baixado não corresponde ao arquivo anunciado pela fonte.")
    _validate_mapping(data)
    digest = hashlib.sha256(data).hexdigest()
    _check(check)
    _store_file("mapping", data, digest)
    return {"name": name, "build": build, "sha256": digest, "git_blob_sha1": git_sha, "source": "SpaceDepot/rivals-depot"}


def _ensure_codec(kind, check):
    spec = CODECS[kind]
    record = {"version": spec["version"], "sha256": spec["sha256"],
              "source": spec.get("source", spec.get("url"))}
    try:
        _read_record(kind, record)
        return record
    except (OSError, SupportError):
        pass
    operation_jobs.progress("native3d_codecs", f"Baixando e verificando o codec {kind}…", 2, 3)
    archive = _download(spec["url"], spec["max_download"], check)
    if hashlib.sha256(archive).hexdigest() != spec["archive_sha256"]:
        raise SupportError("O download do codec não corresponde à versão verificada pelo Manager.")
    try:
        if spec["format"] == "raw":
            data = archive
        elif spec["format"] == "zip":
            with zipfile.ZipFile(io.BytesIO(archive)) as container:
                entries = [item for item in container.infolist() if item.filename == spec["entry"]]
                if len(entries) != 1 or entries[0].file_size > MAX_DLL:
                    raise SupportError("O pacote do codec não contém a biblioteca esperada.")
                with container.open(entries[0]) as stream:
                    data = _read_limited(stream, MAX_DLL, check)
        else:
            with gzip.GzipFile(fileobj=io.BytesIO(archive)) as stream:
                data = _read_limited(stream, MAX_DLL, check)
    except (OSError, zipfile.BadZipFile, EOFError) as error:
        raise SupportError("O pacote do codec está corrompido.") from error
    _check(check)
    _store_file(kind, data, spec["sha256"])
    return record


@contextlib.contextmanager
def _provision_guard(check):
    # Separate from current.json's storage guard; simultaneous Manager instances
    # must not publish older snapshots over a preparation that just completed.
    root = _safe_path(SUPPORT_DIR)
    root.mkdir(parents=True, exist_ok=True)
    while not _LOCK.acquire(timeout=0.1):
        _check(check)
    try:
        _check(check)
        path = _safe_path(root / "prepare.lock")
        with path.open("a+b") as stream:
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b"0")
                stream.flush()
            while True:
                _check(check)
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (BlockingIOError, PermissionError):
                    time.sleep(0.1)
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        _LOCK.release()


def ensure_support(settings=None, check=None, update=False):
    """Retorna mapping/Oodle/zlib locais; update explícito nunca perde o cache.

    settings é aceito por conveniência da API; nenhum caminho de programa
    externo é lido. check pode lançar o cancelamento do job chamador.
    """
    _check(check)
    with _provision_guard(check):
        current = None
        try:
            current = _load_current()
        except (OSError, ValueError, SupportError, TypeError):
            pass
        if current and not update:
            current_codecs = current[0]
            if all(current_codecs.get(kind, {}).get("sha256") == spec["sha256"]
                   for kind, spec in CODECS.items()):
                return current[1]
            # Migra o antigo Oodle 2.9.16 usando o mapping/zlib já validados;
            # a troca local não exige rede e só ativa o manifesto ao final.
            manifest = dict(current[0])
            for kind, spec in CODECS.items():
                if manifest.get(kind, {}).get("sha256") != spec["sha256"]:
                    manifest[kind] = _ensure_codec(kind, check)
            manifest["updated_at"] = time.time()
            paths = tuple(_read_record(kind, manifest[kind]) for kind in ("mapping", "oodle", "zlib"))
            _check(check)
            storage._save_json(str(_safe_path(Path(SUPPORT_DIR) / "current.json")), manifest)
            return paths
        try:
            mapping = _latest_mapping(check)
            if current and mapping["build"] < current[0]["mapping"].get("build", 0):
                raise SupportError("A fonte ofereceu um mapping mais antigo. A versão atual foi preservada.")
            codecs = {kind: _ensure_codec(kind, check) for kind in CODECS}
            manifest = {"schema": 1, "updated_at": time.time(), "mapping": mapping, **codecs}
            paths = tuple(_read_record(kind, manifest[kind]) for kind in ("mapping", "oodle", "zlib"))
            _check(check)
            destination = _safe_path(Path(SUPPORT_DIR) / "current.json")
            storage._save_json(str(destination), manifest)
            return paths
        except SupportError as error:
            if current:
                raise SupportError(f"{error} O suporte já instalado continua disponível.") from error
            raise
