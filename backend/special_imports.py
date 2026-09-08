"""Importadores especiais: preparo cancelável e aplicação com reversão durável.

O journal guarda somente os destinos desta importação. O backup original de
MoviesBink continua completo, mas é criado uma única vez, fora do jogo, e só
é publicado quando a cópia terminou. Nunca se copia a árvore inteira do jogo.
"""
import os
import pathlib
import re
import shutil
import subprocess

from . import operation_jobs, operation_recovery, storage


def _ops():
    from . import mod_ops
    return mod_ops


def _signature(path):
    stat = os.stat(path)
    return (stat.st_size, stat.st_mtime_ns, stat.st_ino)


def _digest(path):
    return operation_jobs.hash_file(path)


def _relative(value, background=False):
    ops = _ops()
    relative = (ops._background_relative_file_path(value) if background
                else ops._safe_relative_file_path(value))
    path = pathlib.PureWindowsPath(relative)
    if path.drive or path.root or any(
        not part or part.endswith((" ", ".")) or re.search(r'[<>:"|?*\x00-\x1f]', part)
        for part in path.parts
    ):
        raise ValueError("O pacote contém um caminho de arquivo inválido.")
    return relative


def _copy(source, destination, total=0):
    if not os.path.isfile(source):
        raise ValueError(f"O arquivo selecionado não está mais disponível: {os.path.basename(source)}")
    before = _signature(source)
    expected = _digest(source)
    operation_jobs.copy_file(source, destination, total=total or before[0], expected_hash=expected)
    if before != _signature(source):
        raise ValueError("Um arquivo mudou durante a cópia. Selecione o pacote novamente.")
    return {"size": before[0], "sha256": expected}


def _unique_name(relative, used):
    parent, name = os.path.split(relative)
    result, index = relative, 1
    while os.path.normcase(result) in used:
        index += 1
        result = os.path.join(parent, str(index), name)
    used.add(os.path.normcase(result))
    return result


def _copy_extras(meta, stage, used, source_paks=()):
    ops = _ops()
    archives, source_names = [], {}
    for index, source in enumerate([*source_paks, *(meta.get("archive_paths") or [])], 1):
        operation_jobs.check()
        name = ops._safe_storage_segment(os.path.basename(source), "source.archive")
        relative = _unique_name(os.path.join("Archive", str(index), name), used)
        destination = operation_recovery._inside(os.path.join(stage, relative), stage)
        _copy(source, destination)
        archives.append(relative)
        source_names[os.path.normcase(source)] = relative
    images = []
    for index, source in enumerate(meta.get("image_paths") or [], 1):
        name = ops._safe_storage_segment(os.path.basename(source), "image.png")
        relative = _unique_name(f"image_{index}_{name}", used)
        _copy(source, operation_recovery._inside(os.path.join(stage, relative), stage))
        images.append(relative)
    return archives, images, source_names


