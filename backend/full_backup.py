"""Backup opcional de arquivos, portátil e sem restaurar o jogo automaticamente.

O ZIP usa entradas sem compressão (ZIP64), tamanho previsível e SHA-256 por
arquivo. Preparação e execução são separadas por um token revisável. Nenhum
registro atual é alterado: a restauração extrai uma biblioteca desativada em
uma pasta nova, ao lado de um snapshot fiel do catálogo e das configurações.
"""
import copy
import hashlib
import json
import os
import pathlib
import secrets
import shutil
import stat
import threading
import time
import zipfile

from . import mod_ops, operation_jobs, storage


_PLANS = {}
_LOCK = threading.Lock()
_PLAN_SECONDS = 15 * 60
_CHUNK_SIZE = 2 * 1024 * 1024
_FORMAT = "marvel-manager-full-backup"
_MAX_MANIFEST = 64 * 1024 * 1024
_MAX_FILES = 200_000
_README = """# Backup de arquivos do CrabVault

Este pacote contém o catálogo, as configurações e os arquivos privados da
biblioteca, inclusive mídias e compactados preservados após remover um mod.
Arquivos cadastrados disponíveis somente no jogo foram incluídos quando
possível. Consulte `manifest.json`: `complete: false` e `warnings` indicam
conteúdo ausente. Backups incompletos não recuperam arquivos que já faltavam.

`mods.json` e `settings.json` formam uma cópia segura: todos os mods estão
desativados e o caminho do jogo está vazio. Os snapshots originais ficam em
`catalog/`. `mods_storage/` conserva a estrutura dos arquivos privados;
`backups/original_moviesbink/`, quando presente, conserva o MoviesBink original.
`manifest.json` registra tamanho e SHA-256 de cada arquivo para verificação.

Use a opção de restauração de backup completo do Manager: ela verifica todos
os hashes e extrai somente para uma nova pasta. Não instala arquivos no jogo,
não ativa mods e não substitui o catálogo nem as configurações em uso. Você
pode inspecionar essa pasta ou usá-la com uma cópia separada do Manager antes
de selecionar novamente o diretório do jogo. Também é possível extrair o ZIP
com uma ferramenta ZIP64 e revisar os arquivos manualmente.

O programa Manager, o jogo original, caches regeneráveis e outros backups não
fazem parte deste pacote. Arquivos .partial não são backups concluídos.
"""


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _stamp(info):
    common = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    return common if os.name == "nt" else (*common, info.st_ctime_ns)


def _plain_path(path, *, directory=False, missing=False):
    """Recusa links/junctions em qualquer ancestral antes de resolver o caminho."""
    candidate = pathlib.Path(os.path.abspath(os.fspath(path)))
    for item in (*reversed(candidate.parents), candidate):
        try:
            info = item.lstat()
        except FileNotFoundError:
            if missing:
                continue
            raise ValueError(f"O caminho não existe: {candidate}")
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"Links simbólicos/junctions não são permitidos no backup: {item}")
    if candidate.exists():
        info = candidate.stat()
        if directory and not stat.S_ISDIR(info.st_mode):
            raise ValueError("Escolha uma pasta de destino existente.")
        if not directory and not stat.S_ISREG(info.st_mode):
            raise ValueError(f"O caminho não é um arquivo regular: {candidate}")
    elif not missing:
        raise ValueError(f"O caminho não existe: {candidate}")
    return candidate


def _relative(value):
    raw = str(value or "").replace("\\", "/")
    parts = raw.split("/")
    if (not raw or pathlib.PureWindowsPath(raw).drive or raw.startswith("/")
            or any(part in {"", ".", ".."} or ":" in part or part.rstrip(" .") != part
                   or any(character in part for character in '<>"|?*\x00') for part in parts)):
        raise ValueError("O backup contém um caminho relativo inválido.")
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    if any(part.split(".")[0].casefold() in reserved for part in parts):
        raise ValueError("O backup contém um nome reservado pelo Windows.")
    return "/".join(parts)


def _within(path, root):
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(root)]) == os.path.abspath(root)
    except ValueError:
        return False


def _child(root, relative, *, missing=True):
    target = pathlib.Path(root).joinpath(*_relative(relative).split("/"))
    return _plain_path(target, missing=missing)


