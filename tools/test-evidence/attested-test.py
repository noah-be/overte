#!/usr/bin/env python3
"""Offline original-runtime admission and zero-execution terminal regressions."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import attested as A
import execution
import inputs
import runtime


NOW = datetime(2026, 10, 15, 16, 0, tzinfo=timezone.utc)
QUALIFIED = "2026-10-15T15:00:00Z"
EXPIRES = "2026-10-16T15:00:00Z"
HASH = "sha256:" + "a" * 64


class RuntimeFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="overte-attested-policy-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        required, manifests = runtime._requirement_inventory(A.ROOT)
        for relative in {*runtime._TRUSTED_EXECUTION_FILES, *A._CONSUMER_FILES, *manifests}:
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((A.ROOT / relative).read_bytes())
        self.policy = json.loads((self.root / A.POLICY).read_text())
        # Explicit legacy fixture, independent of a future protected-only epoch.
        self.policy.update(enabled=True,epoch='legacy-admission-fixture-v1',not_before='2026-10-15T00:00:00Z')
        self.policy['flags'].update(git_process_overrides='maintenance-disabled',LC_ALL='')
        self.write_policy()
        self.environment = {
            "schema": 1, "profile": "ubuntu24-host-qt5-qt6-v1",
            "os": {"architecture": "x86_64", "distribution": "ubuntu", "version": "24.04", "kernel": "6.17.0-azure",
                "namespace": {"apparmor_restrict_unprivileged_userns": "0", "max_user_namespaces": "63838"},
                "runner": {"ImageOS": "ubuntu24", "ImageVersion": "20261004.327.1", "RUNNER_ENVIRONMENT": "github-hosted"},
                "timezone_digest": HASH},
            "python": {"implementation": "CPython", "version": "3.12.15", "executable_digest": HASH, "library_digest": HASH,
                "flags": deepcopy(A._PYTHON_FLAGS), "packages": required,
                "process_lookup": {"aliases": ["python", "python3"], "include_system_site_packages": False,
                                   "mode": "controller-virtualenv", "user_site_enabled": False}},
            "tools": {name: {"version": "Reviewed fixture 1.0", "executable_digest": HASH} for name in runtime._COMMANDS},
            "qt": {"modules": {name: "5.15.13" if name.startswith("Qt5") else "6.4.2" for name in runtime._QT_MODULES},
                   "tools": {name: HASH for name in ("Qt5-moc", "Qt6-moc", "qmltestrunner")}},
            "glm": {"header_digest": HASH, "configuration_digest": HASH},
            "system_packages": {"libglm-dev": "1.0.1+ds-3", "libqt6core6t64:amd64": "6.4.2+dfsg-21.1build5"},
            "flags": deepcopy(self.policy["flags"]),
        }
        for name, version in {"node": "v22.23.3", "npm": "10.9.9", "java": "openjdk 17.0.20.1 2026-08-18", "javac": "javac 17.0.20.1"}.items():
            self.environment["tools"][name]["version"] = version
        self.bind_controller()

    def write_policy(self):
        (self.root / A.POLICY).write_text(json.dumps(self.policy, indent=2) + "\n")

    def bind_controller(self):
        _, manifests = runtime._requirement_inventory(self.root)
        self.environment["trusted_execution"] = runtime._controller_file_hashes(manifests, self.root)

    def admit(self, environment=None, qualified=QUALIFIED, expires=EXPIRES, now=NOW):
        return A.validate_environment(self.environment if environment is None else environment, qualified, expires, now, root=self.root)

    def isolated(self, *, certificate=False):
        self.policy['flags'].update(git_process_overrides='maintenance-disabled-safe-work', LC_ALL='C.UTF-8')
        self.write_policy(); self.environment['flags'] = deepcopy(self.policy['flags']); self.bind_controller()
        self.environment.update(schema=inputs.ISOLATED_FULL_SCHEMA, profile=inputs.ISOLATED_FULL_PROFILE,
            prepared={'schema': 1, 'external_inputs': [inputs.ISOLATED_CACERTS] if certificate else [],
                'roots': dict.fromkeys((inputs.ISOLATED_VENV, inputs.ISOLATED_JDK,
                    '/opt/hostedtoolcache/Python/3.12.15/x64', '/opt/hostedtoolcache/node/22.23.3/x64',
                    *((inputs.ISOLATED_CACERTS,) if certificate else ())), HASH)})
        return self.environment


class AdmissionTests(RuntimeFixture):
    def test_isolated_work_exception_needs_separate_source_capability_and_exact_trusted_policy(self):
        self.isolated()
        with patch.object(A,'ISOLATED_ADMISSION_READY',False), self.assertRaises(A.AttestedReuseUnavailable):
            A.validate_environment(self.environment,QUALIFIED,EXPIRES,NOW,root=self.root,isolated=True)
        with patch.object(A,'ISOLATED_ADMISSION_READY',True):
            value=A.validate_environment(self.environment,QUALIFIED,EXPIRES,NOW,root=self.root,isolated=True)
            self.assertEqual(value['environment_digest'],A._digest(self.environment))
            with self.assertRaises(A.AttestedReuseUnavailable):self.admit()
            for variant in ('maintenance-disabled','wildcard-safe-directory','none'):
                self.policy['flags']['git_process_overrides']=variant;self.write_policy()
                self.environment['flags']=deepcopy(self.policy['flags']);self.bind_controller()
                with self.subTest(variant=variant),self.assertRaises(A.AttestedReuseUnavailable):
                    A.validate_environment(self.environment,QUALIFIED,EXPIRES,NOW,root=self.root,isolated=True)

    def test_isolated_locale_must_match_actual_fixed_namespace_before_runtime_admission(self):
        self.policy['flags'].update(git_process_overrides='maintenance-disabled-safe-work', LC_ALL='C.UTF-8')
        with patch.object(A,'ISOLATED_ADMISSION_READY',True):
            self.write_policy()
            self.assertEqual(A.load_policy(self.root,isolated=True)['flags'],self.policy['flags'])
            for name,value in (('LANG','C'),('LC_ALL',''),('LC_CTYPE','C.UTF-8'),('TZ','UTC')):
                original=self.policy['flags'][name]
                self.policy['flags'][name]=value;self.write_policy()
                with self.subTest(name=name),self.assertRaises(A.AttestedReuseUnavailable):
                    A.load_policy(self.root,isolated=True)
                self.policy['flags'][name]=original
        self.assertFalse(A.ACTIVATION_READY)

    def test_isolated_generation_requires_every_prepared_identity_and_retains_original_without_queries(self):
        self.isolated(certificate=True)
        original = deepcopy(self.environment)
        with (patch.object(A, 'ISOLATED_ADMISSION_READY', True),
              patch.object(runtime, 'capture_isolated_host_environment', side_effect=AssertionError('unused consumer E')),
              patch.object(runtime, '_command', side_effect=AssertionError('no consumer tool queries'))):
            value = A.validate_environment(original, QUALIFIED, EXPIRES, NOW, root=self.root, isolated=True)
            self.assertEqual(value['environment_digest'], A._digest(original))
            self.assertEqual(original, self.environment)
            for mutation in ('legacy', 'prepared', 'extra', 'root', 'certificate', 'external', 'digest', 'version'):
                changed = deepcopy(original)
                if mutation == 'legacy':
                    changed.update(schema=1, profile='ubuntu24-host-qt5-qt6-v1'); changed.pop('prepared')
                elif mutation == 'prepared':changed.pop('prepared')
                elif mutation == 'extra':changed['prepared']['unexpected'] = True
                elif mutation == 'root':changed['prepared']['roots']['/unknown'] = HASH
                elif mutation == 'certificate':changed['prepared']['roots'].pop(inputs.ISOLATED_CACERTS)
                elif mutation == 'external':changed['prepared']['external_inputs'] = []
                elif mutation == 'digest':changed['prepared']['roots'][inputs.ISOLATED_VENV] = 'unknown'
                else:changed['python']['version'] = '3.12.99'
                with self.subTest(mutation=mutation), self.assertRaises(A.AttestedReuseUnavailable):
                    A.validate_environment(changed, QUALIFIED, EXPIRES, NOW, root=self.root, isolated=True)
            changed = deepcopy(original)
            changed['prepared']['roots'][inputs.ISOLATED_CACERTS] = 'sha256:' + 'b' * 64
            other = A.validate_environment(changed, QUALIFIED, EXPIRES, NOW, root=self.root, isolated=True)
            self.assertNotEqual(value['environment_digest'], other['environment_digest'])

    def test_original_environment_is_retained_without_measuring_or_installing_consumer(self):
        original = deepcopy(self.environment)
        with patch.object(runtime, "capture_host_environment", side_effect=AssertionError("unused VM")), \
                patch.object(runtime, "_command", side_effect=AssertionError("no runtime tool probes")):
            value = self.admit()
        self.assertEqual(self.environment, original)
        self.assertEqual(value["environment_digest"], A._digest(original))
        self.assertEqual(value["policy"]["epoch"], self.policy["epoch"])

    def test_disabled_trusted_policy_cannot_admit_original_environment(self):
        self.policy["enabled"] = False; self.write_policy(); self.bind_controller()
        with self.assertRaises(A.AttestedReuseUnavailable): self.admit()

    def test_policy_epoch_flags_controller_and_requirement_changes_invalidate_original_proof(self):
        original = deepcopy(self.environment)
        for relative in (A.POLICY, "tools/test-evidence/inputs.py", "tests/run-project-tests.py", "tests/requirements-repository.txt"):
            path = self.root / relative
            content = path.read_bytes()
            if relative == A.POLICY:
                self.policy["epoch"] = "next-reviewed-generation"; self.write_policy()
            else:
                path.write_bytes(content + b"\n# Reviewed source change\n")
            with self.subTest(path=relative), self.assertRaises(A.AttestedReuseUnavailable): self.admit(original)
            path.write_bytes(content)

    def test_original_lifetime_epoch_and_expiry_are_never_renewed(self):
        for qualified, expires, now in ((QUALIFIED, EXPIRES, datetime(2026, 10, 16, 15, tzinfo=timezone.utc)),
                                        ("2026-10-14T15:00:00Z", EXPIRES, NOW),
                                        (QUALIFIED, "2026-10-20T15:00:00Z", NOW),
                                        ("2026-10-15T17:00:00Z", EXPIRES, NOW)):
            with self.subTest(qualified=qualified, expires=expires), self.assertRaises(A.AttestedReuseUnavailable):
                self.admit(qualified=qualified, expires=expires, now=now)

    def test_unknown_missing_noncanonical_and_incompatible_runtime_data_fail(self):
        cases = [lambda x: x.update(extra="unknown"), lambda x: x.update(schema=True),
                 lambda x: x["tools"].pop("node"), lambda x: x["tools"]["node"].update(version="v24.21.0"),
                 lambda x: x["tools"]["java"].update(version="openjdk 21.0.8 2026-07-01"),
                 lambda x: x["python"].update(version="3.13.1"), lambda x: x["python"]["flags"].update(optimize=1),
                 lambda x: x["python"]["process_lookup"].update(include_system_site_packages=True),
                 lambda x: x["python"]["process_lookup"].update(user_site_enabled=True),
                 lambda x: x["python"]["flags"].update(safe_path=0),
                 lambda x: x["flags"].update(UNKNOWN_FLAG="1"), lambda x: x["flags"].update(QT_QUICK_BACKEND="opengl"),
                 lambda x: x["flags"].update(OVERTE_GOTO_TEST_QT="Qt5"),
                 lambda x: x["qt"]["modules"].update(Qt6Quick="6.8.1"),
                 lambda x: x["os"]["runner"].update(RUNNER_ENVIRONMENT="self-hosted"),
                 lambda x: x["os"]["namespace"].update(apparmor_restrict_unprivileged_userns="1"),
                 lambda x: x["system_packages"].clear(), lambda x: x["glm"].pop("header_digest"),
                 lambda x: x["python"]["packages"].update(pillow="0.0.0"),
                 lambda x: x["tools"]["node"].update(executable_digest="unknown")]
        for change in cases:
            environment = deepcopy(self.environment); change(environment)
            with self.subTest(change=change), self.assertRaises((A.AttestedReuseUnavailable, inputs.InputError)):
                self.admit(environment)

    def test_package_and_binary_identities_are_not_projected_or_coerced(self):
        other = deepcopy(self.environment)
        other["system_packages"]["new-reviewed-package"] = "1.2.3"
        other["tools"]["cmake"]["executable_digest"] = "sha256:" + "b" * 64
        admitted = self.admit(other)
        self.assertNotEqual(self.admit()["environment_digest"], admitted["environment_digest"])
        self.assertEqual(other["system_packages"]["new-reviewed-package"], "1.2.3")

    def test_legacy_proof_without_current_policy_and_validator_generation_fails(self):
        old = deepcopy(self.environment)
        old["trusted_execution"].pop(A.POLICY)
        old["trusted_execution"].pop("tools/test-evidence/attested.py")
        with self.assertRaises(A.AttestedReuseUnavailable): self.admit(old)

    def test_pair_scheduler_controllers_reject_old_serial_E_and_changed_actual_bytes(self):
        controllers=('tools/test-evidence/sandbox_host.py','tools/test-evidence/sandbox_shared.py',
                     'tools/test-evidence/producer_workflow.py')
        original=deepcopy(self.environment)
        self.assertTrue(set(controllers)<=set(original['trusted_execution']))
        self.assertEqual(self.admit(original)['environment_digest'],A._digest(original))
        serial=deepcopy(original)
        for name in controllers:serial['trusted_execution'].pop(name)
        with self.assertRaises(A.AttestedReuseUnavailable):self.admit(serial)
        for name in controllers:
            with self.subTest(name=name):
                path=self.root/name;old=path.read_bytes()
                try:
                    path.write_bytes(old+b'\n# Same version; changed two-scope scheduler bytes\n')
                    with self.assertRaises(A.AttestedReuseUnavailable):self.admit(original)
                    self.bind_controller()
                    self.assertEqual(self.admit()['environment_digest'],A._digest(self.environment))
                finally:
                    path.write_bytes(old);self.bind_controller()
        self.assertEqual(self.environment,original)


SPEC = importlib.util.spec_from_file_location("attested_consumer_fixture", Path(__file__).with_name("validate-sync-test.py"))
FIXTURES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURES)


class ZeroTerminalTests(RuntimeFixture):
    def setUp(self):
        super().setUp()
        case = FIXTURES.IsolatedConsumerTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.case = case
        case.environment = self.environment
        case.evidence = case.make_evidence()
        case.evidence.update(qualified_at=QUALIFIED, expires_at=EXPIRES)
        (self.root / ".github/test-suites.json").write_text(json.dumps(case.registry))
        self.validation = FIXTURES.VALIDATION
        self.calls = []
        def verify(api, config, request, *, now):
            self.calls.append(now)
            return deepcopy(case.evidence)
        case.gate.verify_evidence = verify

    def terminal(self, clock=lambda: NOW):
        # Exercise the future internal path without authorizing production use.
        with patch.object(A, "ACTIVATION_READY", True), \
                patch.object(A, "_validation", return_value=self.validation), \
                patch.object(self.validation, "_gate", return_value=self.case.gate), \
                patch.object(execution, "execute", side_effect=AssertionError("no shared or product execution")), \
                patch.object(execution, "capture_execution_environment", side_effect=AssertionError("unused consumer VM")), \
                patch.object(runtime, "_command", side_effect=AssertionError("no tool probe")):
            return A.verify_zero_shared_sync(self.case.args, api=self.case.api, root=self.root, clock=clock)

    def test_enabled_policy_cannot_bypass_unimplemented_producer_authentication_guard(self):
        with patch.object(A, "_validation", side_effect=AssertionError("no legacy gate activation")), \
                self.assertRaisesRegex(A.AttestedReuseUnavailable, "activation blocked"):
            A.verify_zero_shared_sync(self.case.args, api=self.case.api, root=self.root, clock=lambda: NOW)
        self.assertFalse(self.case.api.calls)

    def test_zero_shared_terminal_reauthenticates_twice_without_fake_machine_or_product_success(self):
        with patch.object(self.validation, "_candidate_differential", wraps=self.validation._candidate_differential) as differential:
            result = self.terminal()
        self.assertEqual(differential.call_count, 1)
        self.assertEqual(len(self.calls), 2)
        self.assertIsNone(result["consumer_environment"])
        self.assertIsNone(result["execution"])
        self.assertEqual(result["executed_suites"], [])
        self.assertEqual(set(result["reused_suites"]), {"alpha", "beta"})
        self.assertEqual(result["platform_results"], {})
        self.assertEqual(result["parent_evidence"]["expires_at"], EXPIRES)
        self.assertEqual(self.case.executed(), [])
        self.assertEqual(json.loads(self.case.args.receipt.read_text()), result)
        cases = ET.parse(self.case.args.junit).getroot().findall("testcase")
        self.assertEqual([case.attrib["name"] for case in cases], ["sync-differential"])

    def test_historical_source_mismatch_missing_failed_or_context_suite_prevents_zero_terminal(self):
        original = deepcopy(self.case.evidence)
        for change in (lambda x: x["parent_inputs"]["libraries/alpha.cpp"].update(sha="d" * 40),
                       lambda x: x["results"]["suites"].pop("beta"),
                       lambda x: x["results"]["suites"]["alpha"].update(status="failed")):
            self.case.evidence = deepcopy(original); change(self.case.evidence)
            with self.subTest(change=change), self.assertRaises(A.AttestedReuseUnavailable): self.terminal()
        self.case.evidence = original
        self.case.registry["suites"]["alpha"]["scope"] = "candidate"
        (self.root / ".github/test-suites.json").write_text(json.dumps(self.case.registry))
        with self.assertRaises(A.AttestedReuseUnavailable): self.terminal()

    def test_nonempty_platform_inventory_does_not_claim_ios_or_android_success(self):
        with patch.object(execution, "platform_suites", return_value=[("ios-host", ["python", "tests/ios-host.py"])]) as product:
            with self.assertRaises(A.AttestedReuseUnavailable): self.terminal()
        product.assert_called_once()
        self.assertFalse(self.case.args.receipt.exists())

    def test_final_missing_changed_pending_authority_or_live_refs_never_verifies(self):
        original_verify = self.case.gate.verify_evidence
        count = 0
        def missing(api, config, request, *, now):
            nonlocal count
            count += 1
            if count == 2: raise FIXTURES.EvidenceError("newest evidence is missing or failed")
            return original_verify(api, config, request, now=now)
        self.case.gate.verify_evidence = missing
        with self.assertRaises(FIXTURES.EvidenceError): self.terminal()
        self.case.gate.verify_evidence = original_verify
        original_recheck = self.validation._recheck
        def moved(api, gate, request):
            self.case.api.pr["head"]["sha"] = "9" * 40
            return original_recheck(api, gate, request)
        with patch.object(self.validation, "_recheck", side_effect=moved), self.assertRaises(ValueError): self.terminal()
        self.assertFalse(self.case.args.receipt.exists())

    def test_policy_or_candidate_change_during_real_differential_fails(self):
        original = self.validation._candidate_differential
        def changed(candidate, request, gate, api):
            original(candidate, request, gate, api)
            self.policy["epoch"] = "changed-during-validation"; self.write_policy()
        with patch.object(self.validation, "_candidate_differential", side_effect=changed), self.assertRaises(A.AttestedReuseUnavailable):
            self.terminal()
        self.assertFalse(self.case.args.receipt.exists())

    def test_changed_materialized_product_profile_cannot_hide_behind_git_index_flags(self):
        original = self.validation._candidate_differential
        def changed(candidate, request, gate, api):
            original(candidate, request, gate, api)
            self.case.git("update-index", "--assume-unchanged", "tests/platform-profile.json")
            (candidate / "tests/platform-profile.json").write_text('{"schema":1,"platform":"android","suites":[]}')
        with patch.object(self.validation, "_candidate_differential", side_effect=changed), self.assertRaises(A.AttestedReuseUnavailable):
            self.terminal()
        self.assertFalse(self.case.args.receipt.exists())

    def test_failed_required_differential_and_expiry_during_last_api_check_never_write_receipt(self):
        with patch.object(self.validation, "_candidate_differential", side_effect=ValueError("required differential failed")), \
                self.assertRaises(ValueError): self.terminal()
        final_clock = iter([NOW] * 5 + [datetime.fromisoformat(EXPIRES.replace("Z", "+00:00"))])
        with self.assertRaises(A.AttestedReuseUnavailable):
            self.terminal(clock=lambda: next(final_clock))
        self.assertFalse(self.case.args.receipt.exists())


if __name__ == "__main__":
    unittest.main()
