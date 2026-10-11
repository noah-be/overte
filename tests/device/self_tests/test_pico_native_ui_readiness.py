"""Native source readiness must retain one process and return actual service XML."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.android.adapter import AndroidAdapter


class PicoNativeUiReadinessTests(unittest.TestCase):
    def read(self, sources, *, changed=False, timed_out=False):
        adapter = AndroidAdapter.__new__(AndroidAdapter)
        adapter.profile = {'package': 'org.overte.pico'}
        adapter.pico_configuration = (5039, {})
        adapter.adb = SimpleNamespace(executable='/unused-test-adb')
        adapter.require_controlled_debug_identity = MagicMock(return_value='owned-process')
        adapter.require_same_process = MagicMock(side_effect=RuntimeError('process changed') if changed else None)
        calls = []
        def call(method, path, value=None):
            calls.append((method, path))
            if path == '/session':
                return {'sessionId': 'owned-native-ui-session'}
            if path.endswith('/source'):
                return sources.pop(0)
        client = SimpleNamespace(call=call)
        entry = {'enabled': True, 'physical': True, 'appId': 'org.overte.pico',
                 'serverUrl': 'http://owned-ui-test', 'capabilities': {
                     'appium:adbPort': 5039, 'appium:autoLaunch': False, 'appium:noReset': True}}
        clock = [0.0, 0.0, 21.0] if timed_out else [0.0, 0.0, 0.25, 0.5]
        with patch.dict(os.environ, {'OVERTE_PICO_APPIUM_TARGETS': '/owned-test-config'}), \
             patch('adapters.shared_appium.adapter.AppiumAdapter', return_value=SimpleNamespace(targets={'owned': entry})), \
             patch('adapters.shared_appium.adapter.WebDriver', return_value=client), \
             patch('openxr_input.android_transport.AndroidOpenXrTransport'), \
             patch('adapters.android.adapter.time.sleep'), \
             patch('adapters.android.adapter.time.monotonic', side_effect=clock):
            try:
                return adapter.pico_appium_accessibility_source('owned-test-alias'), adapter, calls
            finally:
                self.assertEqual(calls[-1], ('DELETE', '/session/owned-native-ui-session'))

    def test_waits_for_actual_owned_nodes_without_expected_test_ids(self):
        actual = '<hierarchy><node package="org.overte.pico" resource-id="org.overte.pico:id/real-control"/></hierarchy>'
        source, adapter, calls = self.read(['<hierarchy/>', actual])
        self.assertEqual(source, actual)
        self.assertEqual(adapter.require_same_process.call_count, 2)
        self.assertEqual(sum(path.endswith('/source') for _, path in calls), 2)

    def test_process_change_cannot_be_hidden_by_retry(self):
        with self.assertRaisesRegex(RuntimeError, 'process changed'):
            self.read(['<hierarchy/>'], changed=True)

    def test_appium_class_name_tags_expose_the_actual_owned_nodes(self):
        actual = '<hierarchy><android.widget.Button package="org.overte.pico" resource-id="org.overte.pico:id/real-control"/></hierarchy>'
        source, adapter, calls = self.read(['<hierarchy/>', actual])
        self.assertEqual(source, actual)
        self.assertEqual(adapter.require_same_process.call_count, 2)

    def test_empty_service_times_out_and_closes_session(self):
        with self.assertRaisesRegex(RuntimeError, 'did not expose owned semantic nodes'):
            self.read(['<hierarchy/>'], timed_out=True)

    def test_snapshot_preserves_appium_class_tag_source_and_live_identity(self):
        actual = '<hierarchy><android.widget.Button package="org.overte.pico" resource-id="org.overte.pico:id/real-control"/></hierarchy>'
        adapter = AndroidAdapter.__new__(AndroidAdapter)
        adapter.kind = 'pico'
        adapter.profile = {'package': 'org.overte.pico'}
        adapter.require_controlled_debug_identity = MagicMock(return_value='owned-process')
        adapter.require_same_process = MagicMock()
        adapter.pico_appium_accessibility_source = MagicMock(return_value=actual)
        adapter.adb = SimpleNamespace(foreground_package=MagicMock(return_value='org.overte.pico'))
        with patch.dict(os.environ, {'OVERTE_PICO_APPIUM_TARGETS': '/owned-test-config'}):
            self.assertEqual(adapter.invoke('owned-test-alias', 'accessibility.snapshot', {}), {'source': actual})
        adapter.require_same_process.assert_called_once_with('owned-test-alias', 'owned-process', 'accessibility.snapshot')

    def test_invalid_xml_is_rejected_without_retry(self):
        with self.assertRaisesRegex(RuntimeError, 'invalid XML'):
            self.read(['<broken'])


if __name__ == '__main__':
    unittest.main()
