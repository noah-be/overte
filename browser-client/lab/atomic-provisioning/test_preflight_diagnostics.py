#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""CPU-only controls; no namespace, tracer, native or service execution."""
import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

D = load('preflight_diagnostics_contract', HERE / 'preflight_diagnostics.py')
T = load('actual_observer_contract', HERE / 'test_observer.py')
ZERO = '\n'.join(key + ':\t0000000000000000' for key in D.CAPABILITIES)

ORIGINAL_FUNCTIONS_SHA256 = '2d2912688d4e595f02011ee24dbc3bc3a955bdfc622bd6e8662a8a3114d59ca8'
ADDED_OPERATION_FIELD = "\n            'outerCapabilityOperation': stderr_capability_operation(stderr),"


def original_function_sources(source, remove_operation_field=False):
    names=('stderr_failure','project_preflight')
    result={}
    for node in ast.parse(source).body:
        if isinstance(node,ast.FunctionDef) and node.name in names:
            if node.name in result:raise AssertionError('duplicate-original-function')
            result[node.name]=ast.get_source_segment(source,node)
    if set(result)!=set(names):raise AssertionError('original-function-missing')
    if remove_operation_field:
        text=result['project_preflight']
        if text.count(ADDED_OPERATION_FIELD)!=1:raise AssertionError('exact-added-field-refused')
        result['project_preflight']=text.replace(ADDED_OPERATION_FIELD,'',1)
    return result


