"""
CrabVault - main entry point.
"""
import os
import json
import traceback
import pathlib
import shutil
import tempfile
import zipfile
import subprocess
import threading
import time
import webview

from backend import app_updates, mod_ops, operation_jobs, operation_recovery

BASE_DIR = mod_ops.storage.BASE_DIR
RESOURCE_DIR = mod_ops.storage.RESOURCE_DIR
FRONTEND_DIR = os.path.join(RESOURCE_DIR, "frontend")

window = None
pending_imports = {}
_pending_imports_lock = threading.RLock()
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z"}
MOD_EXTENSIONS = {".pak", ".ucas", ".utoc"}
ARCHIVE_PATTERN = "*.zip;*.rar;*.7z"


def _source_snapshots(source_paths):
    snapshots = {}
    for path in source_paths:
        if path and os.path.isfile(path):
            stat = os.stat(path)
            snapshots[os.path.normcase(os.path.realpath(path))] = (stat.st_size, stat.st_mtime_ns, stat.st_ino)
    return snapshots


def _remove_import_sources(source_paths, expected=None):
    """Remove arquivos de origem após uma importação bem-sucedida.

    O armazenamento do Manager é a cópia de segurança da importação. Nunca
    apagamos um arquivo que já esteja dentro dele, mesmo que ele tenha sido
    selecionado como origem pelo usuário.
    """
    storage_root = os.path.normcase(os.path.realpath(mod_ops.storage.STORAGE_DIR))
    removed = []
    errors = []
    seen = set()

    for source_path in source_paths:
        if not source_path:
            continue
        absolute_path = os.path.abspath(source_path)
        path_key = os.path.normcase(os.path.realpath(absolute_path))
        if path_key in seen:
            continue
        seen.add(path_key)

        try:
            if os.path.commonpath([storage_root, path_key]) == storage_root:
                continue
        except ValueError:
            # Caminhos de unidades diferentes não ficam dentro do storage.
            pass

        if not os.path.isfile(absolute_path):
            continue
        try:
            if expected is not None:
                stat = os.stat(absolute_path)
                if expected.get(path_key) != (stat.st_size, stat.st_mtime_ns, stat.st_ino):
                    errors.append({"path": absolute_path, "error": "A origem mudou durante a importação e foi preservada."})
                    continue
            os.remove(absolute_path)
            removed.append(absolute_path)
        except OSError as exc:
            errors.append({"path": absolute_path, "error": str(exc)})

    return removed, errors


def _create_loose_package_archive(source_paths, destination):
    """Agrupa PAK/UCAS/UTOC soltos em um ZIP restaurável da importação."""
    sources = list(dict.fromkeys(os.path.abspath(path) for path in source_paths))
    if not sources or any(pathlib.Path(path).suffix.lower() not in MOD_EXTENSIONS for path in sources):
        raise ValueError("O ZIP privado só pode conter arquivos .pak, .ucas ou .utoc.")

    groups = {}
    for source in sources:
        if not os.path.isfile(source):
            raise ValueError(f"O arquivo selecionado não está mais disponível: {os.path.basename(source)}")
        groups.setdefault(os.path.normcase(os.path.splitext(source)[0]), []).append(source)

    total = sum(os.path.getsize(source) for source in sources)
    completed = 0
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    try:
        with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            for group_index, group in enumerate(groups.values(), 1):
                folder = ""
                if len(groups) > 1:
                    folder = f"Pacote {group_index:02d} - {pathlib.Path(group[0]).stem}/"
                for source in group:
                    operation_jobs.check()
                    archive_name = folder + os.path.basename(source)
                    info = zipfile.ZipInfo.from_file(source, archive_name)
                    info.compress_type = zipfile.ZIP_STORED
                    with open(source, "rb") as incoming, archive.open(info, "w", force_zip64=True) as outgoing:
                        while True:
                            operation_jobs.check()
                            chunk = incoming.read(2 * 1024 * 1024)
                            if not chunk:
                                break
                            outgoing.write(chunk)
                            completed += len(chunk)
                            operation_jobs.progress(
                                "archiving", "Criando o ZIP dos pacotes selecionados…",
                                completed, total, "bytes",
                            )
        return destination
    except BaseException:
        try:
            os.remove(destination)
        except OSError:
            pass
        raise


def _safe_extract_zip(archive_path, destination):
    """Extrai ZIP sem permitir caminhos fora da pasta temporária."""
    with zipfile.ZipFile(archive_path) as archive:
        base = os.path.abspath(destination)
        entries = archive.infolist()
        for entry in entries:
            target = os.path.abspath(os.path.join(destination, entry.filename))
            if os.path.commonpath([base, target]) != base or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("O arquivo compactado contém um caminho inválido.")
        total = sum(entry.file_size for entry in entries)
        completed = 0
        for entry in entries:
            operation_jobs.check()
            target = os.path.abspath(os.path.join(destination, entry.filename))
            if entry.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(entry) as source, open(target, "wb") as outgoing:
                while True:
                    operation_jobs.check()
                    chunk = source.read(2 * 1024 * 1024)
                    if not chunk:
                        break
                    outgoing.write(chunk)
                    completed += len(chunk)
                    operation_jobs.progress("extracting", f"Extraindo {os.path.basename(archive_path)}",
                                            completed, total, "bytes")


