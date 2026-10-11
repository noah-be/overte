"""Exercise real adapter methods without opening sockets or selecting a device."""
import importlib.util
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('native_text_appium', ROOT / 'adapters/shared_appium/adapter.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NativeTextBindingTests(unittest.TestCase):
    def setUp(self):
        self.adapter = object.__new__(module.AppiumAdapter)
        self.target = {'appId': 'io.github.noah_be.overte.phone',
                       'process': {'selector': 'host-contract-target'}, 'capabilities': {}}
        self.identity = {'running': True, 'identity': 'host-contract-process'}
        self.response = None
        self.value = ''
        self.submitted = 0
        self.focused = True
        self.keycodes = []
        self.bad = {}
        self.clock_offset_ms = 0
        self.adapter.android_client_identity = lambda *args: self.identity
        def write(client, session, target, command, identity):
            action = command['operation']
            if action == 'focus':
                self.value = ''
                self.focused = True
            elif action == 'dismiss':
                self.focused = False
            self.response = {'schemaVersion': 1, 'commandId': command['commandId'], 'ok': True,
                             'sampleEpochMs': int(time.time() * 1000) + self.clock_offset_ms,
                             'snapshot': {'schemaVersion': 1, 'value': self.value, 'focused': self.focused,
                                          'keyboardVisible': self.focused, 'submittedCount': self.submitted}}
            self.response.update(self.bad)
        self.adapter.write_android_client_command = write
        case = self
        class Transport:
            def epoch_milliseconds(self, device):
                return int(time.time() * 1000) + case.clock_offset_ms
            def read_debug_app_file(self, *args, **kwargs):
                case.assertEqual('files/overte-e2e/phone-ui-status.json', args[2])
                return json.dumps(case.response)
            def shell(self, device, command, verb, keycode):
                case.assertEqual(('input', 'keyevent'), (command, verb))
                case.keycodes.append(keycode)
                if keycode == '67': case.value = case.value[:-1]
                elif keycode == '66': case.submitted += 1
                return ''
        self.transport_patch = patch('adb_transport.AdbTransport', Transport)
        self.transport_patch.start()
        self.addCleanup(self.transport_patch.stop)
        class Client:
            def call(self, method, path, payload):
                case.assertEqual('POST', method)
                if path.endswith('/element'):
                    case.assertEqual({'using': 'id', 'value': case.target['appId'] + ':id/controlled.text'}, payload)
                    return {'element-6066-11e4-a52e-4f735466cecf': 'controlled-element'}
                case.assertTrue(path.endswith('/element/controlled-element/value'))
                case.value = payload['text']
                return None
        self.client = Client()

    def test_native_tablet_resource_ids_use_actual_element_clicks(self):
        target = {'platform': 'android', 'appId': self.target['appId'],
                  'controls': {'tablet': {
                      'openResourceId': self.target['appId'] + ':id/tablet.open',
                      'closeResourceId': self.target['appId'] + ':id/nav.close'}}}
        self.adapter.target = lambda selector: target
        calls = []
        class Client:
            def call(self, method, path, payload):
                calls.append((method, path, payload))
                return {'element-6066-11e4-a52e-4f735466cecf': 'native-button'}
        self.adapter.ensure_session = lambda selector: (Client(), 'session', {})
        for operation, resource in [('tablet.open', 'tablet.open'), ('tablet.close', 'nav.close')]:
            with self.subTest(operation=operation):
                self.assertIn(operation, self.adapter.advertised_capabilities(target))
                self.assertEqual({'performed': True}, self.adapter.invoke('host-target', operation, {}))
                self.assertEqual(('POST', '/session/session/element',
                                  {'using': 'id', 'value': target['appId'] + ':id/' + resource}), calls[-2])
                self.assertEqual(('POST', '/session/session/element/native-button/click', {}), calls[-1])

    def test_tablet_resource_ids_reject_foreign_namespaces_and_platforms(self):
        for platform, identifier in [('ios', self.target['appId'] + ':id/tablet.open'),
                                     ('android', 'other.application:id/tablet.open'),
                                     ('android', None), ('android', ''),
                                     ('android', self.target['appId'] + ':id/../tablet.open')]:
            with self.subTest(platform=platform, identifier=identifier):
                target = {'platform': platform, 'appId': self.target['appId'],
                          'controls': {'tablet': {'openResourceId': identifier}}}
                self.adapter.validate_controls(target['controls'])
                with self.assertRaisesRegex(RuntimeError, 'application namespace'):
                    self.adapter.validate_tablet_resource_ids(target)

    def test_native_tablet_click_rejects_missing_element_reference(self):
        class Client:
            def call(self, *args):
                return {}
        with self.assertRaisesRegex(RuntimeError, 'element reference'):
            self.adapter.click_element(Client(), 'session', 'id', self.target['appId'] + ':id/tablet.open')

    def test_android_semantic_transition_waits_for_real_native_nodes(self):
        self.adapter.platform = 'android'
        sources = iter(['<hierarchy/>', '<hierarchy><node resource-id="io.github.noah_be.overte.phone:id/tablet.home"'
                        ' clickable="false" enabled="true"/></hierarchy>'])
        class TransitionClient:
            def call(self, method, path):
                return next(sources)
        with patch.object(module.time, 'sleep'):
            state, actions = self.adapter.semantic_snapshot(TransitionClient(), 'session')
        self.assertEqual('tablet.home', state['screenId'])
        self.assertTrue(state['ready'])
        self.assertEqual({}, actions)
        class AbsentClient:
            def call(self, method, path):
                return '<hierarchy/>'
        with patch.object(module.time, 'sleep'), self.assertRaisesRegex(RuntimeError, 'exactly one visible screen'):
            self.adapter.semantic_snapshot(AbsentClient(), 'session')

    def test_actual_protocol_route_unicode_keys_and_correlated_observation(self):
        self.adapter.android_text_state(self.client, 'session', self.target, 'focus')
        self.assertEqual({'performed': True}, self.adapter.android_type_text(
            self.client, 'session', self.target, {'text': 'Overte äöüX', 'backspaceCount': 1, 'submit': True}))
        observed = self.adapter.android_text_state(self.client, 'session', self.target, 'snapshot')
        self.assertEqual('Overte äöü', observed['value'])
        self.assertEqual(1, observed['submittedCount'])
        self.assertEqual(['67', '66'], self.keycodes)
        dismissed = self.adapter.android_text_state(self.client, 'session', self.target, 'dismiss')
        self.assertFalse(dismissed['focused'])
        self.assertFalse(dismissed['keyboardVisible'])

    def test_malformed_stale_or_missing_native_keyboard_observations_fail(self):
        for mutation in ({'schemaVersion': True}, {'ok': False}, {'sampleEpochMs': 0},
                         {'sampleEpochMs': True}, {'extra': True},
                         {'snapshot': {'schemaVersion': 1, 'value': '', 'focused': True,
                                       'submittedCount': 0, 'keyboardVisible': None}}):
            self.bad = mutation
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                self.adapter.android_text_state(self.client, 'session', self.target, 'snapshot')

    def test_process_restart_cannot_reuse_measurement(self):
        self.adapter.android_client_identity = lambda *args: {'identity': self.submitted}
        original = self.adapter.write_android_client_command
        def restart(*args):
            original(*args)
            self.submitted += 1
        self.adapter.write_android_client_command = restart
        with self.assertRaisesRegex(RuntimeError, 'process changed'):
            self.adapter.android_text_state(self.client, 'session', self.target, 'snapshot')

    def test_native_clock_offset_preserves_freshness_and_rejects_future_samples(self):
        for offset in (-900000, 900000):
            self.clock_offset_ms = offset
            self.bad = {}
            self.adapter.android_text_state(self.client, 'session', self.target, 'focus')
            self.bad = {'sampleEpochMs': int(time.time() * 1000) + offset + 10000}
            with self.assertRaisesRegex(RuntimeError, 'fresh successful observation'):
                self.adapter.android_text_state(self.client, 'session', self.target, 'snapshot')


if __name__ == '__main__':
    unittest.main()