class ProjectionTests(unittest.TestCase):
    def test_exact_existing_five_operations_are_projected_without_error_text(self):
        operations = [('apply bounding set','apply-bounding-set'),('apply capabilities','apply-capabilities'),('set capabilities','set-capabilities'),('cap_set_proc','cap-set-proc'),('set process securebits','set-process-securebits')]
        for original, fixed in operations:
            for separator in (': ', ' failed: '):
                for errno in ('Operation not permitted','Permission denied'):
                    with self.subTest(operation=fixed,separator=separator,errno=errno):
                        raw=('setpriv: '+original+separator+errno+'\n').encode()
                        result=D.project_preflight(127,b'',raw)
                        self.assertEqual(result['outerStderrFailure'],'capability-action-refused')
                        self.assertEqual(result['outerCapabilityOperation'],fixed)
                        self.assertEqual(result['cause'],'not-established')

    def test_operation_never_claims_same_length_unknown_or_private_text(self):
        for raw in (b'x'*53,b'setpriv: apply bounding set ARG_PRIVATE: Operation not permitted',b'/private/setpriv: apply bounding set: Operation not permitted',b'setpriv: apply bounding set: Operation not permitted/private',b'private: apply bounding set: Operation not permitted',b'setpriv: unknown: Permission denied',b'\xffsetpriv: apply bounding set: Operation not permitted'):
            result=D.project_preflight(127,b'',raw)
            self.assertEqual(result['outerCapabilityOperation'],'unobserved-or-unclassified')
            self.assertNotIn('private',json.dumps(result));self.assertNotIn('ARG_PRIVATE',json.dumps(result))

    def test_ambiguous_or_censored_operations_refuse_preserving_original_category(self):
        one=b'setpriv: apply bounding set: Operation not permitted\n';another=b'setpriv: cap_set_proc failed: Permission denied\n'
        for raw in (one+one,one+another,one+b'x'*D.MAX_BYTES):
            result=D.project_preflight(127,b'',raw)
            self.assertEqual(result['outerStderrFailure'],'capability-action-refused')
            self.assertEqual(result['outerCapabilityOperation'],'unobserved-or-unclassified')
        self.assertEqual(D.project_preflight(127,b'',b'x'*D.MAX_BYTES+b'\n'+one)['outerCapabilityOperation'],'unobserved-or-unclassified')

    def test_original_classifier_and_projection_source_stay_exact_except_one_new_field(self):
        import hashlib
        frozen=(HERE/'fixtures/preflight-original-functions.py.txt').read_text()
        self.assertEqual(hashlib.sha256(frozen.encode()).hexdigest(), ORIGINAL_FUNCTIONS_SHA256)
        self.assertEqual(original_function_sources((HERE/'preflight_diagnostics.py').read_text(), True),
                         original_function_sources(frozen))

    def test_literal_source_oracle_refuses_original_body_and_new_field_mutations(self):
        frozen=original_function_sources((HERE/'fixtures/preflight-original-functions.py.txt').read_text())
        source=(HERE/'preflight_diagnostics.py').read_text()
        for before,after in [('return \'capability-action-refused\'', 'return \'command-exec-refused\''),
                             ("'cause': 'not-established'", "'cause': 'established'")]:
            self.assertIn(before,source)
            self.assertNotEqual(original_function_sources(source.replace(before,after,1),True),frozen)
        for changed in (source.replace(ADDED_OPERATION_FIELD, '', 1),
                        source.replace('stderr_capability_operation(stderr),', 'stderr_capability_operation(err),',1)):
            with self.assertRaises(AssertionError):original_function_sources(changed,True)

    def test_known_exec_and_loader_classes_never_export_private_text(self):
        cases = [
            (b'unshare: failed to execute /private/credential: No such file or directory', 'command-exec-not-found'),
            (b'setpriv: failed to execute /private/credential: Permission denied', 'command-exec-refused'),
            (b'/private/python3.12: error while loading shared libraries: credential.so: cannot open shared object file: No such file or directory', 'dynamic-loader-library-not-found'),
            (b'/private/strace: symbol lookup error: /private/credential.so: undefined symbol: account', 'dynamic-loader-symbol-unavailable'),
            (b'unshare: unshare failed: Operation not permitted', 'unshare-operation-not-permitted'),
            (b'unshare: unshare failed: Permission denied', 'unshare-permission-denied'),
            (b'setpriv: apply capabilities: Operation not permitted', 'capability-action-refused'),
            (b'setpriv: set process securebits failed: Permission denied', 'capability-action-refused'),
            (b'strace: ptrace(PTRACE_TRACEME, /private/credential): Operation not permitted', 'tracer-ptrace-operation-not-permitted'),
            (b'strace: ptrace(PTRACE_TRACEME): Permission denied', 'tracer-ptrace-permission-denied'),
            (b'strace: ptrace(unknown): opaque', 'tracer-ptrace-unclassified-error'),
            (b"strace: Can't stat '/private/credential': No such file or directory", 'tracer-exec-not-found'),
            (b'ModuleNotFoundError: credential', 'python-import-error'),
            (b'SyntaxError: credential', 'python-syntax-error'),
            (b'AssertionError: credential', 'python-assertion-error'),
            (b'RuntimeError: credential', 'python-runtime-error')]
        for raw, expected in cases:
            with self.subTest(expected=expected):
                result = D.project_preflight(127, b'', raw)
                self.assertEqual(result['outerStderrFailure'], expected)
                encoded = json.dumps(result)
                for secret in ('/private', 'credential', 'account', 'PTRACE_TRACEME', 'python3.12'):
                    self.assertNotIn(secret, encoded)
                self.assertEqual(result['cause'], 'not-established')

    def test_exit_127_does_not_imply_exec_or_loader_cause(self):
        for stderr in (b'', b'private: Operation not permitted', b'native: ptrace(secret): Permission denied',
                       b'strace-like: ptrace(secret): Permission denied', b'opaque\xffprivate message'):
            self.assertEqual(D.project_preflight(127, b'', stderr)['outerStderrFailure'], 'unobserved-or-unclassified')

    def test_capability_classes_keep_all_five_and_missing_duplicate_invalid(self):
        self.assertEqual(set(D.capability_states(ZERO.splitlines()).values()), {'zero'})
        for key, name in D.CAPABILITIES.items():
            lines = ZERO.splitlines()
            index = list(D.CAPABILITIES).index(key)
            lines[index] = key + ': 0000000000000001'
            self.assertEqual(D.capability_states(lines)[name], 'nonzero')
            self.assertEqual(D.capability_states([line for line in lines if not line.startswith(key + ':')])[name], 'absent')
            self.assertEqual(D.capability_states(lines + [key + ': 0'])[name], 'unparseable')
            self.assertEqual(D.capability_states([key + ': private'])[name], 'unparseable')

    def test_prefix_censoring_and_malformed_records_do_not_throw_or_leak(self):
        # A marker beyond the original prefix cannot become a reported milestone.
        result = D.project_preflight(127, b'x' * (D.MAX_BYTES + 1) + b'\nATOMIC_PREFLIGHT:strict-inner-asserted',
                                     b'x' * (D.MAX_BYTES + 1) + b'\nAssertionError: private')
        self.assertTrue(result['stdoutPrefixTruncated'])
        self.assertTrue(result['stderrPrefixTruncated'])
        self.assertEqual(result['lastMilestone'], 'none-observed')
        self.assertEqual(result['outerStderrFailure'], 'unobserved-or-unclassified')
        raw = (b'ATOMIC_PREFLIGHT_CAPS:{"secret":"private"}\nATOMIC_PREFLIGHT_OBSERVER:{"exitCode":0}\n'
               b'ATOMIC_PREFLIGHT_CAPS:' + b'[' * 1500 + b'0' + b']' * 1500 + b'\n')
        result = D.project_preflight(True, raw, b'')
        self.assertEqual(result['malformedFixedRecords'], 3)
        self.assertIsNone(result['outerExitCode'])
        self.assertNotIn('private', json.dumps(result))

    def test_inner_exact_markers_and_counts_and_output_censoring(self):
        report = {'terminal': 'native-terminal', 'exitCode': 127, 'tracerFailure': 'ptrace-operation-not-permitted',
                  'projection': {'calls': {'fsync': {'success': 0}}}, 'nativeOutputTruncated': True}
        native = b'ATOMIC_PREFLIGHT:inner-start\nunshare: failed to execute /private/credential: No such file or directory\n'
        inner = D.inner_observation(report, native)
        self.assertTrue(inner['innerStarted'])
        self.assertFalse(inner['innerFsyncReturned'])
        self.assertEqual(inner['outputFailure'], 'command-exec-not-found')
        self.assertTrue(inner['nativeOutputTruncated'])
        projected = D.project_preflight(1, b'ATOMIC_PREFLIGHT_OBSERVER:' + json.dumps(inner).encode(), b'')
        self.assertEqual(projected['innerObservation'], inner)
        report['exitCode'] = True
        report['projection']['calls']['fsync']['success'] = D.MAX_COUNT + 1
        bad = D.inner_observation(report, b'x' * (D.MAX_BYTES + 1))
        self.assertIsNone(bad['exitCode'])
        self.assertIsNone(bad['fsyncSuccess'])
        self.assertTrue(bad['outputPrefixTruncated'])

    def test_oversized_or_extra_inner_schema_cannot_export_context(self):
        inner = D.inner_observation({}, b'')
        for altered in (dict(inner, private='credential'), dict(inner, fsyncSuccess=True),
                        dict(inner, captureStatus='private'), dict(inner, terminal=[])):
            result = D.project_preflight(1, b'ATOMIC_PREFLIGHT_OBSERVER:' + json.dumps(altered).encode(), b'')
            self.assertIsNone(result['innerObservation'])
            self.assertEqual(result['malformedFixedRecords'], 1)