def _run_tool(command):
    operation_jobs.check()
    job = operation_jobs.current()
    if job:
        return job.run(command, timeout=120)
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _prepare_audio(filepaths, stage, journal, meta, used):
    ops = _ops()
    pak_files = [source for source in filepaths if str(source).lower().endswith(".pak")]
    if not pak_files:
        raise ValueError("Não encontrei um arquivo .pak de áudio.")
    if not os.path.isfile(ops._UASSET_TOOL):
        raise ValueError("UAssetTool não está disponível para separar o áudio.")
    # Extraia a cópia privada verificada; uma origem alterada não pode misturar
    # bancos de uma versão com o PAK de outra versão guardado na biblioteca.
    archives, images, source_names = _copy_extras(meta, stage, used, pak_files)
    files, components = [], []
    for pak_index, source_pak in enumerate(pak_files, 1):
        operation_jobs.progress("extracting", f"Lendo áudio {pak_index}/{len(pak_files)}…", pak_index - 1, len(pak_files))
        extract_dir = os.path.join(journal.stage_dir("extracted"), "audio", str(pak_index))
        os.makedirs(extract_dir, exist_ok=True)
        archived = source_names[os.path.normcase(source_pak)]
        result = _run_tool([ops._UASSET_TOOL, "extract_pak", os.path.join(stage, archived), extract_dir])
        if result.returncode:
            raise ValueError(f"Não foi possível ler {os.path.basename(source_pak)}.")
        banks = sorted(pathlib.Path(extract_dir).rglob("*.bnk"), key=lambda path: str(path).casefold())
        source_label = re.sub(r"_9999999_P$", "", pathlib.Path(source_pak).stem, flags=re.IGNORECASE)
        for bank_index, bank in enumerate(banks, 1):
            operation_recovery._inside(str(bank), extract_dir)
            operation_jobs.progress("analyzing", f"Separando banco {bank_index}/{len(banks)}: {bank.name}", bank_index - 1, len(banks))
            metadata = ops._background_audio_metadata(bank.name)
            bank_stem = ops._safe_storage_segment(bank.stem, "Audio")
            relative = _unique_name(os.path.join("Audio Components", f"{pak_index:02d}_{bank_index:03d}_{bank_stem}_9999999_P.pak"), used)
            output = operation_recovery._inside(os.path.join(stage, relative), stage)
            os.makedirs(os.path.dirname(output), exist_ok=True)
            result = _run_tool([ops._UASSET_TOOL, "create_pak", output, str(bank)])
            if result.returncode or not os.path.isfile(output):
                raise ValueError(f"Não foi possível separar o banco {bank.name}.")
            entry = {"name": relative, "size": os.path.getsize(output), "sha256": _digest(output)}
            files.append(entry)
            components.append({"id": storage.new_id(), "name": f"{source_label} · {metadata['title']}",
                               "files": [entry], "enabled": False, "source_archive": os.path.relpath(archived, "Archive"),
                               "audio_bank": bank.name, **metadata})
    if not components:
        raise ValueError("O PAK não contém bancos de áudio Wwise (.bnk).")
    return files, components, archives, images


def _tree_files(root):
    """Sem links: um MoviesBink redirecionado não vira backup do jogo por engano."""
    operation_jobs.check()
    if os.path.islink(root):
        raise ValueError("MoviesBink não pode ser um link para outro diretório.")
    result = {}
    for directory, directories, files in os.walk(root):
        operation_jobs.check()
        for name in [*directories, *files]:
            path = os.path.join(directory, name)
            operation_recovery._inside(path, root)
            if os.path.islink(path):
                raise ValueError("MoviesBink contém um link; o backup original foi preservado sem alterações.")
        for name in files:
            path = os.path.join(directory, name)
            result[os.path.relpath(path, root)] = _signature(path)
    return result


def _prepare_movies_backup(record, mods_path, journal, mods):
    ops = _ops()
    if not record["enabled"] or record["install_target"] != "marvel_content":
        return None
    backup = ops._movies_backup_dir()
    if os.path.isdir(backup):
        if os.path.islink(backup):
            raise ValueError("O backup original de MoviesBink não pode ser um link.")
        return None
    if os.path.lexists(backup):
        raise ValueError("O destino do backup original MoviesBink está ocupado.")
    if any(mod.get("install_target") == "marvel_content" and mod.get("enabled") for mod in mods):
        raise ValueError("O backup original MoviesBink está ausente e há Backgrounds ativos. Restaure o backup original antes de importar outro perfil-base.")
    content = ops._game_target_dir(record, mods_path)
    source = os.path.join(content, "MoviesBink")
    if not os.path.isdir(source):
        raise ValueError("A pasta original MoviesBink não foi encontrada.")
    original = _tree_files(source)
    destination = os.path.join(journal.stage_dir("extracted"), "original_moviesbink")
    os.makedirs(destination, exist_ok=True)
    total = sum(signature[0] for signature in original.values())
    for index, relative in enumerate(original):
        operation_jobs.progress("backup", f"Preservando MoviesBink original: {index + 1}/{len(original)}", index, len(original))
        _copy(os.path.join(source, relative), os.path.join(destination, relative), total)
    if _tree_files(source) != original:
        raise ValueError("MoviesBink mudou durante o preparo do backup. Tente novamente com o jogo fechado.")
    return {"source": source, "stage": destination, "destination": backup, "signature": original}