def _destination(directory, sources=()):
    target = _plain_path(directory, directory=True)
    protected = [pathlib.Path(storage.STORAGE_DIR), pathlib.Path(storage.BACKUPS_DIR) / "original_moviesbink", *sources]
    settings = storage.load_settings()
    if settings.get("mods_path"):
        protected.append(pathlib.Path(settings["mods_path"]))
        for mod in storage.load_mods():
            if mod.get("install_target"):
                try:
                    protected.append(pathlib.Path(mod_ops._game_target_dir(mod, settings["mods_path"])))
                except OSError:
                    pass
    for root in protected:
        if _within(target, root):
            raise ValueError("Escolha um destino fora da biblioteca privada e das pastas ativas do jogo.")
    return target


def _catalog():
    # Os métodos de storage fornecem snapshots independentes, sem acesso JSON
    # paralelo pela interface. A revalidação abaixo detecta mudanças entre eles.
    mods, settings = copy.deepcopy(list(storage.load_mods())), copy.deepcopy(dict(storage.load_settings()))
    if not all(isinstance(mod, dict) for mod in mods):
        raise ValueError("O catálogo contém um registro de mod inválido.")
    return mods, settings


def _corrections():
    loader = getattr(storage, "load_personal_corrections", None)
    return copy.deepcopy(loader()) if loader else None


def _fingerprint(mods, settings):
    return hashlib.sha256(_json_bytes({"mods": mods, "settings": settings})).hexdigest()


def _source(path, archive_name):
    path = _plain_path(path)
    info = path.stat()
    return {"source": str(path), "name": _relative(archive_name), "stamp": _stamp(info), "size": info.st_size}


def _walk(root, prefix, *, check_cancel=True):
    root = _plain_path(root, directory=True)
    result = []

    def failed(error):
        raise error

    for directory, dirs, files in os.walk(root, followlinks=False, onerror=failed):
        if check_cancel:
            operation_jobs.check()
        dirs.sort(key=str.casefold)
        files.sort(key=str.casefold)
        for name in dirs:
            _plain_path(pathlib.Path(directory) / name, directory=True)
        for name in files:
            target = pathlib.Path(directory) / name
            result.append(_source(target, prefix + "/" + target.relative_to(root).as_posix()))
            if len(result) > _MAX_FILES:
                raise ValueError(f"A biblioteca excede o limite de {_MAX_FILES} arquivos por backup.")
            if check_cancel:
                operation_jobs.progress("estimating", "Calculando o tamanho da biblioteca…", len(result), 0)
    return result


