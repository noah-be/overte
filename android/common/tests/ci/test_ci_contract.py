from pathlib import Path
import unittest

import validate_ci_contract as contract


VALID_ACTION = "    - uses: actions/checkout@" + ("a" * 40) + " # v4\n"
VALID_WORKFLOW = VALID_ACTION + """
    - name: Install Qt Quick test runtime
      run: |
        apt-get install qtdeclarative5-dev-tools qml-module-qttest qml-module-qtquick2 \\
          qml-module-qtquick-controls qml-module-qtquick-controls2 \\
          qml-module-qtquick-layouts qml-module-qtquick-window2
    - name: next
      run: python3 ../tests/run-tests.py --profile android-fast
    - run: python3 ../tests/run-tests.py --profile android-contracts
    - run: python3 ../tests/run-tests.py --profile android-regression
    - run: python3 ../tests/run-tests.py --profile android-mutation
    - run: python3 ../tests/run-tests.py --profile android-mutation-extended
    - run: python3 ../tests/run-tests.py --profile android-stability
    - run: python3 ../tests/run-tests.py --profile android-endurance
      path: |
        android/build/test-results/suite/
        android/build/test-results/suite/
        android/build/test-results/suite/
        android/build/test-results/suite/TEST-android-mutation.xml
        android/build/test-results/suite/TEST-android-mutation-extended.xml
        android/common/tests/robolectric/build/test-results/test/
        android/build/test-results/native/
        android/build/test-results/javascript/
        android/build/test-results/qml/
        android/build/test-results/suite/TEST-android-stability.xml
        android/build/test-results/suite/TEST-android-endurance.xml
        android/build/test-results/qml-endurance/TEST-qml-endurance.xml
        android/build/reports/mutation/critical-policies-extended.json
      if-no-files-found: error
"""

PERIODIC_WORKFLOW = """
  stability:
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    steps:
      - run: python3 ../tests/run-tests.py --profile android-stability
      - if: always()
        continue-on-error: true
  endurance:
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    steps:
      - env:
          OVERTE_JS_ENDURANCE_CYCLES: 100
          OVERTE_NATIVE_ENDURANCE_CYCLES: 1000
          OVERTE_REQUIRE_QML_TESTS: 1
        run: python3 ../tests/run-tests.py --profile android-endurance
      - if: always()
        continue-on-error: true
"""


class CiContractTest(unittest.TestCase):
    def test_valid_fixture(self):
        self.assertEqual([], contract.validate_workflow(VALID_WORKFLOW))

    def test_rejects_movable_action_tag(self):
        errors = contract.validate_actions("- uses: actions/checkout@v4\n")
        self.assertTrue(any("full 40-character" in error for error in errors))
        errors = contract.validate_actions("- uses: actions/checkout\n")
        self.assertTrue(any("full 40-character" in error for error in errors))

    def test_rejects_missing_controls_one_and_junit_path(self):
        broken = VALID_WORKFLOW.replace("qml-module-qtquick-controls ", "")
        broken = broken.replace("android/build/test-results/suite/TEST-android-mutation-extended.xml\n", "")
        errors = contract.validate_workflow(broken)
        self.assertTrue(any("qml-module-qtquick-controls" in error for error in errors))
        self.assertTrue(any("mutation-extended.xml" in error for error in errors))

    def test_rejects_missing_tier_command(self):
        errors = contract.validate_workflow(
            VALID_WORKFLOW.replace("--profile android-contracts", "--profile android-typo"))
        self.assertTrue(any("contracts" in error for error in errors))

    def test_rejects_wrong_wrapper_checksum(self):
        self.assertEqual([], contract.validate_wrapper(
            "distributionSha256Sum=" + contract.EXPECTED_GRADLE_SHA))
        self.assertTrue(contract.validate_wrapper("distributionSha256Sum=" + ("0" * 64)))

    def test_rejects_lenient_or_incomplete_robolectric_locking(self):
        build = "dependencyLocking { lockAllConfigurations(); lockMode = LockMode.STRICT }"
        lock = "org.robolectric:robolectric:4.16.1=testRuntimeClasspath\n"
        self.assertEqual([], contract.validate_robolectric(build, lock))
        self.assertTrue(contract.validate_robolectric(
            build.replace("STRICT", "LENIENT"), lock))
        self.assertTrue(contract.validate_robolectric(build, "# empty\n"))

    def test_periodic_jobs_are_schedule_or_dispatch_only_and_scaled(self):
        self.assertEqual([], contract.validate_periodic_jobs(PERIODIC_WORKFLOW))
        broken = PERIODIC_WORKFLOW.replace(contract.PERIODIC_CONDITION,
                                           "github.event_name == 'pull_request'", 1)
        self.assertTrue(any("stability must run only" in error
                            for error in contract.validate_periodic_jobs(broken)))
        broken = PERIODIC_WORKFLOW.replace("OVERTE_NATIVE_ENDURANCE_CYCLES: 1000", "")
        self.assertTrue(any("NATIVE_ENDURANCE" in error
                            for error in contract.validate_periodic_jobs(broken)))

    def test_actual_workflow_event_matrix_and_parallel_needs(self):
        workflow = (Path(__file__).resolve().parents[4] /
                    ".github/workflows/android-tests.yml").read_text(encoding="utf-8")
        required = {"fast", "contracts", "coverage"}
        periodic = {"mutation-extended", "stability", "endurance"}
        self.assertEqual(required, contract.workflow_event_matrix(workflow, "pull_request"))
        self.assertEqual(required | {"regression"},
                         contract.workflow_event_matrix(workflow, "push"))
        self.assertEqual(required | periodic | {"regression"},
                         contract.workflow_event_matrix(workflow, "schedule"))
        self.assertEqual(required | periodic | {"regression"},
                         contract.workflow_event_matrix(workflow, "workflow_dispatch", True))
        self.assertEqual(required | periodic,
                         contract.workflow_event_matrix(workflow, "workflow_dispatch", False))
        self.assertTrue(contract.quick_mutation_runs("pull_request"))
        self.assertTrue(contract.quick_mutation_runs("push"))
        self.assertFalse(contract.quick_mutation_runs("schedule"))
        self.assertFalse(contract.quick_mutation_runs("workflow_dispatch"))
        self.assertEqual([], contract.validate_workflow_topology(workflow))

    def test_topology_rejects_optional_gate_dependency_and_timeout_regression(self):
        workflow = (Path(__file__).resolve().parents[4] /
                    ".github/workflows/android-tests.yml").read_text(encoding="utf-8")
        broken = workflow.replace("needs: [fast, contracts, coverage]",
                                  "needs: [fast, contracts, coverage, regression]", 1)
        self.assertTrue(any("depend only" in error
                            for error in contract.validate_workflow_topology(broken)))
        broken = workflow.replace("timeout-minutes: 45", "timeout-minutes: 40", 1)
        self.assertTrue(any("stability timeout hierarchy" in error
                            for error in contract.validate_workflow_topology(broken)))


if __name__ == "__main__":
    unittest.main()
