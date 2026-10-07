# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Retain fixed aggregate syscall observations without private paths or causes."""
import copy
import json
import unittest

import curate
from observer import Projection


def document():
    projection = Projection()
    projection.add(b'1790890201.1 linkat(-100, "/private/fd/SECRET", -100, "/private/config/SECRET", 0) = -1 EEXIST (File exists)\n'
                   b'1790890201.2 linkat(-100, "/private/fd/SECRET", -100, "/private/temp/SECRET", 0) = -1 EPERM (Operation not permitted)\n')
    return {'schemaVersion': 1,
            'scope': 'standalone-fresh-domain-provisioning-probe-not-nineteen-stage-world-lifecycle',
            'completed': False, 'phase': 'stored-readback',
            'endpointOwnership': 'exact-owned-native-fixed-port', 'provisioning': 'not-requested',
            'observer': {'schemaVersion': 1, 'terminal': 'cancelled', 'exitCode': -15,
                         'trace': {'retainedBytes': 500, 'observedBytes': 500, 'truncated': False},
                         'nativeOutputTruncated': False, 'tracerOutputTruncated': False,
                         'projection': projection.finish(),
                         'tracerFailure': 'unobserved-or-unclassified',
                         'limits': ['ptrace-may-affect-timing', 'no-settings-target-causality-from-sync-fd',
                                    'unknown-or-split-trace-lines-explicit', 'no-shipping-or-CI-pass-claim']}}


class ObserverCuration(unittest.TestCase):
    def test_actual_private_projection_retains_fixed_errnos_without_target_causality(self):
        source = document()
        before = copy.deepcopy(source)
        result = curate.project(source)
        self.assertEqual(result['observer']['projection'], source['observer']['projection'])
        self.assertEqual(result['observer']['projection']['calls']['linkat']['errno'], {'EEXIST': 1, 'EPERM': 1})
        self.assertEqual(result['settingsCommitCause'], 'not-established')
        self.assertFalse(result['completed'])
        self.assertEqual(source, before)
        for private in ('SECRET', '/private', '1790890201', '-100'):
            self.assertNotIn(private, json.dumps(result))

    def test_unknown_call_errno_prose_and_oversized_counters_are_refused(self):
        for field, value in (('secret', '/private/SECRET'), ('unparsedLines', 2**53),
                             ('scope', 'proven-settings-cause'), ('incompleteLines', True)):
            source = document()
            source['observer']['projection'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                curate.project(source)
        for changed in ('call', 'errno', 'count'):
            source = document()
            calls = source['observer']['projection']['calls']
            if changed == 'call': calls['private-secret-call'] = calls['linkat']
            elif changed == 'errno': calls['linkat']['errno']['private-secret-errno'] = 1
            else: calls['linkat']['failure'] = -1
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                curate.project(source)

    def test_observation_cannot_change_false_completion_to_acceptance(self):
        source = document()
        source['completed'] = True
        with self.assertRaises(ValueError):
            curate.project(source)


if __name__ == '__main__':
    unittest.main()