class ActualGeneratedPreflightTests(unittest.TestCase):
    def run_control(self, mode='success', caps=ZERO, capture=True):
        observed = {}
        real_spec = importlib.util.spec_from_file_location
        real_read = Path.read_text
        original_cwd = os.getcwd()
        def fake_run(argv, **kwargs):
            observed['argv'] = argv
            observed['kwargs'] = kwargs
            entry = Path(argv[-1])
            observed['entry'] = entry.read_text()
            observed['marker'] = (entry.parent / 'preflight.py').read_text()
            observed['root'] = entry.parent
            if mode == 'outer-127':
                return subprocess.CompletedProcess(argv, 127, b'', b'setpriv: failed to execute /private/credential: No such file or directory\n')
            out, err = io.StringIO(), io.StringIO()
            def fake_observe(tracer, inner_argv, environment, cwd, directory, seconds):
                observed['inner'] = (tracer, inner_argv, environment, cwd, directory, seconds)
                if mode == 'tracer-throw':
                    raise FileNotFoundError('private tracer name')
                native = io.StringIO()
                if mode not in ('tracer-refused', 'inner-127'):
                    os.chdir(cwd)
                    with contextlib.redirect_stdout(native), patch.object(os, 'fsync') as fsync:
                        exec(compile(observed['marker'], '<authored-inner>', 'exec'), {})
                    observed['fsync_calls'] = fsync.call_count
                elif mode == 'inner-127':
                    native.write('unshare: failed to execute /private/credential: No such file or directory\n')
                if capture:
                    path = Path(directory) / 'native-output.private.log'
                    path.write_bytes(native.getvalue().encode())
                    path.chmod(0o600)
                return {'terminal': 'native-terminal', 'exitCode': 127 if mode == 'inner-127' else (1 if mode == 'tracer-refused' else 0),
                        'tracerFailure': 'ptrace-operation-not-permitted' if mode == 'tracer-refused' else 'unobserved-or-unclassified',
                        'projection': {'calls': {'fsync': {'success': 0 if mode in ('no-fsync', 'tracer-refused', 'inner-127') else 1}}}}
            fake_observer = types.SimpleNamespace(observe_owned=fake_observe, checked_regular=T.observer.checked_regular,
                                                   MAX_CAPTURE=T.observer.MAX_CAPTURE)
            def spec(name, path):
                if name == 'observer':
                    def populate(module):
                        if mode == 'import-fault':
                            raise ImportError('private observer filename')
                        module.__dict__.update(fake_observer.__dict__)
                    return importlib.util.spec_from_loader(name, types.SimpleNamespace(create_module=lambda spec: None, exec_module=populate))
                return real_spec(name, path)
            def read(path, *args, **kwargs):
                return caps if str(path) == '/proc/self/status' else real_read(path, *args, **kwargs)
            code = 0
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                     patch.object(importlib.util, 'spec_from_file_location', side_effect=spec), \
                     patch.object(Path, 'read_text', read):
                    exec(compile(observed['entry'], '<authored-entry>', 'exec'), {})
            except Exception:
                code = 1
                traceback.print_exc(file=err)
            finally:
                os.chdir(original_cwd)
            observed['projection'] = D.project_preflight(code, out.getvalue().encode(), err.getvalue().encode())
            return subprocess.CompletedProcess(argv, code, out.getvalue().encode(), err.getvalue().encode())
        error = None
        with patch.object(T.subprocess, 'run', side_effect=fake_run) as run:
            try:
                T.ObserverTests('historical_zero_cap_own_child_and_same_namespace_user_ipc_launch_preflight').historical_zero_cap_own_child_and_same_namespace_user_ipc_launch_preflight()
            except AssertionError as exc:
                error = str(exc)
            self.assertEqual(run.call_count, 1)
        observed['error'] = error
        return observed

    def test_actual_original_argv_caps_deadlines_and_fsync_predicate_preserved(self):
        result = self.run_control()
        self.assertIsNone(result['error'])
        self.assertEqual(result['argv'][:-1], ['/usr/bin/unshare', '--user', '--map-current-user', '--keep-caps',
                         '--ipc', '--', '/usr/bin/setpriv', '--bounding-set=-all', '--inh-caps=-all', '--ambient-caps=-all', '--', sys.executable])
        self.assertEqual(result['kwargs'], {'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE, 'timeout': 8})
        tracer, argv, env, cwd, directory, seconds = result['inner']
        self.assertEqual(tracer, str(T.STRACE))
        self.assertEqual(argv, ['/usr/bin/unshare', '--user', '--map-current-user', '--ipc', '--', sys.executable, str(result['root'] / 'preflight.py')])
        self.assertEqual(env, dict(os.environ))
        self.assertEqual(cwd, str(result['root']))
        self.assertEqual(directory, str(result['root'] / 'capture'))
        self.assertEqual(seconds, 5)
        self.assertEqual(result['fsync_calls'], 1)
        asserts = [ast.unparse(node.test) for node in ast.walk(ast.parse(result['entry'])) if isinstance(node, ast.Assert)]
        self.assertEqual(len(asserts), 2)
        self.assertIn("int(line.split(':', 1)[1], 16) == 0", asserts[0])
        for key in D.CAPABILITIES:
            self.assertIn(key + ':', asserts[0])
        self.assertEqual(asserts[1], "r['exitCode'] == 0 and r['projection']['calls']['fsync']['success'] >= 1")
        self.assertEqual(result['projection']['lastMilestone'], 'strict-inner-asserted')
        self.assertTrue(result['projection']['innerObservation']['innerFsyncReturned'])

    def test_actual_outer127_still_fails_with_only_fixed_diagnostic(self):
        result = self.run_control('outer-127')
        self.assertIsNotNone(result['error'])
        self.assertIn('command-exec-not-found', result['error'])
        self.assertNotIn('/private', result['error'])
        self.assertNotIn('credential', result['error'])
        self.assertNotIn('inner', result)

    def test_actual_nonzero_each_cap_fails_before_tracer(self):
        for key in D.CAPABILITIES:
            with self.subTest(capability=key):
                result = self.run_control(caps=ZERO.replace(key + ':\t0000000000000000', key + ':\t0000000000000001'))
                self.assertIsNotNone(result['error'])
                self.assertNotIn('inner', result)
                self.assertEqual(result['projection']['lastMilestone'], 'observer-imported')
                self.assertEqual(result['projection']['capabilityStates'][D.CAPABILITIES[key]], 'nonzero')

    def test_actual_import_and_tracer_faults_remain_failed(self):
        for mode, milestone, category in [('import-fault', 'entry-start', 'python-import-error'),
                                         ('tracer-throw', 'tracer-launch-requested', 'python-runtime-error')]:
            result = self.run_control(mode)
            self.assertIsNotNone(result['error'])
            self.assertEqual(result['projection']['lastMilestone'], milestone)
            self.assertEqual(result['projection']['outerStderrFailure'], category)
            self.assertNotIn('private', result['error'])

    def test_actual_tracer_refusal_inner127_and_no_fsync_preserve_failures(self):
        for mode in ('tracer-refused', 'inner-127', 'no-fsync'):
            result = self.run_control(mode)
            self.assertIsNotNone(result['error'])
            self.assertEqual(result['projection']['lastMilestone'], 'observer-returned')
            self.assertEqual(result['projection']['outerStderrFailure'], 'python-assertion-error')
            inner = result['projection']['innerObservation']
            if mode == 'tracer-refused':
                self.assertEqual(inner['tracerFailure'], 'ptrace-operation-not-permitted')
            if mode == 'inner-127':
                self.assertEqual(inner['outputFailure'], 'command-exec-not-found')
            if mode == 'no-fsync':
                self.assertEqual(inner['fsyncSuccess'], 0)
                self.assertTrue(inner['innerFsyncReturned'])  # Marker alone never satisfies the assertion.

    def test_original_outer_timeout_still_propagates_without_retry(self):
        with patch.object(T.subprocess, 'run', side_effect=subprocess.TimeoutExpired('authored-control', 8)) as run:
            with self.assertRaises(subprocess.TimeoutExpired) as failure:
                T.ObserverTests('historical_zero_cap_own_child_and_same_namespace_user_ipc_launch_preflight').historical_zero_cap_own_child_and_same_namespace_user_ipc_launch_preflight()
            self.assertEqual(failure.exception.timeout, 8)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.kwargs['timeout'], 8)

    def test_diagnostic_read_refusal_does_not_replace_original_outcome(self):
        result = self.run_control(capture=False)
        self.assertIsNone(result['error'])
        self.assertEqual(result['projection']['innerObservation']['captureStatus'], 'read-refused')
        self.assertFalse(result['projection']['innerObservation']['innerStarted'])



class PrivateFailureCaptureTests(unittest.TestCase):
    def test_original_failed_bytes_remain_private_bounded_and_no_raw_output(self):
        import tempfile
        import stat
        with tempfile.TemporaryDirectory() as directory:
            stdout = b'private-account' * 1000
            stderr = b'private-executable: opaque' * 1000
            result = D.retain_failed_preflight(directory, stdout, stderr)
            self.assertEqual(result['status'], 'retained-private')
            self.assertEqual(result['stdoutRetainedBytes'], D.MAX_BYTES)
            self.assertEqual(result['stderrRetainedBytes'], D.MAX_BYTES)
            self.assertTrue(result['stdoutTruncated']); self.assertTrue(result['stderrTruncated'])
            children = list(Path(directory).iterdir()); self.assertEqual(len(children), 1)
            self.assertEqual(stat.S_IMODE(children[0].stat().st_mode), 0o700)
            for label, expected in [('stdout', stdout), ('stderr', stderr)]:
                file = children[0] / (label + '-prefix.private.log')
                self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
                self.assertEqual(file.read_bytes(), expected[:D.MAX_BYTES])
            self.assertNotIn('private-account', json.dumps(result)); self.assertNotIn(directory, json.dumps(result))
    def test_unsafe_parent_and_symlink_refuse_without_write_and_missing_optional_input(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); writable = root / 'wrong'; writable.mkdir(mode=0o755); writable.chmod(0o755)
            self.assertEqual(D.retain_failed_preflight(str(writable), b'x', b'y')['status'], 'retention-refused')
            link = root / 'link'; link.symlink_to(root, target_is_directory=True)
            self.assertEqual(D.retain_failed_preflight(str(link), b'x', b'y')['status'], 'retention-refused')
            self.assertEqual(list(writable.iterdir()), [])
            self.assertEqual(D.retain_failed_preflight(None, b'x', b'y')['status'], 'not-configured')
    def test_unsafe_parent_control_remains_unsafe_under_restrictive_umask(self):
        original = os.umask(0o077)
        try:
            self.test_unsafe_parent_and_symlink_refuse_without_write_and_missing_optional_input()
        finally:
            os.umask(original)

    def test_capture_write_failure_cannot_replace_original_failure_and_fds_close(self):
        import tempfile
        opened = []; original_open = os.open
        def tracked_open(*args, **kwargs):
            descriptor = original_open(*args, **kwargs); opened.append(descriptor); return descriptor
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(D.os, 'open', side_effect=tracked_open), patch.object(D.os, 'write', side_effect=OSError('private failure')):
                result = D.retain_failed_preflight(directory, b'x', b'y')
            self.assertEqual(result['status'], 'retention-refused'); self.assertNotIn('private failure', json.dumps(result))
            self.assertEqual(len(opened), 3)
            for descriptor in opened:
                with self.assertRaises(OSError): os.fstat(descriptor)
    def test_installed_setpriv_literal_variants_project_fixed_no_path_and_unknown_stays_unknown(self):
        for line, category in [(b'setpriv: apply bounding set: Operation not permitted', 'capability-action-refused'), (b'setpriv: setresuid failed: Permission denied', 'identity-action-refused'), (b'setpriv: setgroups failed: Operation not permitted', 'identity-action-refused')]:
            self.assertEqual(D.stderr_failure(line), category)
        self.assertEqual(D.stderr_failure(b'private-tool: apply bounding set: Operation not permitted'), 'unobserved-or-unclassified')
        self.assertEqual(D.stderr_failure(b'opaque private stderr'), 'unobserved-or-unclassified')
    def test_original_preflight_argv_timeout_asserts_and_one_run_are_unchanged(self):
        source = (HERE / 'test_observer.py').read_text()
        self.assertIn('stderr=subprocess.PIPE, timeout=8)', source)
        self.assertIn("'--bounding-set=-all', '--inh-caps=-all'", source)
        self.assertIn("assert r[\"exitCode\"]==0 and r[\"projection\"][\"calls\"][\"fsync\"][\"success\"]>=1", source)
        self.assertIn("self.assertEqual(result.returncode, 0, 'unchanged-own-child-confinement-preflight-refused:'", source)


if __name__ == '__main__':
    unittest.main()
