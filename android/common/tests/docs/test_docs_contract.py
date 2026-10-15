from pathlib import Path
import sys
import unittest
import tempfile
import copy
import json
sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_test_docs as contract

class DocsContractTest(unittest.TestCase):
    def setUp(self):
        self.facts = {"tiers":{"fast","stability"}, "qml_tests":38, "qml_rows":52,
                      "robo_methods":13, "robo_executions":26,
                      "robo_matrices":{"Phone":(26,35)},
                      "robo_classes":{"org/overte/phone/ExampleRobolectricTest.java":
                                      {"behaviors":13,"sdks":[26,35]}},
                      "harness_executions":26,
                      "mutation_quick":22, "mutation_extended":38}
        self.testing = "common/tests/run-tests.sh fast\ncommon/tests/run-tests.sh stability\n13 Robolectric source behaviors (26 executions), 26 granular JUnit cases. Phone (API 26/35)."
        self.coverage = "38 explicit `test_*` functions pass (52 QtTest result rows). kills 22/22 curated mutants; extended kills 38/38."
        self.testing += self.profile(self.facts, "android-parent")

    def profile(self, facts, scope):
        return ("\n" + contract.PROFILE_START + "\n```json\n" +
                json.dumps(contract.expected_profile(facts, scope)) +
                "\n```\n" + contract.PROFILE_END)
    def test_valid_fixture(self):
        self.assertEqual([], contract.validate(self.testing,self.coverage,self.facts))

    def test_actual_include_patterns_expand_all_downstream_tests(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prefix = root / 'phone/apps/phoneInterface/src/test/java/org/overte/phone'
            prefix.mkdir(parents=True)
            first = prefix / 'FirstRobolectricTest.java'
            second = prefix / 'SecondRobolectricTest.java'
            first.write_text('@Test void one() {}')
            second.write_text('@Test void two() {}')
            pattern = 'org/overte/phone/*RobolectricTest.java'
            self.assertEqual(contract.resolve_test_includes(root, [pattern, pattern]), [first, second])
            with self.assertRaisesRegex(ValueError, 'at least once'):
                contract.resolve_test_includes(root, ['org/overte/phone/MissingRobolectricTest.java'])
            duplicate = root / 'other/apps/otherInterface/src/test/java/org/overte/phone/FirstRobolectricTest.java'
            duplicate.parent.mkdir(parents=True)
            duplicate.write_text(first.read_text())
            with self.assertRaisesRegex(ValueError, 'duplicate class'):
                contract.resolve_test_includes(root, [pattern])
    def test_rejects_stale_tier(self):
        self.assertTrue(any("stability" in e for e in contract.validate(self.testing.replace("stability","stable"),self.coverage,self.facts)))
    def test_rejects_stale_count(self):
        self.assertTrue(contract.validate(self.testing.replace('"qmlFunctions": 38', '"qmlFunctions": 37'), self.coverage, self.facts))

    def test_rejects_stale_robolectric_sdk_matrix(self):
        errors = contract.validate(
            self.testing.replace('[26, 35]', '[26, 34]'), self.coverage, self.facts)
        self.assertTrue(any("SDK matrix" in error for error in errors))

    def test_product_profile_is_authoritative_over_matching_parent_numbers(self):
        stale = self.profile(self.facts, "android-phone").replace('"junitCases": 26', '"junitCases": 25')
        self.assertTrue(contract.validate(self.testing, self.coverage, self.facts, stale))
        own = self.profile(self.facts, "android-phone")
        self.assertEqual([], contract.validate(self.testing, self.coverage, self.facts, own))

    def test_missing_product_profile_cannot_hide_extended_checkout(self):
        facts = copy.deepcopy(self.facts)
        facts['robo_classes']['org/overte/phone/FocusRobolectricTest.java'] = {"behaviors":9,"sdks":[26,35]}
        facts['robo_methods'] += 9
        facts['robo_executions'] += 18
        facts['harness_executions'] += 18
        self.assertTrue(contract.validate(self.testing, self.coverage, facts))
        self.assertEqual([], contract.validate(self.testing, self.coverage, facts, self.profile(facts, "android-phone")))

    def test_product_matrix_and_exact_class_inventory_are_bound(self):
        own = self.profile(self.facts, "android-phone")
        for altered in (own.replace('[26, 35]', '[35]'), own.replace('ExampleRobolectricTest', 'DifferentRobolectricTest')):
            self.assertTrue(contract.validate(self.testing, self.coverage, self.facts, altered))

    def test_invalid_product_profile_never_falls_back(self):
        own = self.profile(self.facts, "android-phone")
        for altered in (own + own, own.replace(contract.PROFILE_END, ''),
                        own.replace('"scope": "android-phone"', '"scope": "android-parent"'),
                        own.replace('"qmlFunctions": 38', '"qmlFunctions": 38, "qmlFunctions": 38'),
                        own.replace('"behaviors": 13', '"behaviors": true')):
            self.assertTrue(contract.validate(self.testing, self.coverage, self.facts, altered))

    def test_rejects_stale_coverage_threshold(self):
        facts = dict(self.facts)
        facts["js_thresholds"] = {"places-main": (98, 94, 97)}
        errors = contract.validate(self.testing + " places.js requires 97% lines / 94% branches / 97% functions",
                                   self.coverage, facts)
        self.assertTrue(any("places.js" in error for error in errors))

if __name__ == "__main__":
    unittest.main()
