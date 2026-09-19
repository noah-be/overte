#!/usr/bin/env python3
"""Exercise production adapter with in-memory transport; never connects to ADB."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from android.common.device_tests.adb_transport import AdbTransport

with patch.object(AdbTransport, 'find_executable', return_value='/unused-test-only'):
    spec = importlib.util.spec_from_file_location('pico_adapter_boundary',
        ROOT / 'android/vr/pico/device-tests/adapter.py')
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)

class FakeTransport:
    def __init__(self):
        self.properties = {}
        self.world = ''
    def prop(self, target, name): return self.properties.get(name, '')
    def foreground_package(self, target): return adapter.PACKAGE
    def shell(self, *arguments, **options): return self.world
    def authorized_targets(self): return []
    def require_connected(self, target): raise AssertionError('unauthorized transport reached')

class AdapterNegativeTest(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.previous = adapter.ADB
        adapter.ADB = self.transport
    def tearDown(self): adapter.ADB = self.previous

    def test_unknown_boundary_and_seethrough_cannot_pass(self):
        state = adapter.xr_focus('fixture')
        self.assertFalse(state['boundaryReady'])
        self.assertTrue(state['seethroughActive'])
        self.transport.properties = {'sys.pxr.boundary.ready': '1', 'sys.guardian.vst.status': '0'}
        state = adapter.xr_focus('fixture')
        self.assertTrue(state['boundaryReady'])
        self.assertFalse(state['seethroughActive'])

    def test_world_output_never_contains_private_target_and_rejects_stale(self):
        with patch.object(adapter.time, 'time', return_value=100):
            self.transport.world = '100|1|private-canary-location|unused'
            result = adapter.world_status('fixture')
            self.assertTrue(result['connected'])
            self.assertNotIn('private-canary', json.dumps(result))
            for stamp in ('94', '101', 'invalid', '9' * 100):
                self.transport.world = stamp + '|1|private-canary-location|unused'
                self.assertFalse(adapter.world_status('fixture')['connected'])

    def test_unapproved_target_never_reaches_device_operation(self):
        for operation in adapter.CAPABILITIES:
            with self.subTest(operation=operation), self.assertRaises(RuntimeError):
                adapter.invoke('fixture', operation)
        with self.assertRaises(RuntimeError): adapter.cleanup('fixture')

if __name__ == '__main__':
    unittest.main(verbosity=2)