def _active_context(mods, targets, mods_path, excluded=()):
    ops = _ops()
    target_keys = {os.path.normcase(os.path.realpath(path)) for path, _ in targets}
    context = []
    for mod in mods:
        if (str(mod.get("id")) in excluded or not mod.get("enabled")
                or mod.get("install_target") not in {"marvel_content", "binaries_win64"}):
            continue
        try:
            root = ops._game_target_dir(mod, mods_path)
        except OSError:
            continue
        active = {entry.get("name") for component in mod.get("components", []) if component.get("enabled", True)
                  for entry in component.get("files", [])}
        relevant = []
        for entry in ops._all_mod_file_entries(mod):
            if mod.get("components") and entry.get("name") not in active:
                continue
            name = _relative(entry["name"], mod.get("install_target") == "marvel_content")
            path = operation_recovery._inside(os.path.join(root, name), root)
            if os.path.normcase(path) in target_keys:
                relevant.append(name)
        if relevant:
            context.append({"id": str(mod["id"]), "files": sorted(relevant)})
    return sorted(context, key=lambda item: item["id"])


def validate_recovery(journal):
    """Impede restaurar por cima de outra camada aplicada após a interrupção."""
    guard = journal.data.get("special_guard")
    if not guard or not journal.data.get("mutation_started"):
        return
    temporary = {os.path.normcase(path) for path, _ in temporary_targets(journal)}
    targets = [(item["path"], item["root"]) for item in journal.data.get("files", [])
               if os.path.normcase(item["path"]) not in temporary]
    target_keys = {os.path.normcase(os.path.realpath(path)) for path, _ in targets}
    guard_keys = {os.path.normcase(os.path.realpath(item["path"])) for item in guard["targets"]}
    if guard_keys != target_keys:
        raise ValueError("A verificação da importação contém destinos inconsistentes.")
    after_ids = {str(item["id"]) for item in journal.data.get("after_records", [])}
    current = _active_context(storage.load_mods(), targets, journal.data["mods_path"], after_ids)
    if current != guard["context"]:
        raise ValueError("Outra camada usa os arquivos desta importação. Desfaça essa alteração antes de recuperar a operação.")
    for item in guard["targets"]:
        path = item["path"]
        if os.path.islink(path) or os.path.isdir(path):
            raise ValueError("Um destino da importação mudou de tipo; a recuperação foi interrompida.")
        actual = _digest(path) if os.path.isfile(path) else None
        if actual not in (item["before"], item["after"]):
            raise ValueError("Um arquivo foi alterado após a importação interrompida. A recuperação não substituirá essa alteração.")


def temporary_targets(journal):
    """Nomes derivados do ID e dos destinos, sem aceitar caminhos do JSON."""
    if not journal.data.get("special_atomic"):
        return []
    ops = _ops()
    result = []
    for record in journal.data.get("after_records", []):
        if not record.get("enabled"):
            continue
        root = ops._game_target_dir(record, journal.data.get("mods_path", ""))
        active = _enabled_entries(record)
        for index, entry in enumerate(active):
            path = operation_recovery._inside(os.path.join(root, _relative(entry["name"], record.get("install_target") == "marvel_content")), root)
            result.append((os.path.join(os.path.dirname(path), f".mm-import-{journal.id}-{index}.tmp"), root))
    return result


def _enabled_entries(record):
    active = {entry["name"] for component in record.get("components", []) if component.get("enabled", True)
              for entry in component.get("files", [])}
    return [entry for entry in record["files"] if not record.get("components") or entry["name"] in active]


