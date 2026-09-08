import json
import pathlib
import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from backend import mod_ops, storage


class StorageSafetyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = pathlib.Path(temp.name)
        paths = dict(MODS_JSON=str(self.root/'mods.json'), SETTINGS_FILE=str(self.root/'settings.json'),
                     STORAGE_DIR=str(self.root/'library'), BACKUPS_DIR=str(self.root/'backups'))
        patcher = patch.multiple(storage, **paths)
        patcher.start()
        self.addCleanup(patcher.stop)
        storage.ensure_dirs()
        storage.save_mods([{'id':'a','name':'Mod','tags':[], 'components':[{'id':'c','enabled':True,'types':['Unknown']}]}])

    def test_atomic_replace_failure_preserves_valid_catalog(self):
        before = (self.root/'mods.json').read_bytes()
        mods = storage.load_mods()
        mods[0]['name'] = 'New'
        with patch.object(storage.os, 'replace', side_effect=OSError('locked')):
            with self.assertRaises(OSError): storage.save_mods(mods)
        self.assertEqual((self.root/'mods.json').read_bytes(), before)
        self.assertFalse(list(self.root.glob('.catalog-*.tmp')))

    def test_independent_concurrent_edits_are_merged(self):
        a, b = storage.load_mods(), storage.load_mods()
        a[0]['components'][0]['types'] = ['Mesh']
        b[0]['components'][0]['enabled'] = False
        b[0]['name'] = 'Renamed'
        storage.save_mods(a)
        storage.save_mods(b)
        saved = storage.load_mods()[0]
        self.assertEqual(saved['name'], 'Renamed')
        self.assertEqual(saved['components'][0], {'id':'c','enabled':False,'types':['Mesh']})
        b[0]['tags'] = ['next']
        storage.save_mods(b)
        self.assertEqual(storage.load_mods()[0]['components'][0]['types'], ['Mesh'])

    def test_same_field_conflict_is_reported(self):
        a, b = storage.load_mods(), storage.load_mods()
        a[0]['name'], b[0]['name'] = 'A', 'B'
        storage.save_mods(a)
        with self.assertRaises(storage.ConcurrentUpdateError): storage.save_mods(b)
        self.assertEqual(storage.load_mods()[0]['name'], 'A')

    def test_deleted_record_is_not_resurrected(self):
        a, b = storage.load_mods(), storage.load_mods()
        a.clear()
        storage.save_mods(a)
        b[0]['name'] = 'Late result'
        with self.assertRaises(storage.ConcurrentUpdateError): storage.save_mods(b)
        self.assertEqual(storage.load_mods(), [])

    def test_delete_field_and_concurrent_append(self):
        a, b = storage.load_mods(), storage.load_mods()
        del a[0]['tags']
        b.append({'id':'b','name':'Other'})
        storage.save_mods(b)
        storage.save_mods(a)
        self.assertNotIn('tags', storage.load_mods()[0])
        self.assertEqual(len(storage.load_mods()), 2)

    def test_settings_merge_independent_fields(self):
        a, b = storage.load_settings(), storage.load_settings()
        a['preview_volume'], b['theme_mode'] = .2, 'light'
        storage.save_settings(a)
        storage.save_settings(b)
        self.assertEqual(storage.load_settings()['preview_volume'], .2)
        self.assertEqual(storage.load_settings()['theme_mode'], 'light')

    def test_import_source_preferences_have_safe_existing_behavior_defaults(self):
        settings = storage.load_settings()
        self.assertTrue(settings['preserve_import_archives'])
        self.assertTrue(settings['delete_import_sources_after_success'])
        saved = mod_ops.save_settings({
            'preserve_import_archives': False,
            'delete_import_sources_after_success': False,
        })
        self.assertFalse(saved['preserve_import_archives'])
        self.assertFalse(saved['delete_import_sources_after_success'])

    def test_onboarding_preferences_default_and_save_independently(self):
        settings = storage.load_settings()
        self.assertEqual(settings['ui_language'], 'pt-BR')
        self.assertFalse(settings['language_selected'])
        self.assertFalse(settings['tutorial_completed'])
        saved = mod_ops.save_settings({
            'ui_language': 'en', 'language_selected': True, 'tutorial_completed': True,
        })
        self.assertEqual(saved['ui_language'], 'en')
        self.assertTrue(saved['language_selected'])
        self.assertTrue(saved['tutorial_completed'])

    def test_threads_preserve_all_independent_changes(self):
        barrier = threading.Barrier(6)
        def edit(index):
            mods = storage.load_mods()
            mods[0][f'field_{index}'] = index
            barrier.wait(timeout=10)
            storage.save_mods(mods)
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(edit,range(6)))
        saved = storage.load_mods()[0]
        self.assertTrue(all(saved[f'field_{i}'] == i for i in range(6)))


if __name__ == '__main__': unittest.main()
