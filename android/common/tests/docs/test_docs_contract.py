from pathlib import Path
import sys
import unittest
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_test_docs as contract

class DocsContractTest(unittest.TestCase):
    def setUp(self):
        self.facts = {"tiers":{"fast","stability"}, "qml_tests":38, "qml_rows":52,
                      "robo_methods":13, "robo_executions":26,
                      "robo_matrices":{"Phone":(26,35)},
                      "harness_executions":26,
                      "mutation_quick":22, "mutation_extended":38}
        self.testing = "common/tests/run-tests.sh fast\ncommon/tests/run-tests.sh stability\n13 Robolectric source behaviors (26 executions), 26 granular JUnit cases. Phone (API 26/35)."
        self.coverage = "38 explicit `test_*` functions pass (52 QtTest result rows). kills 22/22 curated mutants; extended kills 38/38."
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
        self.assertTrue(any("QML count" in e for e in contract.validate(self.testing,self.coverage.replace("38 explicit","37 explicit"),self.facts)))

    def test_rejects_stale_robolectric_sdk_matrix(self):
        errors = contract.validate(
            self.testing.replace("API 26/35", "API 26/34"), self.coverage, self.facts)
        self.assertTrue(any("SDK matrix for Phone" in error for error in errors))

    def test_rejects_stale_coverage_threshold(self):
        facts = dict(self.facts)
        facts["js_thresholds"] = {"places-main": (98, 94, 97)}
        errors = contract.validate(self.testing + " places.js requires 97% lines / 94% branches / 97% functions",
                                   self.coverage, facts)
        self.assertTrue(any("places.js" in error for error in errors))

if __name__ == "__main__":
    unittest.main()