def _collect(mods, settings, corrections=None):
    entries = _walk(storage.STORAGE_DIR, "mods_storage")
    sources = {item["name"].casefold(): item for item in entries}
    if len(sources) != len(entries):
        raise ValueError("Há nomes de arquivos que diferem apenas em maiúsculas/minúsculas na biblioteca.")
    warnings, missing = [], []
    portable_mods = copy.deepcopy(mods)
    for mod, portable in zip(mods, portable_mods):
        mod_name = mod.get("name") or mod.get("id") or "Mod"
        folder = _relative(mod_ops._storage_relative(mod))
        root = pathlib.Path(storage.STORAGE_DIR).joinpath(*folder.split("/"))
        # Mesmo pastas privadas ausentes precisam ter ancestrais confiáveis.
        _plain_path(root, directory=True, missing=True)
        portable["storage_folder"] = folder
        portable["enabled"] = False
        portable["external"] = False
        if mod.get("folder"):
            _relative(mod["folder"])
        for component in portable.get("components") or []:
            component["enabled"] = False
        active = None
        fallback_count = 0
        for entry in mod_ops._all_library_file_entries(mod):
            name = _relative(entry["name"])
            archive_name = "mods_storage/" + folder + "/" + name
            if archive_name.casefold() in sources:
                continue
            candidate = None
            if settings.get("mods_path"):
                try:
                    if active is None:
                        active = pathlib.Path(mod_ops._game_target_dir(mod, settings["mods_path"]))
                        _plain_path(active, directory=True, missing=True)
                    candidate = _child(active, name)
                except OSError:
                    candidate = None
            if candidate and candidate.exists():
                item = _source(candidate, archive_name)
                sources[archive_name.casefold()] = item
                entries.append(item)
                fallback_count += 1
            else:
                missing.append({"mod": mod_name, "name": name, "kind": "package"})
                warnings.append(f"{mod_name}: arquivo ausente no privado e no jogo: {name}.")
        references = [*(mod.get("images") or []), *(mod.get("archives") or [])]
        if mod.get("image"):
            references.append(mod["image"])
        for name in dict.fromkeys(references):
            archive_name = "mods_storage/" + folder + "/" + _relative(name)
            if archive_name.casefold() not in sources:
                missing.append({"mod": mod_name, "name": str(name), "kind": "media_or_archive"})
                warnings.append(f"{mod_name}: mídia/compactado ausente: {name}.")
        if fallback_count:
            warnings.append(f"{mod_name}: {fallback_count} arquivo(s) incluído(s) a partir da cópia ativa do jogo; não havia cópia privada.")
    original_movies = pathlib.Path(storage.BACKUPS_DIR) / "original_moviesbink"
    if os.path.lexists(original_movies):
        entries.extend(_walk(original_movies, "backups/original_moviesbink"))
    if len(entries) > _MAX_FILES:
        raise ValueError(f"A biblioteca excede o limite de {_MAX_FILES} arquivos por backup.")
    portable_settings = copy.deepcopy(settings)
    portable_settings.update(mods_path="", bypass_game_running_lock=False,
                             pending_background_audio_changes=[], last_recovery_snapshot=None)
    generated = {"catalog/mods.json": _json_bytes(mods), "catalog/settings.json": _json_bytes(settings),
                 "mods.json": _json_bytes(portable_mods), "settings.json": _json_bytes(portable_settings),
                 "RESTAURACAO.md": _README.encode("utf-8")}
    if corrections is not None:
        generated["personal_corrections.json"] = _json_bytes(corrections)
    return sorted(entries, key=lambda item: item["name"].casefold()), generated, warnings, missing


def _keep_plan(plan):
    token = secrets.token_hex(20)
    with _LOCK:
        now = time.monotonic()
        for key, previous in list(_PLANS.items()):
            if now - previous["created"] > _PLAN_SECONDS:
                _PLANS.pop(key, None)
        if len(_PLANS) >= 20:
            _PLANS.pop(next(iter(_PLANS)))
        plan["created"] = now
        _PLANS[token] = plan
    return token


def _take_plan(token, kind):
    with _LOCK:
        plan = _PLANS.pop(str(token), None)
    if not plan or plan["kind"] != kind or time.monotonic() - plan["created"] > _PLAN_SECONDS:
        raise ValueError("Esta prévia expirou ou já foi usada. Gere uma nova prévia.")
    return plan


def _required_bytes(entries, generated):
    # ZIP_STORED não aumenta os dados. Reservamos os dois cabeçalhos ZIP64 por
    # entrada, nomes UTF-8 e manifesto JSON com hashes, mais margem de 1 MiB.
    total = sum(item["size"] for item in entries) + sum(map(len, generated.values()))
    overhead = sum(1024 + len(item["name"].encode("utf-8")) * 4 for item in entries)
    return total, total + overhead + 1024 * 1024


def preview_backup(destination_dir):
    """Estima por metadados; não lê todos os bytes nem cria o ZIP."""
    try:
        destination = _destination(destination_dir)
        mods, settings = _catalog()
        corrections = _corrections()
        entries, generated, warnings, missing = _collect(mods, settings, corrections)
        if _fingerprint(*_catalog()) != _fingerprint(mods, settings) or _corrections() != corrections:
            raise ValueError("A biblioteca mudou durante a estimativa. Tente novamente.")
        total, required = _required_bytes(entries, generated)
        available = shutil.disk_usage(destination).free
        filename = "marvel-manager-completo-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3) + ".zip"
        plan = {"kind": "export", "destination": str(destination), "filename": filename,
                "entries": entries, "generated": generated, "fingerprint": _fingerprint(mods, settings),
                "required_bytes": required, "total_bytes": total, "mods": len(mods),
                "warnings": warnings, "missing": missing, "corrections": corrections}
        token = _keep_plan(plan)
        return {"ok": True, "token": token, "file_count": len(entries), "mods": len(mods),
                "total_bytes": total, "required_bytes": required, "available_bytes": available,
                "can_create": available >= required, "complete": not missing, "warnings": warnings,
                "destination": str(destination), "filename": filename}
    except operation_jobs.OperationCancelled:
        raise
    except (OSError, ValueError, TypeError, KeyError) as error:
        return {"ok": False, "error": str(error)}


