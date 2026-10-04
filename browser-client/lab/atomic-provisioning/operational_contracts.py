#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the explicit repaired operational contracts; history remains separate."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
REQUIRED = (
    'test_confined_launch.ConfinedLaunchTests.test_retire_caps_before_final_exec_and_trace_real_cpu_writes',
    'test_confined_launch.ConfinedLaunchTests.test_fixed_denial_keeps_zero_caps_and_exclusive_temp_atomic_rename',
    'test_tmpfile_contract.TmpfileContract.test_host_atomic_tmpfile_materialization_and_readback',
    'test_observer.ObserverTests.test_original_deadline_kills_own_child_without_detached_tracee',
)
HISTORICAL = (
    'test_observer.ObserverTests.historical_zero_cap_own_child_and_same_namespace_user_ipc_launch_preflight',
    'test_tmpfile_contract.TmpfileContract.historical_original_user_ipc_prefix_atomic_tmpfile_materialization_and_readback',
)
REPLACEMENTS = {
    'test_observer.py': (('historical_zero_cap_own_child_and_same_namespace_user_ipc_launch_preflight',
                         'test_zero_cap_own_child_and_same_namespace_user_ipc_launch_preflight', 1),),
    'test_tmpfile_contract.py': (('historical_original_user_ipc_prefix_atomic_tmpfile_materialization_and_readback',
                                'test_original_user_ipc_prefix_atomic_tmpfile_materialization_and_readback', 1),),
    'test_preflight_diagnostics.py': (('historical_zero_cap_own_child_and_same_namespace_user_ipc_launch_preflight',
                                     'test_zero_cap_own_child_and_same_namespace_user_ipc_launch_preflight', 4),),
}


def unique(pairs):
    row = {}
    for key, value in pairs:
        if key in row:
            raise ValueError('operational-source-duplicate')
        row[key] = value
    return row


def authenticate_sources(here=HERE):
    raw = (here / 'operational-gate-source.json').read_bytes()
    if len(raw) > 16384:
        raise ValueError('operational-source-bounds')
    document = json.loads(raw, object_pairs_hook=unique)
    prefix = 'browser-client/lab/atomic-provisioning/'
    names = set(REPLACEMENTS) | {'test_confined_launch.py'}
    if set(document) != {'schemaVersion', 'scope', 'current', 'historical'} \
            or document['schemaVersion'] != 1 \
            or document['scope'] != 'operational-command-migration-not-native-acceptance' \
            or set(document['current']) != {prefix + name for name in names} \
            or set(document['historical']) != {prefix + name for name in REPLACEMENTS}:
        raise ValueError('operational-source-schema')
    for name in names:
        data = (here / name).read_bytes()
        row = document['current'][prefix + name]
        if set(row) != {'sha256', 'bytes'} or len(data) != row['bytes'] \
                or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('operational-current-source-changed')
        if name in REPLACEMENTS:
            for new, old, count in REPLACEMENTS[name]:
                if data.count(new.encode()) != count:
                    raise ValueError('operational-history-anchor-changed')
                data = data.replace(new.encode(), old.encode())
            row = document['historical'][prefix + name]
            if set(row) != {'sha256', 'bytes'} or len(data) != row['bytes'] \
                    or hashlib.sha256(data).hexdigest() != row['sha256']:
                raise ValueError('operational-whole-history-changed')
    return document


def cases(suite):
    for child in suite:
        if isinstance(child, unittest.TestSuite):
            yield from cases(child)
        else:
            yield child


def admit_suite(suite):
    selected = list(cases(suite))
    identifiers = [case.id() for case in selected]
    if not selected or any(identifiers.count(name) != 1 for name in REQUIRED) \
            or any(name in identifiers for name in HISTORICAL) \
            or any(type(case).__name__ == '_FailedTest' for case in selected):
        raise ValueError('operational-gate-census-refused')
    return selected


class StrictResult(unittest.TextTestResult):
    def addSkip(self, test, reason):
        # A skipped operational contract cannot make this job pass.
        super().addSkip(test, reason)
        self.addFailure(test, (AssertionError, AssertionError('operational-skip-refused'), None))


def main():
    authenticate_sources()
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern='test_*.py')
    admit_suite(suite)
    result = unittest.TextTestRunner(verbosity=2, resultclass=StrictResult).run(suite)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == '__main__':
    raise SystemExit(main())
