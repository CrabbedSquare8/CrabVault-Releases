import copy
import unittest
from backend import component_rules


class ComponentRulesTests(unittest.TestCase):
    def fixture(self):
        return [{'id':'a','enabled':True,'exclusive_group':'Roupa'},
                {'id':'b','enabled':False,'exclusive_group':'roupa'},
                {'id':'eyes','enabled':True,'requires':['a']},
                {'id':'effect','enabled':False,'requires':['eyes']}]

    def test_alternative_disables_previous_and_its_dependents(self):
        result = component_rules.changed_state(self.fixture(), 'b', True)
        self.assertEqual([c['enabled'] for c in result], [False,True,False,False])

    def test_dependency_activates_transitive_requirements(self):
        components = self.fixture()
        for c in components: c['enabled'] = False
        result = component_rules.changed_state(components,'effect',True)
        self.assertEqual([c['enabled'] for c in result], [True,False,True,True])

    def test_disable_requirement_disables_transitive_dependents(self):
        components = self.fixture()
        components[-1]['enabled'] = True
        result = component_rules.changed_state(components,'a',False)
        self.assertFalse(any(c['enabled'] for c in result))

    def test_cycle_rejected_without_mutation(self):
        components = self.fixture()
        components[0]['requires'] = ['effect']
        before = copy.deepcopy(components)
        with self.assertRaisesRegex(ValueError,'ciclo'): component_rules.changed_state(components,'a',True)
        self.assertEqual(components,before)

    def test_incompatible_dependency_closure_rejected(self):
        components = self.fixture()
        components[2]['requires'] = ['a','b']
        with self.assertRaisesRegex(ValueError,'incompatíveis'): component_rules.validate(components)

    def test_missing_dependency_rejected(self):
        components = self.fixture()
        components[2]['requires'] = ['deleted']
        with self.assertRaisesRegex(ValueError,'não existe'): component_rules.validate(components)

    def test_legacy_without_rules_retains_other_switches(self):
        components = [{'id':'a','enabled':True},{'id':'b','enabled':True}]
        result = component_rules.changed_state(components,'a',False)
        self.assertEqual(result,[{'id':'a','enabled':False},{'id':'b','enabled':True}])


if __name__ == '__main__': unittest.main()