def _revalidate_export(plan):
    mods, settings = _catalog()
    if _fingerprint(mods, settings) != plan["fingerprint"]:
        raise ValueError("O catálogo ou as configurações mudaram. Gere uma nova prévia do backup.")
    corrections = _corrections()
    if corrections != plan["corrections"]:
        raise ValueError("As correções pessoais mudaram. Gere uma nova prévia do backup.")
    entries, generated, warnings, missing = _collect(mods, settings, corrections)
    if entries != plan["entries"] or generated != plan["generated"] or warnings != plan["warnings"] or missing != plan["missing"]:
        raise ValueError("Os arquivos da biblioteca mudaram. Gere uma nova prévia do backup.")


def _safe_unlink_owned(path, parent, identity):
    # Somente o arquivo criado por esta operação pode ser descartado.
    try:
        candidate = _plain_path(path)
        if candidate.parent != parent or (candidate.stat().st_dev, candidate.stat().st_ino) != identity:
            raise OSError("O arquivo temporário mudou; ele não foi removido automaticamente.")
        candidate.unlink()
    except FileNotFoundError:
        pass


def _publish_directory(staged, final):
    """Reserva a pasta final exclusivamente, sem substituir uma pasta vazia."""
    final.mkdir(exist_ok=False)
    info = final.stat()
    identity = info.st_dev, info.st_ino
    try:
        # O manifesto é o marcador de conclusão e sempre chega por último.
        children = sorted(staged.iterdir(), key=lambda item: item.name == "manifest.json")
        for child in children:
            _plain_path(final, directory=True)
            os.rename(child, final / child.name)
        staged.rmdir()
    except BaseException:
        _remove_owned_tree(final, final.parent, identity)
        raise