def _find_archive_extractor(suffix):
    """UnRAR só abre RAR; WinRAR e 7-Zip também abrem 7z."""
    candidates = [("7zip", os.path.join(RESOURCE_DIR, "tools", "7zip", "7z.exe"))]
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
        if root:
            candidates.extend((kind, os.path.join(root, relative)) for kind, relative in (
                ("7zip", r"7-Zip\7z.exe"), ("winrar", r"WinRAR\WinRAR.exe")))
    candidates.extend((kind, shutil.which(name)) for kind, name in (
        ("7zip", "7z"), ("7zip", "7zz"), ("winrar", "WinRAR")))
    if suffix == ".rar":
        candidates.append(("unrar", shutil.which("UnRAR")))
    return next(((kind, path) for kind, path in candidates if path and os.path.isfile(path)), (None, None))


def _extract_archive(archive_path, destination=None):
    """Extrai ZIP nativamente e RAR/7z com uma ferramenta compatível."""
    suffix = pathlib.Path(archive_path).suffix.lower()
    destination = destination or tempfile.mkdtemp(prefix="marvel_manager_import_")
    os.makedirs(destination, exist_ok=True)
    try:
        if suffix == ".zip":
            _safe_extract_zip(archive_path, destination)
        elif suffix in {".rar", ".7z"}:
            kind, executable = _find_archive_extractor(suffix)
            if not executable:
                raise RuntimeError(f"O leitor de {suffix} está ausente. Extraia novamente o pacote completo do CrabVault.")
            if kind == "7zip":
                command = [executable, "x", "-y", "-p-", "-o" + destination, archive_path]
            else:
                command = [executable, "x", "-y", "-p-", "-inul"]
                if kind == "winrar":
                    command.append("-ibck")
                command.extend([archive_path, destination + os.sep])
            job = operation_jobs.current()
            result = job.run(command, timeout=120) if job else subprocess.run(
                command, capture_output=True, text=True, errors="ignore", timeout=120,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode != 0:
                raise RuntimeError(f"Não foi possível extrair completamente o arquivo {suffix}. "
                                   "Verifique se está íntegro e sem senha.")
        else:
            raise ValueError("Formato compactado não suportado.")
        return destination
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


class Api:
    # ---- leitura ----
    def get_mods(self):
        return mod_ops.list_mods(include_thumbnails=False)

    def get_library_snapshot(self):
        return mod_ops.get_library_snapshot()

    def get_characters(self):
        return mod_ops.get_characters()

    def get_character_roster(self):
        return mod_ops.get_character_roster()

    def get_skins_for_character(self, character):
        return mod_ops.get_skins_for_character(character)

    def get_character_skins(self, character):
        return mod_ops.get_character_skins(character)

    def get_types(self):
        return mod_ops.get_types()

    def get_tags(self):
        return mod_ops.get_tags()

    def get_folders(self):
        return mod_ops.get_folders()

    def scan_installed_mods(self):
        return mod_ops.scan_installed_mods()

    def get_settings(self):
        return mod_ops.get_settings()

    def get_character_catalog_status(self):
        return mod_ops.get_character_catalog_status()

    def update_character_catalog(self):
        return mod_ops.update_character_catalog(force=True)

    def check_app_update(self):
        return app_updates.check()

    def get_github_download_stats(self):
        return app_updates.github_download_stats()

    def install_app_update(self):
        return app_updates.download_and_install(BASE_DIR, window.destroy)

    def launch_game(self):
        return mod_ops.launch_game()

    def get_profiles(self):
        return mod_ops.list_profiles()

    def save_profile(self, name):
        return mod_ops.save_profile(name)

    def update_profile(self, profile_id):
        return mod_ops.update_profile(profile_id)

    def apply_profile(self, profile_id):
        return mod_ops.apply_profile(profile_id)

    def delete_profile(self, profile_id):
        return mod_ops.delete_profile(profile_id)

    def get_recovery_snapshot(self):
        return mod_ops.get_recovery_snapshot()

    def restore_last_recovery_snapshot(self):
        return mod_ops.restore_last_recovery_snapshot()

    def get_activity_log(self):
        return mod_ops.get_activity_log()

    def clear_activity_log(self):
        return mod_ops.clear_activity_log()

    def clear_old_activity_log(self, days=30):
        return mod_ops.clear_old_activity_log(days)

    def record_import_performance(self, sample):
        return mod_ops.record_import_performance(sample)

    def get_import_performance(self, limit=10):
        return mod_ops.get_import_performance(limit)

    def inspect_library_integrity(self):
        return mod_ops.inspect_library_integrity()

    def inspect_library_health(self, verify_hashes=True, mod_ids=None):
        from backend import library_maintenance
        return library_maintenance.inspect_library_health(verify_hashes, mod_ids)

    def preview_library_repair(self, mod_id):
        from backend import library_maintenance
        return library_maintenance.preview_library_repair(mod_id)

    def apply_library_repair(self, token, action_ids=None):
        from backend import library_maintenance
        return library_maintenance.apply_library_repair(token, action_ids)

    def list_pending_classifications(self):
        from backend import library_maintenance
        return library_maintenance.list_pending_classifications()

    def reanalyze_selected_components(self, components):
        from backend import library_maintenance
        return library_maintenance.reanalyze_selected_components(components)

    def suggest_component_relations(self, mod_id, component_id=None):
        from backend import library_maintenance
        return library_maintenance.suggest_component_relations(mod_id, component_id)

    def preview_relation_suggestion(self, mod_id, suggestion_id, preferred_component_id=None):
        from backend import library_maintenance
        return library_maintenance.preview_relation_suggestion(mod_id, suggestion_id, preferred_component_id)

    def apply_relation_suggestion(self, token):
        from backend import library_maintenance
        return library_maintenance.apply_relation_suggestion(token)

    def preview_conflict_resolution(self, mod_id, component_id):
        from backend import conflict_resolution
        return conflict_resolution.preview_resolution(mod_id, component_id)

    def apply_conflict_resolution(self, token):
        from backend import conflict_resolution
        return conflict_resolution.apply_resolution(token)

    def repair_library_integrity(self, mod_id):
        return mod_ops.repair_library_integrity(mod_id)

    def ignore_missing_media(self, mod_id, media_names):
        return mod_ops.ignore_missing_media(mod_id, media_names)

    def export_library_backup_dialog(self):
        return mod_ops.export_library_backup_to_default_directory()

    def restore_library_backup_dialog(self):
        result = window.create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=("Backup do CrabVault (*.json)", "JSON (*.json)"),
        )
        if not result:
            return {"cancelled": True}
        path = result[0] if isinstance(result, (list, tuple)) else result
        return mod_ops.restore_library_backup(path)

    def start_full_backup_preview(self, request_id=None):
        from backend import full_backup

        def prepare(job):
            operation_jobs.progress("selection", "Escolha onde salvar o backup completo…")
            selected = window.create_file_dialog(webview.FileDialog.FOLDER)
            if not selected:
                return {"cancelled": True}
            operation_jobs.check()
            directory = selected[0] if isinstance(selected, (list, tuple)) else selected
            return full_backup.preview_backup(directory)

        return operation_jobs.start("Estimando backup completo…", prepare, request_id=request_id,
                                    context={"kind": "backup_preview"})

    def start_full_backup(self, token, allow_incomplete=False):
        from backend import full_backup
        return operation_jobs.start("Criando backup completo…",
                                    lambda job: full_backup.create_backup(token, allow_incomplete),
                                    request_id="backup:" + str(token), context={"kind": "backup_create"})

    def start_full_restore_preview(self, request_id=None):
        from backend import full_backup

        def prepare(job):
            operation_jobs.progress("selection", "Selecione o backup completo em ZIP…")
            selected = window.create_file_dialog(webview.FileDialog.OPEN,
                                                file_types=("Backup completo do CrabVault (*.zip)",))
            if not selected:
                return {"cancelled": True}
            operation_jobs.check()
            source = selected[0] if isinstance(selected, (list, tuple)) else selected
            operation_jobs.progress("selection", "Escolha onde criar a pasta da biblioteca restaurada…")
            selected = window.create_file_dialog(webview.FileDialog.FOLDER)
            if not selected:
                return {"cancelled": True}
            operation_jobs.check()
            directory = selected[0] if isinstance(selected, (list, tuple)) else selected
            return full_backup.preview_restore(source, directory)

        return operation_jobs.start("Verificando backup completo…", prepare, request_id=request_id,
                                    context={"kind": "restore_preview"})

    def start_full_restore(self, token):
        from backend import full_backup
        return operation_jobs.start("Extraindo e verificando backup completo…", lambda job: full_backup.restore_backup(token),
                                    request_id="restore:" + str(token), context={"kind": "backup_restore"})

    def save_settings(self, values):
        return mod_ops.save_settings(values)

    def get_mod_details(self, mod_id, include_previews=True):
        return mod_ops.get_mod_details(mod_id, include_previews=include_previews)

    def get_component_file_contents(self, mod_id, component_id):
        return mod_ops.get_component_file_contents(mod_id, component_id)

    def classify_mod_components(self, mod_id):
        return mod_ops.classify_mod_components(mod_id)

    def get_component_diagnosis(self, mod_id, component_id):
        return mod_ops.get_component_diagnosis(mod_id, component_id)

    def retry_component_analysis(self, mod_id, component_id):
        return mod_ops.retry_component_analysis(mod_id, component_id)

    def set_component_rules(self, mod_id, component_id, exclusive_group="", requires=None):
        return mod_ops.set_component_rules(mod_id, component_id, exclusive_group, requires)

    def disable_conflict_owner(self, mod_id, component_id):
        return mod_ops.disable_conflict_owner(mod_id, component_id)

    def prepare_component_3d_preview(self, mod_id, component_id, model_key=None, request_id=None, gpu_formats=None):
        return mod_ops.prepare_component_3d_preview(mod_id, component_id, model_key, request_id, gpu_formats)

    def cancel_component_3d_preview(self, request_id):
        return mod_ops.cancel_component_3d_preview(request_id)

    def open_cinematic_preview(self, mod_id, component_id):
        return mod_ops.open_cinematic_preview(mod_id, component_id)

    def bind_background_audio(self, cinematic_mod_id, cinematic_component_id, audio_mod_id, audio_component_id):
        return mod_ops.bind_background_audio(cinematic_mod_id, cinematic_component_id, audio_mod_id, audio_component_id)

    def unbind_background_audio(self, cinematic_mod_id, cinematic_component_id):
        return mod_ops.unbind_background_audio(cinematic_mod_id, cinematic_component_id)

    def set_background_audio_enabled(self, mod_id, component_id, enable):
        return mod_ops.set_background_audio_enabled(mod_id, component_id, enable)

    def get_background_audio_preview(self, mod_id, component_id):
        return mod_ops.get_background_audio_preview(mod_id, component_id)

    def get_mod_thumbnail(self, mod_id):
        return mod_ops.get_mod_thumbnail(mod_id)

    def get_conflicts(self, mod_ids=None):
        return mod_ops.get_conflicts(mod_ids)

    def get_gallery_media(self, mod_id, media_name):
        return mod_ops.get_gallery_media(mod_id, media_name)

    def get_gallery_preview(self, mod_id, media_name):
        return mod_ops.get_gallery_preview(mod_id, media_name)

    # ---- acoes em mods existentes ----
    def toggle_mod(self, mod_id):
        return mod_ops.toggle_mod(mod_id)

    def set_mods_enabled(self, mod_ids, enable):
        return mod_ops.set_mods_enabled(mod_ids, enable)

    def set_manual_conflicts(self, mod_ids):
        return mod_ops.set_manual_conflicts(mod_ids)

    def toggle_component(self, mod_id, component_id):
        return mod_ops.toggle_component(mod_id, component_id)

    def preview_remove_component(self, mod_id, component_id):
        return mod_ops.preview_remove_component(mod_id, component_id)

    def remove_component(self, mod_id, component_id):
        return mod_ops.remove_component(mod_id, component_id)

    def restore_removed_component(self, mod_id, removed_id):
        return mod_ops.restore_removed_component(mod_id, removed_id)

    def promote_added_component_to_update(self, mod_id, added_component_id, target_component_id):
        return mod_ops.promote_added_component_to_update(mod_id, added_component_id, target_component_id)

    def restore_component_version(self, mod_id, component_id, version_id):
        return mod_ops.restore_component_version(mod_id, component_id, version_id)

    def remove_background_cinematic(self, mod_id, component_id):
        return mod_ops.remove_background_cinematic(mod_id, component_id)

    def rename_component(self, mod_id, component_id, name):
        return mod_ops.rename_component(mod_id, component_id, name)

    def move_component(self, mod_id, component_id, direction):
        return mod_ops.move_component(mod_id, component_id, direction)

    def reorder_components(self, mod_id, component_ids):
        return mod_ops.reorder_components(mod_id, component_ids)

    def move_components(self, mod_id, component_ids, direction):
        return mod_ops.move_components(mod_id, component_ids, direction)

    def set_component_description(self, mod_id, component_id, description):
        return mod_ops.set_component_description(mod_id, component_id, description)

    def set_components_description(self, mod_id, component_ids, description):
        return mod_ops.set_components_description(mod_id, component_ids, description)

    def get_component_labels(self):
        return mod_ops.get_component_labels()

    def create_component_label(self, label):
        return mod_ops.create_component_label(label)

    def delete_component_label(self, label):
        return mod_ops.delete_component_label(label)

    def delete_mod(self, mod_id):
        return mod_ops.delete_mod(mod_id)

    def delete_mod_permanently(self, mod_id):
        return mod_ops.delete_mod_permanently(mod_id)

    def rename_mod(self, mod_id, new_name):
        return mod_ops.rename_mod(mod_id, new_name)

    def set_mod_link(self, mod_id, link):
        return mod_ops.set_mod_link(mod_id, link)

    def set_mod_identity(self, mod_id, character, skin):
        return mod_ops.set_mod_identity(mod_id, character, skin)

    def set_priority(self, mod_id, delta):
        return mod_ops.set_priority(mod_id, delta)

    def move_mod(self, mod_id, folder):
        return mod_ops.move_mod(mod_id, folder)

    def choose_move_destination(self, mod_id):
        """Abre o seletor já no herói e aplica o destino de skin escolhido."""
        root = mod_ops.get_move_destination_root(mod_id)
        if not root.get("ok"):
            return root
        result = window.create_file_dialog(webview.FileDialog.FOLDER, directory=root["directory"])
        if not result:
            return {"cancelled": True}
        selected = result[0] if isinstance(result, (list, tuple)) else result
        return mod_ops.move_mod_to_skin_folder(mod_id, selected)

    def migrate_legacy_layouts(self):
        return mod_ops.migrate_legacy_layouts()

    def create_folder(self, name, parent):
        return mod_ops.create_folder(name, parent)

    def add_tag(self, mod_id, tag):
        return mod_ops.add_tag(mod_id, tag)

    def create_tag(self, tag):
        return mod_ops.create_tag(tag)

    def remove_tag(self, mod_id, tag):
        return mod_ops.remove_tag(mod_id, tag)

    def delete_tag_catalog(self, tag):
        return mod_ops.delete_tag_catalog(tag)

    def open_mod_folder(self, mod_id):
        path = mod_ops.get_open_path(mod_id)
        return mod_ops.open_in_explorer(path)

    def get_native3d_support_status(self):
        return mod_ops.get_native3d_support_status()

    def start_native3d_support_update(self, request_id=None):
        return operation_jobs.start("Preparando suporte 3D…", mod_ops.update_native3d_support,
                                    request_id=request_id, context={"kind": "native3d_support"})

    def edit_image_dialog(self, mod_id):
        result = window.create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=("Images (*.png;*.jpg;*.jpeg;*.webp;*.gif)",),
        )
        if not result:
            return {"cancelled": True}
        image_path = result[0] if isinstance(result, (list, tuple)) else result
        return mod_ops.set_image(mod_id, image_path)

    def add_detail_images(self, mod_id):
        result = window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=True,
            file_types=("Media (*.png;*.jpg;*.jpeg;*.webp;*.gif;*.mp4;*.webm;*.ogv;*.mov)",),
        )
        if not result:
            return {"cancelled": True}
        paths = list(result) if isinstance(result, (list, tuple)) else [result]
        return mod_ops.add_gallery_images(mod_id, paths)

    def remove_detail_image(self, mod_id, image_name):
        return mod_ops.remove_gallery_image(mod_id, image_name)

    def set_detail_cover(self, mod_id, image_name):
        return mod_ops.set_gallery_cover(mod_id, image_name)

    def reorder_detail_gallery(self, mod_id, image_names):
        return mod_ops.reorder_gallery_images(mod_id, image_names)

    def set_detail_image_title(self, mod_id, image_name, title):
        return mod_ops.set_gallery_image_title(mod_id, image_name, title)

    # ---- configuracao da pasta do jogo (Settings) ----
    def auto_detect_mods_path(self):
        path = mod_ops.auto_detect_mods_path()
        if path:
            mod_ops.set_mods_path(path)
        return path

    def set_mods_path_dialog(self):
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if result:
            path = result[0] if isinstance(result, (list, tuple)) else result
            mod_ops.set_mods_path(path)
            return path
        return None

    # ---- adicionar mod ----
    def begin_mod_install(self):
        return self._prepare_mod_install()

    def start_mod_import(self, request_id=None, kind="pak", parent_background_id=None):
        if kind not in {"pak", "reshade", "background", "background_audio"}:
            return {"ok": False, "error": "Tipo de importação inválido."}
        def prepare(job):
            journal = operation_recovery.Journal.create("import", "Importação de mod")
            if kind == "pak":
                return self._prepare_mod_install(journal=journal)
            return self._prepare_special_import(kind, parent_background_id, journal)

        return operation_jobs.start("Selecione os arquivos na janela do sistema…", prepare,
                                    request_id=request_id,
                                    context={"kind": "import_prepare", "install_kind": kind,
                                             "parent_background_id": parent_background_id})

    def start_add_mod_components(self, mod_id, request_id=None, filepaths=None, target_component_id=None):
        """Seleciona, analisa e anexa variantes ao mod sem abrir outro cadastro."""
        def append(job):
            validation = mod_ops.validate_component_append_target(mod_id)
            if not validation.get("ok"):
                return validation
            journal = operation_recovery.Journal.create(
                "component_append", f"Adicionar componentes: {validation.get('name', 'Mod')}",
                mods_path=mod_ops.storage.load_settings().get("mods_path", ""),
            )
            prepared = self._prepare_mod_install(filepaths=filepaths, journal=journal, keep_pending=False)
            if not prepared.get("ok"):
                return prepared
            pending = prepared.pop("_pending")
            pending["install_kind"] = "component_append"
            pending["target_mod_id"] = mod_id
            return self._complete_pending_mod_install(pending, {"target_component_id": target_component_id})

        return operation_jobs.start(
            "Selecione as novas variantes na janela do sistema…", append,
            request_id=request_id,
            context={"kind": "component_append", "mod_id": mod_id,
                     "target_component_id": target_component_id},
        )

    def find_operation(self, request_id):
        return operation_jobs.find_request(request_id)

    def start_library_health(self, verify_hashes=True, request_id=None):
        from backend.library_maintenance import inspect_library_health
        return operation_jobs.start("Verificando a biblioteca…", lambda job: inspect_library_health(verify_hashes),
                                    request_id=request_id, context={"kind": "health"})

    def start_conflict_check(self, request_id=None):
        return operation_jobs.start("Verificando conflitos…", lambda job: mod_ops.get_conflicts(),
                                    request_id=request_id, context={"kind": "conflicts"})

    def get_operation_status(self, job_id):
        return operation_jobs.get_status(job_id)

    def cancel_operation(self, job_id):
        return operation_jobs.cancel(job_id)

    def get_operation_recoveries(self):
        return {"ok": True, "operations": operation_recovery.list_pending()}

    def recover_interrupted_operation(self, operation_id):
        return mod_ops.recover_interrupted_operation(operation_id)

    def _prepare_mod_install(self, filepaths=None, journal=None, keep_pending=True):
        temp_dirs = []
        token = None
        try:
            if filepaths is None:
                filepaths = window.create_file_dialog(
                    webview.FileDialog.OPEN, allow_multiple=True,
                    file_types=(f"Mods e compactados (*.pak;*.ucas;*.utoc;{ARCHIVE_PATTERN})", "Todos os arquivos (*.*)"),
                )
            if not filepaths:
                if journal:
                    journal.finish("cancelled")
                return {"cancelled": True}
            token = mod_ops.storage.new_id()
            paths = list(filepaths) if isinstance(filepaths, (list, tuple)) else [filepaths]
            source_files = list(paths)
            if any(pathlib.Path(path).suffix.lower() not in ARCHIVE_EXTENSIONS | MOD_EXTENSIONS for path in paths):
                raise ValueError("Selecione ZIP, RAR, 7z ou arquivos .pak/.ucas/.utoc.")
            archives = [path for path in paths if pathlib.Path(path).suffix.lower() in ARCHIVE_EXTENSIONS]
            if archives and len(archives) != len(paths):
                raise ValueError("Selecione somente ZIP/RAR/7z ou somente arquivos .pak/.ucas/.utoc.")
            source_snapshots = _source_snapshots(source_files)
            component_labels = {}
            if archives:
                paths = []
                for archive_index, archive_path in enumerate(archives):
                    operation_jobs.progress("extracting", f"Extraindo {archive_index + 1}/{len(archives)}: {os.path.basename(archive_path)}",
                                            archive_index, len(archives))
                    destination = os.path.join(journal.stage_dir("extracted"), str(archive_index)) if journal else None
                    temp_dir = (_extract_archive(archive_path, destination=destination) if destination
                                else _extract_archive(archive_path))
                    temp_dirs.append(temp_dir)
                    archive_files = [str(path) for path in pathlib.Path(temp_dir).rglob("*")
                                     if path.is_file() and path.suffix.lower() in {".pak", ".ucas", ".utoc"}]
                    if any(not path.resolve().is_relative_to(pathlib.Path(temp_dir).resolve()) for path in map(pathlib.Path, archive_files)):
                        raise ValueError("O arquivo compactado contém um caminho inválido.")
                    if not archive_files:
                        raise ValueError(f"O compactado {pathlib.Path(archive_path).name} não contém "
                                         "arquivos .pak, .ucas ou .utoc instaláveis.")
                    paths.extend(archive_files)
                    for path in archive_files:
                        relative_parent = pathlib.Path(path).relative_to(temp_dir).parent.parts
                        label_parts = relative_parent[1:] if len(relative_parent) > 1 else relative_parent
                        # Mesmo quando o compactado deixa tudo na raiz, cada
                        # trio .pak/.ucas/.utoc é uma opção independente.
                        package_stem = pathlib.Path(path).stem
                        label = " / ".join(label_parts + (package_stem,)) if label_parts else package_stem
                        component_labels[os.path.normcase(path)] = (
                            f"{pathlib.Path(archive_path).stem} / {label}" if len(archives) > 1 else label
                        )
                if not paths:
                    for directory in temp_dirs:
                        shutil.rmtree(directory, ignore_errors=True)
                    return {"ok": False, "error": "Não encontrei arquivos .pak, .ucas ou .utoc no compactado."}
            pending = {"files": paths, "images": [], "temp_dirs": temp_dirs,
                       "component_labels": component_labels, "archives": archives,
                       "source_files": source_files,
                       "source_snapshots": source_snapshots,
                       "operation_id": journal.id if journal else None}
            plan = mod_ops.prepare_mod_import(paths, component_labels)
            asset_paths = list(dict.fromkeys(path for component in plan["components"] for path in component["asset_paths"]))
            result = mod_ops.analyze_mod_files(paths, asset_paths=asset_paths)
            pending["plan"] = plan
            from backend import personal_corrections
            result["personal_corrections"] = personal_corrections.suggest_for_import(plan)
            if archives:
                source_name = pathlib.Path(archives[0]).stem
                result["source_folder"] = source_name
                result["suggested_folder"] = os.path.join(
                    "1_Audio" if result["type"] == "Audio" else result["character"],
                    source_name if result["type"] == "Audio" else (result["skin"] or "Default"),
                    *([] if result["type"] == "Audio" else [source_name]),
                )
            result.update({"ok": True, "token": token, "file_count": len(paths)})
            if keep_pending:
                operation_jobs.begin_commit("Arquivos preparados para a instalação.")
                if journal:
                    journal.mark("awaiting_metadata")
                with _pending_imports_lock:
                    pending_imports[token] = pending
            else:
                result["_pending"] = pending
            return result
        except Exception as e:
            if token:
                pending_imports.pop(token, None)
            for directory in temp_dirs:
                shutil.rmtree(directory, ignore_errors=True)
            if journal:
                journal.finish("cancelled" if isinstance(e, operation_jobs.OperationCancelled) else "aborted")
            if not isinstance(e, operation_jobs.OperationCancelled):
                traceback.print_exc()
            return {"ok": False, "error": str(e), "cancelled": isinstance(e, operation_jobs.OperationCancelled)}

    def choose_install_image(self, token):
        if token not in pending_imports:
            return {"ok": False, "error": "Seleção de mod expirou."}
        result = window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=True,
            file_types=("Images (*.png;*.jpg;*.jpeg;*.webp;*.gif)",),
        )
        if not result:
            return {"cancelled": True}
        paths = list(result) if isinstance(result, (list, tuple)) else [result]
        snapshots = _source_snapshots(paths)
        with _pending_imports_lock:
            pending = pending_imports.get(token)
            if not pending:
                return {"ok": False, "error": "Seleção de mod expirou."}
            pending["images"] = paths
            pending.setdefault("source_snapshots", {}).update(snapshots)
        return {
            "ok": True,
            "image_url": pathlib.Path(paths[0]).as_uri(),
            "images": [{"url": pathlib.Path(path).as_uri(), "name": os.path.basename(path)} for path in paths],
        }

    def _prepare_special_import(self, kind, parent_background_id=None, journal=None):
        journal = journal or operation_recovery.Journal.create("import", "Importação de " + kind)
        try:
            audio = kind == "background_audio"
            operation_jobs.progress("selecting", "Selecione os arquivos na janela do sistema…")
            selected = window.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=True,
                file_types=(("Áudio de Background (*.pak)",) if audio else
                            (f"Compactados {kind} ({ARCHIVE_PATTERN})",)),
            )
            if not selected:
                journal.finish("cancelled")
                return {"cancelled": True}
            selected = list(selected) if isinstance(selected, (list, tuple)) else [selected]
            allowed = {".pak"} if audio else ARCHIVE_EXTENSIONS
            if any(pathlib.Path(path).suffix.lower() not in allowed for path in selected):
                raise ValueError("Selecione pacotes PAK de áudio." if audio else "Selecione ZIP, RAR ou 7z.")
            snapshots = _source_snapshots(selected)
            paths, temp_dirs, relative_paths = [], [], {}
            if audio:
                paths = selected
            else:
                for index, archive_path in enumerate(selected):
                    operation_jobs.progress("extracting", f"Extraindo {index + 1}/{len(selected)}: {os.path.basename(archive_path)}", index, len(selected))
                    directory = _extract_archive(archive_path, destination=os.path.join(journal.stage_dir("extracted"), str(index)))
                    temp_dirs.append(directory)
                    root = pathlib.Path(directory).resolve()
                    for path in root.rglob("*"):
                        operation_jobs.check()
                        if not path.is_file():
                            continue
                        if not path.resolve().is_relative_to(root):
                            raise ValueError("O compactado contém um caminho fora da pasta de extração.")
                        source = str(path)
                        paths.append(source)
                        relative_paths[os.path.normcase(source)] = str(path.relative_to(root))
            if not paths:
                raise ValueError("O compactado não contém arquivos instaláveis.")
            operation_jobs.begin_commit("Arquivos preparados para a instalação.")
            journal.mark("awaiting_metadata")
            token = mod_ops.storage.new_id()
            with _pending_imports_lock:
                pending_imports[token] = {
                    "files": paths, "images": [], "temp_dirs": temp_dirs,
                    "archives": [] if audio else selected, "source_snapshots": snapshots,
                    "source_files": selected,
                    "relative_paths": relative_paths, "install_kind": kind,
                    "parent_background_id": parent_background_id, "operation_id": journal.id,
                }
            return {"ok": True, "token": token, "file_count": len(paths), "install_kind": kind,
                    "suggested_name": pathlib.Path(selected[0]).stem, **({"type": "Audio"} if audio else {})}
        except Exception as error:
            journal.finish("cancelled" if isinstance(error, operation_jobs.OperationCancelled) else "aborted")
            return {"ok": False, "error": str(error), "cancelled": isinstance(error, operation_jobs.OperationCancelled)}

    def begin_reshade_install(self):
        return self._prepare_special_import("reshade")

    def begin_background_install(self, parent_background_id=None):
        return self._prepare_special_import("background", parent_background_id)

    def begin_background_audio_install(self, parent_background_id):
        return self._prepare_special_import("background_audio", parent_background_id)

    def start_complete_mod_install(self, token, meta):
        if not isinstance(meta, dict):
            return {"ok": False, "error": "Os dados da instalação são inválidos."}
        if not isinstance(token, str) or not token or len(token) > 100:
            return {"ok": False, "error": "A seleção da instalação é inválida."}
        request_id = "install:" + str(token)
        with _pending_imports_lock:
            previous = operation_jobs.find_request(request_id)
            if previous.get("found"):
                return {"ok": True, "job_id": previous["job_id"], "request_id": request_id, "reused": True}
            pending = pending_imports.pop(token, None)
            if not pending:
                return {"ok": False, "error": "Seleção de mod expirou. Escolha os arquivos novamente."}
            return operation_jobs.start("Copiando os arquivos para a biblioteca…",
                                        lambda job: self._complete_pending_mod_install(pending, dict(meta)),
                                        on_cancel=lambda: self._discard_pending_mod_install(pending),
                                        request_id=request_id,
                                        context={"kind": "import_commit", "install_kind": pending.get("install_kind", "pak"),
                                                 "parent_background_id": pending.get("parent_background_id")})

    def complete_mod_install(self, token, meta):
        with _pending_imports_lock:
            pending = pending_imports.pop(token, None)
        if not pending:
            return {"ok": False, "error": "Seleção de mod expirou. Escolha os arquivos novamente."}
        return self._complete_pending_mod_install(pending, meta)

    def _complete_pending_mod_install(self, pending, meta):
        journal = None
        started_at = time.perf_counter()
        try:
            if pending.get("operation_id"):
                journal = operation_recovery.Journal.load(pending["operation_id"], resume=True)
            operation_jobs.check()
            meta = dict(meta)
            meta["image_paths"] = pending.get("images", [])
            meta["_import_plan"] = pending.get("plan")
            meta["_operation_journal"] = journal
            meta["component_labels"] = pending.get("component_labels", {})
            settings = mod_ops.storage.load_settings()
            archive_sources = pending.get("archives", [])
            source_files = pending.get("source_files", archive_sources)
            meta["source_archive_names"] = [os.path.basename(path) for path in (archive_sources or source_files) if path]
            meta["relative_paths"] = pending.get("relative_paths", {})
            meta["parent_background_id"] = pending.get("parent_background_id")
            source_paths = [*source_files, *pending.get("images", [])]
            source_snapshots = pending.get("source_snapshots", _source_snapshots(source_paths))
            for path, expected in source_snapshots.items():
                stat = os.stat(path)
                if tuple(expected) != (stat.st_size, stat.st_mtime_ns, stat.st_ino):
                    raise ValueError("Um arquivo de origem mudou desde a seleção. Selecione o pacote novamente.")
            preserve_archives = settings.get("preserve_import_archives", True)
            if preserve_archives and not archive_sources and pending.get("install_kind", "pak") in {"pak", "component_append"}:
                if journal:
                    archive_dir = os.path.join(journal.stage_dir("extracted"), "loose-archive")
                else:
                    archive_dir = tempfile.mkdtemp(prefix="marvel_manager_loose_archive_")
                    pending.setdefault("temp_dirs", []).append(archive_dir)
                first_stem = pathlib.Path(source_files[0]).stem if source_files else "Pacotes selecionados"
                package_count = len({os.path.normcase(os.path.splitext(os.path.abspath(path))[0])
                                     for path in source_files})
                archive_name = (first_stem + ".zip" if package_count == 1
                                else f"{first_stem} e mais {package_count - 1} pacote(s).zip")
                archive_sources = [_create_loose_package_archive(
                    source_files, os.path.join(archive_dir, archive_name),
                )]
            meta["archive_paths"] = archive_sources if preserve_archives else []
            record = (mod_ops.add_reshade_mod(pending["files"], meta)
                      if pending.get("install_kind") == "reshade"
                      else mod_ops.add_background_mod(pending["files"], meta)
                      if pending.get("install_kind") == "background"
                      else mod_ops.add_background_audio_mod(pending["files"], meta)
                      if pending.get("install_kind") == "background_audio"
                      else mod_ops.add_mod_components(pending.get("target_mod_id"), pending["files"], meta)
                      if pending.get("install_kind") == "component_append"
                      else mod_ops.add_mod(pending["files"], meta))
            if settings.get("delete_import_sources_after_success", True):
                removed_sources, cleanup_errors = _remove_import_sources(source_paths, expected=source_snapshots)
            else:
                removed_sources, cleanup_errors = [], []
            return {
                "ok": True,
                "record": record,
                "backend_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "source_cleanup": {
                    "removed": removed_sources,
                    "errors": cleanup_errors,
                    "preserved": [] if settings.get("delete_import_sources_after_success", True) else source_paths,
                },
            }
        except Exception as e:
            if journal and not journal.data.get("mutation_started"):
                journal.finish("cancelled" if isinstance(e, operation_jobs.OperationCancelled) else "aborted")
            if not isinstance(e, operation_jobs.OperationCancelled):
                traceback.print_exc()
            return {"ok": False, "error": str(e), "cancelled": isinstance(e, operation_jobs.OperationCancelled)}
        finally:
            for directory in pending.get("temp_dirs", []):
                shutil.rmtree(directory, ignore_errors=True)

    def _discard_pending_mod_install(self, pending):
        if pending.get("operation_id"):
            operation_recovery.Journal.load(pending["operation_id"]).finish("cancelled")
        for directory in pending.get("temp_dirs", []):
            shutil.rmtree(directory, ignore_errors=True)

    def cancel_mod_install(self, token):
        with _pending_imports_lock:
            pending = pending_imports.pop(token, None)
        if pending:
            self._discard_pending_mod_install(pending)
        return {"ok": True}

    def restore_cinematic_defaults(self):
        return mod_ops.restore_cinematic_defaults()

    # ---- titlebar ----
    def minimize(self):
        window.minimize()

    def toggle_maximize(self):
        window.toggle_fullscreen()

    def close(self):
        window.destroy()


