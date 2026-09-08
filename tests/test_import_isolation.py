import hashlib
import pathlib
import shutil
import tempfile
import unittest
from unittest.mock import patch
from backend import mod_ops, operation_recovery, storage


class ImportIsolationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = pathlib.Path(temp.name)
        paths = dict(MODS_JSON=str(self.root/'mods.json'), SETTINGS_FILE=str(self.root/'settings.json'),
                     STORAGE_DIR=str(self.root/'library'), BACKUPS_DIR=str(self.root/'backups'))
        p = patch.multiple(storage, **paths)
        p.start()
        self.addCleanup(p.stop)
        storage.ensure_dirs()
        settings = storage.load_settings()
        settings['mods_path'] = str(self.root/'game')
        storage.save_settings(settings)
        p = patch.object(mod_ops, '_ensure_game_operation_allowed')
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(mod_ops, '_paths_from_bundle', return_value=['Marvel/Content/Meshes/SK_Hero.uasset'])
        p.start()
        self.addCleanup(p.stop)
        self.files = []
        self.archives = []
        for variant in ('normal','alternative'):
            folder = self.root/variant
            folder.mkdir()
            for ext in ('.pak','.utoc','.ucas'):
                path = folder/('mod'+ext)
                path.write_bytes((variant+ext).encode())
                self.files.append(str(path))
            archive = folder/'mod.zip'
            archive.write_bytes(variant.encode())
            self.archives.append(str(archive))

    def install(self, **meta):
        return mod_ops.add_mod(self.files, {'name':'Example','character':'Hela','skin':'Default',
                                           'archive_paths': self.archives, **meta})

    def test_same_names_are_isolated_and_toggle_does_not_touch_other_variant(self):
        mod = self.install()
        self.assertEqual(len(mod['components']), 2)
        self.assertEqual(len(set(e['name'] for e in mod['files'])), 6)
        private = pathlib.Path(mod_ops._storage_dir(mod))
        active = pathlib.Path(mod_ops._game_target_dir(mod, str(self.root/'game')))
        for entry, source in zip(mod['files'], self.files):
            self.assertEqual((private/entry['name']).read_bytes(), pathlib.Path(source).read_bytes())
            self.assertEqual((active/entry['name']).read_bytes(), pathlib.Path(source).read_bytes())
        a, b = mod['components']
        self.assertEqual(len(mod_ops._component_source_files(mod,a,mod_ops._mod_source_files(mod))), 3)
        result = mod_ops.toggle_component(mod['id'], a['id'])
        self.assertTrue(result['ok'])
        self.assertTrue(all(not (active/e['name']).exists() for e in a['files']))
        self.assertTrue(all((active/e['name']).is_file() for e in b['files']))
        self.assertTrue(all((private/e['name']).is_file() for e in mod['files']))
        mod_ops.toggle_component(mod['id'], a['id'])
        self.assertTrue(all((active/e['name']).is_file() for e in mod['files']))

    def test_all_components_can_start_disabled(self):
        mod = self.install(enabled_component_ids=[])
        active = pathlib.Path(mod_ops._game_target_dir(mod, str(self.root/'game')))
        self.assertFalse(list(active.rglob('*.pak')))
        self.assertEqual(mod_ops._expected_active_file_names(mod), set())

    def test_same_archive_names_are_preserved_on_remove(self):
        mod = self.install()
        private = pathlib.Path(mod_ops._storage_dir(mod))
        self.assertEqual(len(set(mod['archives'])), 2)
        self.assertEqual([(private/name).read_bytes() for name in mod['archives']], [b'normal',b'alternative'])
        mod_ops.delete_mod(mod['id'])
        self.assertTrue(all((private/name).exists() for name in mod['archives']))

    def test_legacy_flat_paths_still_resolve(self):
        component = {'files':[{'name':'mod.pak'}]}
        self.assertEqual(mod_ops._component_source_files({}, component, [self.files[0],self.files[1]]), [self.files[0]])

    def test_group_rules_switch_files_and_dependents(self):
        mod = self.install()
        a,b = mod['components']
        self.assertTrue(mod_ops.set_component_rules(mod['id'],a['id'],'roupa')['ok'])
        self.assertTrue(mod_ops.set_component_rules(mod['id'],b['id'],'roupa')['ok'])
        saved = storage.load_mods()[0]
        self.assertEqual([c['enabled'] for c in saved['components']],[False,True])
        active = pathlib.Path(mod_ops._game_target_dir(saved,str(self.root/'game')))
        self.assertTrue(all(not (active/e['name']).exists() for e in a['files']))
        self.assertTrue(mod_ops.toggle_component(mod['id'],a['id'])['ok'])
        self.assertEqual([c['enabled'] for c in storage.load_mods()[0]['components']],[True,False])
        self.assertTrue(all((active/e['name']).exists() for e in a['files']))
        self.assertTrue(all(not (active/e['name']).exists() for e in b['files']))
        self.assertTrue(mod_ops.set_component_rules(mod['id'],b['id'],'',[a['id']])['ok'])
        self.assertTrue(mod_ops.toggle_component(mod['id'],b['id'])['ok'])
        self.assertEqual([c['enabled'] for c in storage.load_mods()[0]['components']],[True,True])
        self.assertTrue(mod_ops.toggle_component(mod['id'],a['id'])['ok'])
        self.assertEqual([c['enabled'] for c in storage.load_mods()[0]['components']],[False,False])

    def test_save_failure_rolls_back_files(self):
        mod = self.install()
        before = storage.load_mods()
        with patch.object(storage,'save_mods',side_effect=OSError('disk full')):
            result = mod_ops.toggle_component(mod['id'],mod['components'][0]['id'])
        self.assertFalse(result['ok'])
        self.assertEqual(storage.load_mods(), before)
        active = pathlib.Path(mod_ops._game_target_dir(mod,str(self.root/'game')))
        self.assertTrue(all((active/e['name']).exists() for e in mod['files']))

    def test_external_variants_are_backed_up_before_rules_remove_files(self):
        mod = self.install()
        private = pathlib.Path(mod_ops._storage_dir(mod))
        self.assertTrue(private.is_relative_to(self.root))
        shutil.rmtree(private)
        mods = storage.load_mods()
        mods[0]['external'] = True
        storage.save_mods(mods)
        a,b = mod['components']
        self.assertTrue(mod_ops.set_component_rules(mod['id'],a['id'],'roupa')['ok'])
        self.assertTrue(mod_ops.set_component_rules(mod['id'],b['id'],'roupa')['ok'])
        self.assertFalse(storage.load_mods()[0]['external'])
        self.assertTrue(all((private/e['name']).exists() for e in mod['files']))
        self.assertTrue(mod_ops.toggle_component(mod['id'],a['id'])['ok'])
        active = pathlib.Path(mod_ops._game_target_dir(mod,str(self.root/'game')))
        self.assertTrue(all((active/e['name']).exists() for e in a['files']))

    def test_preview_analysis_and_install_reuse_package_reads(self):
        paths = ['Marvel/Content/Meshes/SK_Hero.uasset']
        with patch.object(mod_ops,'_paths_from_bundle',return_value=paths) as read:
            plan = mod_ops.prepare_mod_import(self.files)
            suggestion = mod_ops.analyze_mod_files(self.files, asset_paths=paths)
            mod = self.install(_import_plan=plan)
        self.assertEqual(suggestion['types'], ['Mesh'])
        self.assertEqual(len(mod['components']), 2)
        self.assertEqual(read.call_count, 2)

    def test_invalid_profile_does_not_remove_current_files(self):
        mod = self.install()
        a,b = mod['components']
        mod_ops.set_component_rules(mod['id'],a['id'],'roupa')
        mod_ops.set_component_rules(mod['id'],b['id'],'roupa')
        saved = storage.load_mods()[0]
        with self.assertRaises(ValueError):
            mod_ops._apply_saved_mod_state(saved,{'enabled':True,'components':{a['id']:True,b['id']:True}},str(self.root/'game'))
        self.assertEqual(saved,storage.load_mods()[0])
        active = pathlib.Path(mod_ops._game_target_dir(saved,str(self.root/'game')))
        self.assertTrue(all((active/e['name']).exists() for e in b['files']))

    def test_preview_reports_duplicates_without_changing_catalog(self):
        self.install()
        before = pathlib.Path(storage.MODS_JSON).read_bytes()
        plan = mod_ops.prepare_mod_import(self.files)
        preview = mod_ops.describe_mod_import(plan, self.archives)
        self.assertTrue(all(c['same_names'] for c in preview['components']))
        self.assertTrue(all(c['duplicate_of'] == ['Example'] for c in preview['components']))
        self.assertEqual(pathlib.Path(storage.MODS_JSON).read_bytes(), before)

    def test_source_change_after_preview_is_rejected(self):
        plan = mod_ops.prepare_mod_import(self.files)
        pathlib.Path(self.files[0]).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'mudou'):
            self.install(_import_plan=plan)
        self.assertEqual(storage.load_mods(), [])
        self.assertTrue(all(pathlib.Path(p).exists() for p in self.files))

    def test_append_components_keeps_new_variant_disabled_until_user_enables_it(self):
        mod = self.install()
        later = self.root / 'later'
        later.mkdir()
        sources = []
        for ext in ('.pak', '.utoc', '.ucas'):
            path = later / ('future_variant' + ext)
            path.write_bytes(('future' + ext).encode())
            sources.append(str(path))
        plan = mod_ops.prepare_mod_import(sources)
        updated = mod_ops.add_mod_components(mod['id'], sources, {'_import_plan': plan})
        self.assertEqual(updated['added_components'], 1)
        self.assertEqual(updated['skipped_duplicates'], 0)
        self.assertEqual(len(updated['components']), 3)
        added = updated['components'][-1]
        self.assertFalse(added['enabled'])
        private = pathlib.Path(mod_ops._storage_dir(updated))
        active = pathlib.Path(mod_ops._game_target_dir(updated, str(self.root / 'game')))
        self.assertTrue(all((private / entry['name']).is_file() for entry in added['files']))
        self.assertTrue(all(not (active / entry['name']).exists() for entry in added['files']))
        self.assertTrue(all((active / entry['name']).is_file() for entry in mod['files']))
        self.assertTrue(mod_ops.toggle_component(mod['id'], added['id'])['ok'])
        self.assertTrue(all((active / entry['name']).is_file() for entry in added['files']))

    def test_append_rejects_exact_duplicate_without_changing_mod(self):
        mod = self.install()
        before = storage.load_mods()
        duplicate_sources = self.files[:3]
        plan = mod_ops.prepare_mod_import(duplicate_sources)
        with self.assertRaisesRegex(ValueError, 'já existem'):
            mod_ops.add_mod_components(mod['id'], duplicate_sources, {'_import_plan': plan})
        self.assertEqual(storage.load_mods(), before)
        self.assertEqual(operation_recovery.list_pending(), [])

    def test_append_suggests_update_but_keeps_variant_until_review(self):
        mod = self.install()
        later = self.root / 'suggested-update'
        later.mkdir()
        sources = []
        for ext in ('.pak', '.utoc', '.ucas'):
            path = later / ('mod_v2' + ext)
            path.write_bytes(('version-two' + ext).encode())
            sources.append(str(path))
        result = mod_ops.add_mod_components(mod['id'], sources, {'_import_plan': mod_ops.prepare_mod_import(sources)})
        self.assertEqual(len(result['suggested_updates']), 1)
        self.assertEqual(result['suggested_updates'][0]['new_component_id'], result['added_component_ids'][0])
        saved = storage.load_mods()[0]
        self.assertEqual(len(saved['components']), 3)
        self.assertFalse(saved['components'][-1]['enabled'])
        self.assertNotIn('suggested_updates', saved)

    def test_update_preserves_identity_and_can_restore_previous_payload(self):
        mod = self.install()
        target = mod['components'][0]
        old_names = {entry['name'] for entry in target['files']}
        later = self.root / 'replacement'
        later.mkdir()
        sources = []
        for ext in ('.pak', '.utoc', '.ucas'):
            path = later / ('replacement' + ext)
            path.write_bytes(('replacement' + ext).encode())
            sources.append(str(path))
        appended = mod_ops.add_mod_components(mod['id'], sources, {'_import_plan': mod_ops.prepare_mod_import(sources)})
        added_id = appended['added_component_ids'][0]
        result = mod_ops.promote_added_component_to_update(mod['id'], added_id, target['id'])
        self.assertTrue(result['ok'])
        saved = storage.load_mods()[0]
        current = next(item for item in saved['components'] if item['id'] == target['id'])
        self.assertEqual(current['name'], target['name'])
        self.assertEqual(current['enabled'], target['enabled'])
        self.assertEqual(len(current['versions']), 1)
        self.assertTrue(current.get('content_sha256'))
        active = pathlib.Path(mod_ops._game_target_dir(saved, str(self.root/'game')))
        self.assertTrue(all((active / entry['name']).is_file() for entry in current['files']))
        self.assertTrue(all(not (active / name).exists() for name in old_names))
        version_id = current['versions'][0]['id']
        restored = mod_ops.restore_component_version(mod['id'], target['id'], version_id)
        self.assertTrue(restored['ok'])
        restored_component = next(item for item in storage.load_mods()[0]['components'] if item['id'] == target['id'])
        self.assertEqual({entry['name'] for entry in restored_component['files']}, old_names)
        self.assertTrue(all((active / name).is_file() for name in old_names))
        self.assertTrue(all(not (active / entry['name']).exists() for entry in current['files']))

    def test_remove_component_preserves_private_payload_and_can_restore_it(self):
        mod = self.install()
        component = mod['components'][1]
        private = pathlib.Path(mod_ops._storage_dir(mod))
        active = pathlib.Path(mod_ops._game_target_dir(mod, str(self.root/'game')))
        result = mod_ops.remove_component(mod['id'], component['id'])
        self.assertTrue(result['ok'])
        saved = storage.load_mods()[0]
        self.assertEqual(len(saved['components']), 1)
        self.assertTrue(all((private / entry['name']).is_file() for entry in component['files']))
        self.assertTrue(all(not (active / entry['name']).exists() for entry in component['files']))
        removed_id = saved['removed_components'][0]['id']
        restored = mod_ops.restore_removed_component(mod['id'], removed_id)
        self.assertTrue(restored['ok'])
        saved = storage.load_mods()[0]
        self.assertEqual(len(saved['components']), 2)
        self.assertTrue(all((active / entry['name']).is_file() for entry in component['files']))
        self.assertFalse(saved.get('removed_components'))

    def test_remove_refuses_last_component_and_required_component(self):
        mod = self.install()
        first, second = mod['components']
        self.assertTrue(mod_ops.set_component_rules(mod['id'], second['id'], '', [first['id']])['ok'])
        blocked = mod_ops.remove_component(mod['id'], first['id'])
        self.assertFalse(blocked['ok'])
        self.assertIn(second['name'], blocked['error'])
        self.assertTrue(mod_ops.remove_component(mod['id'], second['id'])['ok'])
        last = mod_ops.remove_component(mod['id'], first['id'])
        self.assertFalse(last['ok'])
        self.assertIn('último componente', last['error'])

    def test_import_performance_log_is_bounded_and_normalized(self):
        for index in range(35):
            result = mod_ops.record_import_performance({
                'kind': 'component_append', 'mod_id': 'mod', 'total_ms': index,
                'backend_ms': '12.5', 'reload_ms': -8,
            })
            self.assertTrue(result['ok'])
        entries = mod_ops.get_import_performance(30)
        self.assertEqual(len(entries), 30)
        self.assertEqual(entries[0]['total_ms'], 34.0)
        self.assertEqual(entries[0]['backend_ms'], 12.5)
        self.assertEqual(entries[0]['reload_ms'], 0.0)

    def test_diagnosis_explains_assets_and_missing_files(self):
        mod = self.install()
        component = mod['components'][0]
        result = mod_ops.get_component_diagnosis(mod['id'],component['id'])
        self.assertEqual(result['status'],'analyzed')
        self.assertEqual(result['evidence'][0]['source'],'assets')
        self.assertIn('SK_Hero',result['evidence'][0]['paths'][0])
        with patch.object(mod_ops,'_mod_source_files',return_value=[]):
            self.assertEqual(mod_ops.get_component_diagnosis(mod['id'],component['id'])['status'],'missing')


if __name__ == '__main__': unittest.main()
