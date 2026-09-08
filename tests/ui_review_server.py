"""Servidor de revisão local com biblioteca descartável; nunca usa mods reais.

Executar: python tests/ui_review_server.py
"""
import argparse
import json
import pathlib
import sys
import tempfile
import time
import zipfile
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from unittest.mock import Mock, patch
from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main
from backend import mod_ops, operation_recovery, storage

ALLOWED = {'get_mods','get_settings','save_settings','get_characters','get_character_roster','get_types','get_tags','get_folders',
           'get_character_catalog_status','update_character_catalog',
           'get_native3d_support_status','start_native3d_support_update',
           'get_library_snapshot','find_operation','start_library_health','start_conflict_check',
           'start_full_backup_preview','start_full_backup','start_full_restore_preview','start_full_restore',
           'get_skins_for_character','get_character_skins','get_mod_details','get_mod_thumbnail',
           'get_gallery_preview','get_gallery_media',
           'classify_mod_components','get_component_diagnosis','retry_component_analysis','get_component_labels',
           'set_component_rules','toggle_component','toggle_mod','set_mods_enabled','begin_mod_install','cancel_mod_install','get_conflicts',
           'disable_conflict_owner','start_mod_import','start_complete_mod_install','start_add_mod_components','get_operation_status',
           'cancel_operation','get_operation_recoveries','recover_interrupted_operation',
           'inspect_library_health','preview_library_repair','apply_library_repair','ignore_missing_media',
           'list_pending_classifications','reanalyze_selected_components','suggest_component_relations',
           'preview_relation_suggestion','apply_relation_suggestion','preview_conflict_resolution','apply_conflict_resolution'}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT/'frontend'), **kwargs)

    def do_GET(self):
        if self.path == '/':
            html = (ROOT/'frontend/index.html').read_text(encoding='utf-8')
            bridge = '''<script>window.pywebview={api:new Proxy({}, {get:(_,name)=>(...args)=>fetch('/api/'+name,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(args)}).then(r=>r.json())})}; window.addEventListener('load',()=>window.dispatchEvent(new Event('pywebviewready')));</script>'''
            data = html.replace('<script src="app.js">',bridge+'<script src="app.js">').encode()
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(data)
        else:
            super().do_GET()

    def do_POST(self):
        name = self.path.removeprefix('/api/')
        if name not in ALLOWED:
            self.send_error(403)
            return
        args = json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
        try:
            if name in {'get_character_catalog_status', 'update_character_catalog'}:
                result = {'ok':True,'checked':name == 'update_character_catalog','changed':False,
                          'total':694,'checked_at':'2026-09-01T12:00:00+00:00'}
            else:
                result = None
            # Simula mídia lenta sem atrasar a API de metadados por consequência.
            if result is not None:
                pass
            elif name == 'get_gallery_preview':
                time.sleep(self.server.preview_delay)
            elif name == 'get_mod_details':
                time.sleep(self.server.details_delay)
            if result is None:
                result = getattr(main.Api(),name)(*args)
            if name == 'get_characters':
                for item in result: item['hero_icon_url'] = None
            if name == 'get_library_snapshot':
                for item in result['characters'] + result['mods']:
                    item['hero_icon_url'] = None
                    item['skin_icon_url'] = None
            if name == 'get_mod_details' and result:
                result['hero_icon_url'] = result['skin_icon_url'] = None
        except Exception as error:
            result = {'ok':False,'error':str(error)}
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())