def _publish_file(source, destination, temporary):
    """O destino só muda após a cópia completa, inclusive entre discos."""
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    try:
        os.link(source, temporary)
    except FileExistsError:
        raise ValueError("Um arquivo temporário da instalação foi ocupado.")
    except OSError:
        with open(source, "rb") as incoming, open(temporary, "xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, 2 * 1024 * 1024)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        shutil.copystat(source, temporary)
    os.replace(temporary, destination)


def _parent_exists(meta, mods):
    parent_id = str(meta.get("parent_background_id") or "").strip()
    if parent_id and not any(str(mod.get("id")) == parent_id and mod.get("install_target") == "marvel_content"
                             for mod in mods):
        raise ValueError("O Background de destino não foi encontrado.")
    return parent_id


def _install(filepaths, meta, kind, journal, settings):
    ops = _ops()
    mods_path = settings.get("mods_path", "")
    mods = storage.load_mods()
    parent = _parent_exists(meta, mods)
    if kind == "background_audio" and not parent:
        raise ValueError("Escolha primeiro o Background que receberá este áudio.")
    mod_id = storage.new_id()
    name = str(meta.get("name") or pathlib.Path(filepaths[0]).stem).strip()
    folder = os.path.join("Generic", "ReShade") if kind == "reshade" else "Backgrounds"
    storage_folder = os.path.join(folder, f"{ops._safe_storage_segment(name, 'Mod')} [{mod_id}]")
    final_dir = operation_recovery._inside(os.path.join(storage.STORAGE_DIR, storage_folder), storage.STORAGE_DIR)
    journal.own_storage_dir(final_dir)
    stage = journal.stage_dir("payload")
    journal.mark("copying")
    used = set()
    if kind == "background_audio":
        files, components, archives, images = _prepare_audio(filepaths, stage, journal, meta, used)
    else:
        files = []
        relative_paths = meta.get("relative_paths") or {}
        for source in filepaths:
            relative = _relative(relative_paths.get(os.path.normcase(source), os.path.basename(source)), kind == "background")
            key = os.path.normcase(relative)
            if key in used:
                raise ValueError(f"Mais de um arquivo da seleção usa o destino {relative}. Importe essas versões separadamente.")
            used.add(key)
            destination = operation_recovery._inside(os.path.join(stage, relative), stage)
            files.append({"name": relative, **_copy(source, destination)})
        archives, images, _ = _copy_extras(meta, stage, used)
        components = (ops._background_components(files) if kind == "background" else
                      [{"id": storage.new_id(), "name": "ReShade", "files": files, "enabled": True}])
    kind_type = {"reshade": "ReShade", "background": "Background", "background_audio": "Audio"}[kind]
    record = {"id": mod_id, "storage_folder": storage_folder, "name": name,
              "character": "Generic" if kind == "reshade" else "Backgrounds", "skin": "",
              "type": kind_type, "types": [kind_type], "tags": [str(tag).strip() for tag in meta.get("tags", []) if str(tag).strip()],
              "image": images[0] if images else None, "images": images, "link": meta.get("link") or "",
              "files": files, "archives": archives, "components": components,
              "size_mb": round(sum(entry["size"] for entry in files) / (1024 * 1024), 2),
              "enabled": bool(mods_path) and not parent and kind != "background_audio",
              "folder": "" if kind == "reshade" else "Backgrounds",
              "install_target": {"reshade": "binaries_win64", "background": "marvel_content", "background_audio": "mods"}[kind],
              "priority": 1, "created_at": storage.now_iso(), "install_options": {}}
    if kind != "reshade":
        record["parent_background_id"] = parent or None
    if parent:
        for component in components:
            component["enabled"] = False
        record["component_selection_initialized"] = True
    if kind == "background_audio":
        record.update(background_audio=True, folder=os.path.join("1_Audio", ops._safe_storage_segment(name, "Background Audio")))
    original_backup = _prepare_movies_backup(record, mods_path, journal, mods)
    active = _enabled_entries(record)
    active_record = {**record, "files": active, "components": []}
    targets = list(dict.fromkeys(ops._journal_file_targets([active_record], mods_path))) if record["enabled"] else []
    journal.set_records([], [record])
    journal.data["special_atomic"] = True
    temporary = temporary_targets(journal)
    if any(os.path.lexists(path) for path, _ in temporary):
        raise ValueError("Um arquivo temporário da instalação já existe. A importação foi interrompida.")
    journal.capture_files([*targets, *temporary])
    guard_targets = []
    hashes = {os.path.normcase(operation_recovery._inside(os.path.join(ops._game_target_dir(record, mods_path), entry["name"]),
                                                               ops._game_target_dir(record, mods_path))): entry["sha256"]
              for entry in files} if targets else {}
    target_keys = {os.path.normcase(operation_recovery._inside(path, root)) for path, root in targets}
    for item in journal.data["files"]:
        if os.path.normcase(item["path"]) not in target_keys:
            continue
        before = _digest(os.path.join(journal.root, item["backup"])) if item["existed"] else None
        guard_targets.append({"path": item["path"], "before": before, "after": hashes[os.path.normcase(item["path"])]})
    context = _active_context(mods, targets, mods_path) if targets else []
    journal.data["special_guard"] = {"context": context, "targets": guard_targets}
    journal.save()
    # Preparação pode demorar. Revalide as configurações e o vínculo, além do
    # destino/backup, antes de tornar o trabalho não cancelável.
    current_settings = storage.load_settings()
    if os.path.realpath(current_settings.get("mods_path") or ".") != os.path.realpath(mods_path or "."):
        raise ValueError("O caminho do jogo mudou durante a importação. Selecione os arquivos novamente.")
    mods = storage.load_mods()
    _parent_exists(meta, mods)
    if targets:
        ops._ensure_game_operation_allowed()
        if _active_context(mods, targets, mods_path) != context:
            raise ValueError("Uma camada mudou durante o preparo da importação. Tente novamente.")
        for item in guard_targets:
            actual = _digest(item["path"]) if os.path.isfile(item["path"]) else None
            if actual != item["before"]:
                raise ValueError("Um arquivo do jogo mudou durante o preparo da importação. Tente novamente.")
    if original_backup:
        if os.path.lexists(original_backup["destination"]) or _tree_files(original_backup["source"]) != original_backup["signature"]:
            raise ValueError("O backup ou MoviesBink mudou durante a importação. Tente novamente.")
    if os.path.lexists(final_dir):
        raise ValueError("A pasta reservada para a importação foi ocupada.")
    operation_jobs.begin_commit("Aplicando o pacote e salvando a biblioteca…")
    journal.mark("applying")
    os.makedirs(os.path.dirname(final_dir), exist_ok=True)
    try:
        os.rename(stage, final_dir)
    except OSError:
        # Se o nome foi ocupado antes do rename, não pertence à operação.
        # Um crash depois do rename bem-sucedido mantém a marca para limpar.
        if os.path.lexists(stage) and os.path.lexists(final_dir):
            journal.data["owned_dirs"].remove(final_dir)
            journal.save()
        raise
    if original_backup:
        os.makedirs(os.path.dirname(original_backup["destination"]), exist_ok=True)
        # Em Windows rename recusa destino existente. A cópia completa fica
        # preservada mesmo se a importação precisar ser desfeita em seguida.
        os.rename(original_backup["stage"], original_backup["destination"])
    if record["enabled"]:
        for entry, (target, _), (temporary_path, _) in zip(active, targets, temporary):
            _publish_file(os.path.join(final_dir, entry["name"]), target, temporary_path)
    mods.append(record)
    storage.save_mods(mods)
    journal.mark("catalog_saved")
    journal.finish("completed")
    try:
        ops._record_activity("add_" + kind, f"{kind_type} adicionado: {name}", {"mod_id": mod_id})
    except Exception:
        pass
    return record


def install(filepaths, meta, kind):
    if not filepaths:
        raise ValueError("Nenhum arquivo foi selecionado para a importação.")
    settings = storage.load_settings()
    journal = meta.get("_operation_journal")
    if not isinstance(journal, operation_recovery.Journal):
        journal = operation_recovery.Journal.create("import_" + kind, "Importar " + kind,
                                                    mods_path=settings.get("mods_path", ""))
    journal.data.update(kind="import_" + kind, title=f"Importar {meta.get('name') or kind}",
                        mods_path=os.path.realpath(settings["mods_path"]) if settings.get("mods_path") else "")
    journal.save()
    try:
        return _install(filepaths, meta, kind, journal, settings)
    except Exception as error:
        try:
            if journal.data.get("mutation_started") and journal.data.get("files"):
                _ops()._ensure_game_operation_allowed()
            operation_recovery.rollback(journal)
        except Exception as recovery_error:
            journal.fail(f"{error} — Recuperação pendente: {recovery_error}")
            raise OSError(f"{error} A operação ficou disponível para recuperação nas configurações.") from error
        raise