def _check_character_catalog_in_background():
    """Consulta diária sem atrasar a abertura e informa a interface carregada."""
    result = mod_ops.update_character_catalog(force=False)
    try:
        window.evaluate_js(
            "window.onCharacterCatalogUpdated?.(" + json.dumps(result, ensure_ascii=False) + ")"
        )
    except Exception:
        # A janela pode ter sido fechada enquanto a consulta estava em curso.
        pass


def _initial_window_geometry(screen):
    """Dimensiona e centraliza a janela sem ocupar toda a área útil."""
    frame = getattr(screen, "frame", None)
    area_x = int(getattr(frame, "X", getattr(screen, "x", 0)))
    area_y = int(getattr(frame, "Y", getattr(screen, "y", 0)))
    area_width = int(getattr(frame, "Width", getattr(screen, "width", 1280)))
    area_height = int(getattr(frame, "Height", getattr(screen, "height", 800)))
    width = min(1280, max(800, int(area_width * 0.9)))
    height = min(800, max(520, int(area_height * 0.9)))
    width = min(width, area_width)
    height = min(height, area_height)
    return {
        "width": width,
        "height": height,
        "x": area_x + max(0, (area_width - width) // 2),
        "y": area_y + max(0, (area_height - height) // 2),
    }


if __name__ == "__main__":
    import sys
    if "--self-check" in sys.argv:
        from backend.portable_check import write_report
        position = sys.argv.index("--self-check") + 1
        raise SystemExit(write_report(sys.argv[position] if position < len(sys.argv) else None))
    from backend.webview2_runtime import ensure_runtime
    if not ensure_runtime():
        raise SystemExit(1)
    api = Api()
    primary_screen = webview.screens[0]
    geometry = _initial_window_geometry(primary_screen)
    window = webview.create_window(
        "CrabVault",
        os.path.join(FRONTEND_DIR, "index.html"),
        js_api=api,
        width=geometry["width"],
        height=geometry["height"],
        x=geometry["x"],
        y=geometry["y"],
        screen=primary_screen,
        min_size=(800, 520),
        frameless=True,
        easy_drag=False,
        background_color="#0c0c0e",
    )
    # ``debug=True`` abre uma segunda janela DevTools a cada inicialização.
    # O programa final deve abrir somente a sua janela principal.
    # O servidor local permite que o WebGL carregue GLB/texturas do cache do
    # projeto sem transformar modelos grandes em Base64 dentro da interface.
    webview.start(_check_character_catalog_in_background, debug=False, http_server=True)
