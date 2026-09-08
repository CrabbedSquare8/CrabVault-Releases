import copy
import unittest
from unittest.mock import patch
from backend import mod_ops


class ConflictDiagnosisTests(unittest.TestCase):
    def mod(self, ident, character='Hela', priority=1):
        return {'id':ident,'name':ident,'character':character,'skin':'Default','priority':priority,'enabled':True,
                'files':[{'name':ident+'.pak'}], 'components':[
                    {'id':ident+'c','name':ident,'enabled':True,'type':'Mesh','types':['Mesh'],'files':[{'name':ident+'.pak'}]}]}

    def conflicts(self, mods, assets=None):
        assets = assets or ['Marvel/Content/Meshes/SK_Hero.uasset']
        with patch.object(mod_ops.storage,'load_mods',return_value=copy.deepcopy(mods)), patch.object(
                mod_ops.storage,'save_mods') as save, patch.object(mod_ops,'_mod_source_files',side_effect=lambda m:[e['name'] for e in m['files']]), patch.object(
                mod_ops,'_cached_bundle_paths',return_value=(assets,False)):
            return mod_ops.get_conflicts()

    def test_different_identity_keeps_legacy_policy(self):
        result = self.conflicts([self.mod('a'),self.mod('b','Storm',5)])
        self.assertFalse(result['conflicts'])

    def test_same_identity_reports_overlap_and_priority(self):
        result = self.conflicts([self.mod('a'),self.mod('b',priority=5)])
        self.assertEqual(len(result['conflicts']),1)
        conflict = result['conflicts'][0]
        self.assertEqual(conflict['winner']['mod_id'],'b')
        self.assertEqual(conflict['owners'][0]['files'],['b.pak'])
        self.assertIn('não altera',result['priority_note'])

    def test_equal_priorities_have_no_invented_winner(self):
        conflict = self.conflicts([self.mod('a'),self.mod('b')])['conflicts'][0]
        self.assertTrue(conflict['tie'])
        self.assertIsNone(conflict['winner'])

    def test_extra_mesh_stays_accompaniment_without_principal_label(self):
        mod = self.mod('a')
        b = self.mod('b')
        mod['components'] += b['components']
        mod['files'] += b['files']
        self.assertFalse(self.conflicts([mod])['conflicts'])

    def test_two_explicit_principals_of_same_mod_conflict(self):
        mod = self.mod('a')
        b = self.mod('b')
        b['components'][0]['description'] = 'Principal'
        mod['components'] += b['components']
        mod['files'] += b['files']
        self.assertEqual(len(self.conflicts([mod])['conflicts']),1)

    def test_different_skin_does_not_conflict(self):
        a, b = self.mod('a'), self.mod('b')
        b['skin'] = 'Other skin'
        self.assertFalse(self.conflicts([a,b])['conflicts'])

    def test_identity_must_be_complete(self):
        a, b = self.mod('a',character=''), self.mod('b',character='')
        self.assertFalse(self.conflicts([a,b])['conflicts'])

    def test_hybrid_physics_is_ignored_like_legacy_detector(self):
        a, b = self.mod('a'), self.mod('b')
        b['components'][0]['name'] = 'Hero Physics'
        b['components'][0]['types'] = ['Mesh', 'Physics']
        result = self.conflicts([a,b])
        self.assertFalse(result['conflicts'])
        self.assertEqual(result['ignored_physics_components'], 1)

    def test_manual_conflicts_still_cross_identity_boundaries(self):
        a, b = self.mod('a'), self.mod('b', character='Storm')
        a['manual_conflicts'] = ['b']
        result = self.conflicts([a,b])
        self.assertEqual(len(result['conflicts']),1)
        self.assertEqual(result['conflicts'][0]['kind'],'manual')

    def test_unrelated_automatic_pairs_do_not_hide_a_manual_conflict(self):
        a, b = self.mod('a'), self.mod('b')
        c, d = self.mod('c', character='Storm'), self.mod('d', character='Storm')
        a['manual_conflicts'] = ['c']
        result = self.conflicts([a, b, c, d])
        manual = [item for item in result['conflicts'] if item['kind'] == 'manual']
        self.assertEqual(len(manual), 1)
        self.assertEqual({owner['mod_id'] for owner in manual[0]['owners']}, {'a', 'c'})

    def test_dependency_metadata_does_not_promote_an_accompaniment(self):
        mod = self.mod('a')
        b = self.mod('b')
        b['components'][0]['requires'] = ['ac']
        mod['components'] += b['components']
        mod['files'] += b['files']
        self.assertFalse(self.conflicts([mod])['conflicts'])

    def test_explicit_principals_keep_legacy_conflict_despite_dependency_metadata(self):
        mod = self.mod('a')
        b = self.mod('b')
        b['components'][0].update(description='Principal', requires=['ac'])
        mod['components'] += b['components']
        mod['files'] += b['files']
        self.assertEqual(len(self.conflicts([mod])['conflicts']), 1)

    def test_alternative_group_does_not_change_legacy_primary_policy(self):
        mod = self.mod('a')
        b = self.mod('b')
        mod['components'][0]['exclusive_group'] = 'roupa'
        b['components'][0]['exclusive_group'] = 'roupa'
        mod['components'] += b['components']
        mod['files'] += b['files']
        self.assertFalse(self.conflicts([mod])['conflicts'])

    def test_disabled_component_does_not_conflict(self):
        a,b = self.mod('a'),self.mod('b')
        b['components'][0]['enabled'] = False
        self.assertFalse(self.conflicts([a,b])['conflicts'])


if __name__ == '__main__': unittest.main()