def create_backup(token, allow_incomplete=False):
    """Escreve o ZIP em blocos. Use dentro de operation_jobs.start para progresso."""
    partial = None
    identity = None
    try:
        plan = _take_plan(token, "export")
        if plan["missing"] and allow_incomplete is not True:
            raise ValueError("Há arquivos ausentes. Confirme explicitamente o backup incompleto ou corrija a biblioteca.")
        destination = _destination(plan["destination"])
        final = destination / plan["filename"]
        if final.exists():
            raise ValueError("O arquivo de destino já existe. Gere uma nova prévia.")
        if shutil.disk_usage(destination).free < plan["required_bytes"]:
            raise ValueError("Não há espaço livre suficiente no destino para este backup.")
        _revalidate_export(plan)
        operation_jobs.check()
        partial = destination / ("." + plan["filename"] + "." + secrets.token_hex(8) + ".partial")
        output = open(partial, "xb")
        info = os.fstat(output.fileno())
        identity = info.st_dev, info.st_ino
        done, manifest_entries = 0, []
        with output:
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                for entry in plan["entries"]:
                    operation_jobs.check()
                    source = _plain_path(entry["source"])
                    if _stamp(source.stat()) != entry["stamp"]:
                        raise ValueError("Um arquivo mudou desde a estimativa. Gere uma nova prévia.")
                    digest = hashlib.sha256()
                    with open(source, "rb") as incoming, archive.open(entry["name"], "w", force_zip64=True) as outgoing:
                        if _stamp(os.fstat(incoming.fileno())) != entry["stamp"]:
                            raise ValueError("Um arquivo mudou ao iniciar a cópia.")
                        while True:
                            operation_jobs.check()
                            chunk = incoming.read(_CHUNK_SIZE)
                            if not chunk:
                                break
                            outgoing.write(chunk)
                            digest.update(chunk)
                            done += len(chunk)
                            operation_jobs.progress("backup", f"Salvando {entry['name']}", done, plan["total_bytes"], "bytes")
                        if _stamp(os.fstat(incoming.fileno())) != entry["stamp"]:
                            raise ValueError("Um arquivo foi alterado durante o backup.")
                    if _stamp(source.stat()) != entry["stamp"]:
                        raise ValueError("Um arquivo foi alterado durante o backup.")
                    manifest_entries.append({"name": entry["name"], "size": entry["size"], "sha256": digest.hexdigest()})
                for name, data in plan["generated"].items():
                    operation_jobs.check()
                    with archive.open(name, "w", force_zip64=True) as outgoing:
                        for offset in range(0, len(data), _CHUNK_SIZE):
                            operation_jobs.check()
                            chunk = data[offset:offset + _CHUNK_SIZE]
                            outgoing.write(chunk)
                            done += len(chunk)
                            operation_jobs.progress("backup", f"Salvando {name}", done, plan["total_bytes"], "bytes")
                    manifest_entries.append({"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
                manifest = {"format": _FORMAT, "format_version": 1, "exported_at": storage.now_iso(),
                            "complete": not plan["missing"], "mods": plan["mods"], "warnings": plan["warnings"],
                            "missing": plan["missing"], "files": manifest_entries}
                manifest_data = _json_bytes(manifest)
                if len(manifest_data) > _MAX_MANIFEST:
                    raise ValueError("O manifesto excede o limite deste formato de backup.")
                archive.writestr("manifest.json", manifest_data)
            output.flush()
            os.fsync(output.fileno())
        # Uma alteração concorrente nunca transforma o snapshot em "concluído".
        _revalidate_export(plan)
        operation_jobs.begin_commit("Concluindo o arquivo de backup…")
        _plain_path(destination, directory=True)
        try:
            os.link(partial, final)
        except OSError as error:
            if os.name != "nt" or final.exists():
                raise
            # rename no Windows falha se já existir; não usa replace.
            os.rename(partial, final)
            partial = None
        if partial is not None:
            _safe_unlink_owned(partial, destination, identity)
            partial = None
        return {"ok": True, "path": str(final), "complete": not plan["missing"],
                "warnings": plan["warnings"], "file_count": len(plan["entries"]), "total_bytes": final.stat().st_size,
                "mods": plan["mods"]}
    except operation_jobs.OperationCancelled:
        raise
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as error:
        return {"ok": False, "error": str(error)}
    finally:
        if partial is not None and identity is not None:
            _safe_unlink_owned(partial, destination, identity)


def _read_manifest(source):
    with zipfile.ZipFile(source, "r") as archive:
        infos = archive.infolist()
        if len(infos) > _MAX_FILES + 10:
            raise ValueError("O backup contém arquivos demais.")
        names = [info.filename for info in infos]
        name_set = set(names)
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError("O backup contém nomes de arquivo duplicados.")
        for info in infos:
            if _relative(info.filename) != info.filename or info.is_dir():
                raise ValueError("O backup contém um caminho inválido.")
            if info.compress_type != zipfile.ZIP_STORED or info.flag_bits & 1 or info.compress_size != info.file_size:
                raise ValueError("Formato de entrada não reconhecido neste backup.")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ValueError("O backup contém links simbólicos.")
        if "manifest.json" not in names or archive.getinfo("manifest.json").file_size > _MAX_MANIFEST:
            raise ValueError("Manifesto ausente ou grande demais.")
        manifest = json.loads(archive.read("manifest.json"))
        if not isinstance(manifest, dict) or manifest.get("format") != _FORMAT or manifest.get("format_version") != 1:
            raise ValueError("Este arquivo não é um backup completo de arquivos do CrabVault.")
        if (type(manifest.get("complete")) is not bool or not isinstance(manifest.get("missing"), list)
                or manifest["complete"] != (not manifest["missing"])
                or not isinstance(manifest.get("warnings"), list)
                or not all(isinstance(warning, str) for warning in manifest["warnings"])):
            raise ValueError("Os avisos de integridade do manifesto têm um formato inválido.")
        files = manifest.get("files")
        if not isinstance(files, list) or len(files) != len(names) - 1:
            raise ValueError("O manifesto não corresponde aos arquivos do backup.")
        listed = set()
        for entry in files:
            if not isinstance(entry, dict):
                raise ValueError("Entrada inválida no manifesto.")
            if not isinstance(entry.get("name"), str):
                raise ValueError("Nome inválido no manifesto.")
            name = _relative(entry.get("name"))
            sha = entry.get("sha256")
            if (name in listed or name not in name_set or name == "manifest.json"
                    or entry["name"] != name or type(entry.get("size")) is not int or entry["size"] < 0
                    or archive.getinfo(name).file_size != entry["size"]
                    or not isinstance(sha, str) or len(sha) != 64 or any(char not in "0123456789abcdef" for char in sha)):
                raise ValueError("Tamanho, nome ou hash inválido no manifesto.")
            listed.add(name)
        expected = {"mods.json", "settings.json", "catalog/mods.json", "catalog/settings.json", "RESTAURACAO.md"}
        if not expected <= listed:
            raise ValueError("O backup não contém os snapshots da biblioteca.")
        for name in listed:
            if name not in expected | {"personal_corrections.json"} and not name.startswith(("mods_storage/", "backups/original_moviesbink/")):
                raise ValueError("O backup contém um arquivo fora das pastas permitidas.")
        return manifest


def _allocation_unit(destination):
    """Considera o espaço ocupado por muitos arquivos pequenos na restauração."""
    if os.name == "nt":
        import ctypes
        sectors = ctypes.c_ulong()
        bytes_per_sector = ctypes.c_ulong()
        free_clusters = ctypes.c_ulong()
        total_clusters = ctypes.c_ulong()
        root = ctypes.create_unicode_buffer(32768)
        if (ctypes.windll.kernel32.GetVolumePathNameW(str(destination), root, len(root))
                and ctypes.windll.kernel32.GetDiskFreeSpaceW(root, ctypes.byref(sectors),
                    ctypes.byref(bytes_per_sector), ctypes.byref(free_clusters), ctypes.byref(total_clusters))):
            return max(4096, sectors.value * bytes_per_sector.value)
    elif hasattr(os, "statvfs"):
        return max(4096, os.statvfs(destination).f_frsize)
    return 4096


def _restore_required_bytes(manifest, destination):
    unit = _allocation_unit(destination)
    directories = set()
    required = 1024 * 1024 + len(_json_bytes(manifest))
    for entry in manifest["files"]:
        required += ((entry["size"] + unit - 1) // unit) * unit
        directories.update(str(parent) for parent in pathlib.PurePosixPath(entry["name"]).parents)
    return required + len(directories) * unit


def preview_restore(source_zip, destination_dir):
    """Revê a extração para uma nova pasta; não muda a biblioteca em uso."""
    try:
        source = _plain_path(source_zip)
        destination = _destination(destination_dir)
        before = _stamp(source.stat())
        manifest = _read_manifest(source)
        if _stamp(source.stat()) != before:
            raise ValueError("O backup mudou durante a leitura.")
        required = _restore_required_bytes(manifest, destination)
        available = shutil.disk_usage(destination).free
        folder = "biblioteca-restaurada-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
        plan = {"kind": "restore", "source": str(source), "stamp": before, "manifest": manifest,
                "destination": str(destination), "folder": folder, "required_bytes": required}
        token = _keep_plan(plan)
        return {"ok": True, "token": token, "destination": str(destination / folder),
                "file_count": len(manifest["files"]), "required_bytes": required, "available_bytes": available,
                "can_restore": available >= required, "complete": bool(manifest.get("complete")),
                "mods": manifest.get("mods", 0), "warnings": manifest.get("warnings", []),
                "note": "Será criada uma pasta nova com a biblioteca desativada. O catálogo atual e os arquivos do jogo não serão alterados."}
    except operation_jobs.OperationCancelled:
        raise
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as error:
        return {"ok": False, "error": str(error)}


def _remove_owned_tree(path, parent, identity):
    root = _plain_path(path, directory=True)
    if root.parent != parent or (root.stat().st_dev, root.stat().st_ino) != identity:
        raise OSError("A pasta temporária mudou; ela não foi removida automaticamente.")
    # Verifica todos os caminhos antes de excluir: junctions nunca são seguidas.
    _walk(root, "validation", check_cancel=False)
    shutil.rmtree(root)


def restore_backup(token):
    """Verifica SHA-256 enquanto extrai, sem gravar na biblioteca/jogo atuais."""
    target = None
    identity = None
    try:
        plan = _take_plan(token, "restore")
        destination = _destination(plan["destination"])
        source = _plain_path(plan["source"])
        if _stamp(source.stat()) != plan["stamp"] or _read_manifest(source) != plan["manifest"]:
            raise ValueError("O backup mudou desde a prévia. Selecione-o novamente.")
        if shutil.disk_usage(destination).free < plan["required_bytes"]:
            raise ValueError("Não há espaço livre suficiente para restaurar esta cópia.")
        operation_jobs.check()
        final = destination / plan["folder"]
        if final.exists():
            raise ValueError("A pasta de destino já existe. Gere uma nova prévia.")
        target = destination / ("." + plan["folder"] + "." + secrets.token_hex(8) + ".partial")
        target.mkdir(exist_ok=False)
        info = target.stat()
        identity = info.st_dev, info.st_ino
        done = 0
        total = sum(entry["size"] for entry in plan["manifest"]["files"])
        with zipfile.ZipFile(source, "r") as archive:
            for entry in plan["manifest"]["files"]:
                operation_jobs.check()
                path = _child(target, entry["name"])
                path.parent.mkdir(parents=True, exist_ok=True)
                _plain_path(path.parent, directory=True)
                digest = hashlib.sha256()
                count = 0
                with archive.open(entry["name"]) as incoming, open(path, "xb") as outgoing:
                    while True:
                        operation_jobs.check()
                        chunk = incoming.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > entry["size"]:
                            raise ValueError("O conteúdo excede o tamanho registrado no manifesto.")
                        outgoing.write(chunk)
                        digest.update(chunk)
                        done += len(chunk)
                        operation_jobs.progress("restore_backup", f"Verificando e extraindo {entry['name']}", done, total, "bytes")
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                if count != entry["size"] or digest.hexdigest() != entry["sha256"]:
                    raise ValueError(f"O arquivo não corresponde ao hash do backup: {entry['name']}")
        if _stamp(source.stat()) != plan["stamp"]:
            raise ValueError("O backup mudou durante a restauração.")
        # Não confiamos no conteúdo de settings.json de um ZIP arbitrário.
        # Exige o snapshot seguro produzido pelo exportador, sem reescrever
        # JSONs e invalidar os hashes originais depois da extração.
        with open(target / "mods.json", encoding="utf-8") as stream:
            mods = json.load(stream)
        with open(target / "settings.json", encoding="utf-8") as stream:
            settings = json.load(stream)
        if not isinstance(mods, list) or not all(isinstance(mod, dict) for mod in mods) or not isinstance(settings, dict):
            raise ValueError("O catálogo restaurado tem um formato inválido.")
        for mod in mods:
            _relative(mod_ops._storage_relative(mod))
            if mod.get("folder"):
                _relative(mod["folder"])
            for entry in mod_ops._all_library_file_entries(mod):
                _relative(entry["name"])
            for name in [*(mod.get("images") or []), *(mod.get("archives") or []), *([mod["image"]] if mod.get("image") else [])]:
                _relative(name)
            if mod.get("enabled") is not False:
                raise ValueError("O catálogo deste backup não está desativado com segurança.")
            for component in mod.get("components") or []:
                if component.get("enabled") is not False:
                    raise ValueError("O catálogo deste backup contém componentes ativos.")
        if (settings.get("mods_path") != "" or settings.get("bypass_game_running_lock") is not False
                or settings.get("pending_background_audio_changes") != [] or settings.get("last_recovery_snapshot") is not None):
            raise ValueError("As configurações deste backup permitem alterações no jogo e não podem ser restauradas como cópia segura.")
        operation_jobs.begin_commit("Concluindo a biblioteca restaurada…")
        with open(target / "manifest.json", "xb") as stream:
            stream.write(_json_bytes(plan["manifest"]))
        _plain_path(destination, directory=True)
        _publish_directory(target, final)
        result = {"ok": True, "path": str(final), "complete": bool(plan["manifest"].get("complete")),
                  "warnings": plan["manifest"].get("warnings", []), "mods": len(mods),
                  "file_count": len(plan["manifest"]["files"]),
                  "note": "Cópia extraída e verificada. Nenhum mod foi ativado e a biblioteca em uso não foi substituída."}
        target = None
        return result
    except operation_jobs.OperationCancelled:
        raise
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as error:
        return {"ok": False, "error": str(error)}
    finally:
        if target is not None and identity is not None:
            _remove_owned_tree(target, destination, identity)