def serve(preview_delay=0, details_delay=0):
    with tempfile.TemporaryDirectory(prefix='marvel-ui-review-') as temp:
        root = pathlib.Path(temp)
        values = dict(MODS_JSON=str(root/'mods.json'), SETTINGS_FILE=str(root/'settings.json'),
                      STORAGE_DIR=str(root/'library'),BACKUPS_DIR=str(root/'backups'))
        def fixture_paths(files):
            if any('sem_leitura' in str(path) for path in files):
                return []
            if any('Physics' in str(path) for path in files):
                return ['Marvel/Content/PhysicsAssets/PH_Hero.uasset']
            return ['Marvel/Content/Meshes/SK_Hero.uasset','Marvel/Content/Textures/T_Body_D.uasset']
        with patch.multiple(storage, **values), patch.object(mod_ops, '_ensure_game_operation_allowed'), patch.object(
                mod_ops, '_paths_from_bundle', side_effect=fixture_paths):
            storage.ensure_dirs()
            settings = storage.load_settings()
            settings['mods_path'] = str(root/'game')
            storage.save_settings(settings)
            sources = []
            for variant in ('Hero_Mask_On','Hero_Mask_Off','Hero_Physics'):
                folder = root/variant
                folder.mkdir()
                for ext in ('.pak','.utoc','.ucas'):
                    path = folder/(variant+ext)
                    path.write_bytes((variant+ext).encode())
                    sources.append(str(path))
            plan = mod_ops.prepare_mod_import(sources)
            variants = mod_ops.add_mod(sources, {'name':'Mod de revisão — variantes','character':'Hela','skin':'Default',
                                               '_import_plan':plan,'enabled_component_ids':[plan['components'][0]['id']]})
            mod_ops.set_mod_identity(variants['id'], 'Hela', 'Default')
            mod_ops.set_component_description(variants['id'], variants['components'][0]['id'], 'Variante de revisão')
            gallery = []
            for index, color in enumerate(('#344f65', '#455947', '#615034', '#523d60', '#663f44', '#37605f'), 1):
                image_path = root/f'Previa-{index}.png'
                image = Image.new('RGB', (800, 450), color)
                ImageDraw.Draw(image).text((50, 180), f'Galeria de revisao - imagem {index}', fill='white')
                image.save(image_path)
                gallery.append(str(image_path))
            mod_ops.add_gallery_images(variants['id'], gallery)
            mod_ops.add_mod(sources[:3], {'name':'Outro mod — conflito','character':'Hela','skin':'Default'})
            unreadable = root/'Pacote_sem_leitura.pak'
            unreadable.write_bytes(b'unsupported fixture')
            mod_ops.add_mod([str(unreadable)], {'name':'Mod com leitura pendente','character':'Storm','skin':'Default'})
            repair_mod = mod_ops.add_mod(sources[:3], {'name':'Mod para revisar cópias','character':'Luna Snow','skin':'Default'})
            for entry in repair_mod['files']:
                target = (root/'game'/repair_mod['folder']/entry['name']).resolve()
                assert target.is_relative_to(root.resolve()), 'A revisão deve usar somente a biblioteca temporária.'
                if target.suffix == '.utoc':
                    target.unlink()
                elif target.suffix == '.ucas':
                    changed = target.with_suffix('.fixture')
                    changed.write_bytes(b'conteudo alterado para revisao')
                    changed.replace(target)
            journal = operation_recovery.Journal.create('import', 'Preparação descartável de revisão')
            (pathlib.Path(journal.stage_dir('extracted'))/'sample.txt').write_text('fixture',encoding='utf-8')
            journal.release()
            archive = root/'Pacote de revisão.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for source in sources: z.write(source, str(pathlib.Path(source).relative_to(root)))
            main.window = Mock()
            exports = root/'exports'
            exports.mkdir()
            def choose_file(dialog_type, **kwargs):
                if dialog_type == main.webview.FileDialog.FOLDER:
                    return [str(exports)]
                if 'Backup completo' in str(kwargs.get('file_types', '')):
                    copies = sorted(exports.glob('marvel-manager-completo-*.zip'))
                    return [str(copies[-1])] if copies else None
                if not archive.exists():
                    with zipfile.ZipFile(archive,'w') as z:
                        for source in sources: z.write(source, str(pathlib.Path(source).relative_to(root)))
                return [str(archive)]
            main.window.create_file_dialog.side_effect = choose_file
            print('Revisão isolada em http://127.0.0.1:8765',flush=True)
            print(f'Biblioteca temporária: {root}', flush=True)
            server = ThreadingHTTPServer(('127.0.0.1',8765),Handler)
            server.preview_delay = preview_delay
            server.details_delay = details_delay
            try:
                server.serve_forever()
            finally:
                server.server_close()
                for token in list(main.pending_imports):
                    main.Api().cancel_mod_install(token)
                journal.finish('cancelled')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview-delay', type=float, default=0, help='Atraso artificial de cada miniatura, em segundos.')
    parser.add_argument('--details-delay', type=float, default=0, help='Atraso artificial dos metadados, em segundos.')
    args = parser.parse_args()
    serve(preview_delay=max(0, min(30, args.preview_delay)), details_delay=max(0, min(30, args.details_delay)))
