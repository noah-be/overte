#!/usr/bin/env python3
"""Check fixed native routing while shared imports retain their implementation."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

DEVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEVICE))
from adapters.appium import adapter
from adapters.shared_appium import adapter as shared


class RoutingTests(unittest.TestCase):
    def test_generic_imports_always_use_the_shared_classes(self):
        self.assertIs(adapter.AppiumAdapter, shared.AppiumAdapter)
        self.assertIs(adapter.WebDriver, shared.WebDriver)

    def test_android_never_imports_native_ios_and_restores_arguments(self):
        original = sys.argv
        with mock.patch.object(adapter.importlib, 'import_module') as native, \
                mock.patch.object(adapter, 'shared_main', return_value=17) as main:
            self.assertEqual(adapter.main(['--platform', 'android', 'discover']), 17)
            native.assert_not_called()
            main.assert_called_once_with()
        self.assertIs(sys.argv, original)

    def test_ios_routes_only_to_the_fixed_product_module(self):
        native = mock.Mock()
        native.main.return_value = 23
        arguments = ['--platform', 'ios', '--native-binding', 'discover']
        with mock.patch.object(adapter.importlib, 'import_module', return_value=native) as load, \
                mock.patch.object(adapter, 'shared_main') as main:
            self.assertEqual(adapter.main(arguments), 23)
            load.assert_called_once_with('ios.adapters.appium_adapter')
            native.main.assert_called_once_with(arguments)
            main.assert_not_called()

    def test_absent_native_ios_retains_the_shared_non_native_cli(self):
        for name in ('ios.adapters', 'ios.adapters.appium_adapter'):
            with self.subTest(name=name), \
                    mock.patch.object(adapter.importlib, 'import_module',
                                      side_effect=ModuleNotFoundError(name=name)), \
                    mock.patch.object(adapter, 'shared_main', return_value=7):
                self.assertEqual(adapter.main(['--platform', 'ios', 'discover']), 7)

    def test_native_requests_without_the_owned_module_fail_before_driver_start(self):
        for platform in ('android', 'ios'):
            with self.subTest(platform=platform), \
                    mock.patch.object(adapter.importlib, 'import_module',
                                      side_effect=ModuleNotFoundError(name='ios.adapters')), \
                    mock.patch.object(adapter, 'shared_main') as main:
                with self.assertRaisesRegex(ValueError, 'PRODUCT_REJECTED'):
                    adapter.main(['--platform', platform, '--native-binding', 'discover'])
                main.assert_not_called()

    def test_broken_native_dependencies_do_not_silently_use_another_adapter(self):
        with mock.patch.object(adapter.importlib, 'import_module',
                               side_effect=ModuleNotFoundError(name='native_dependency')), \
                mock.patch.object(adapter, 'shared_main') as main:
            with self.assertRaises(ModuleNotFoundError):
                adapter.main(['--platform', 'ios', 'discover'])
            main.assert_not_called()

    def test_shared_failure_restores_process_arguments(self):
        original = sys.argv
        with mock.patch.object(adapter, 'shared_main', side_effect=ValueError('closed')):
            with self.assertRaisesRegex(ValueError, 'closed'):
                adapter.main(['--platform', 'android', 'discover'])
        self.assertIs(sys.argv, original)

    def test_actual_private_parser_does_not_echo_invalid_platform_values(self):
        canary = 'private-platform-canary'
        result = subprocess.run([sys.executable, str(DEVICE / 'adapters/appium/adapter.py'),
                                 '--platform', canary, '--native-binding', 'discover'],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn('OVT_ADAPTER_ARGUMENTS_REJECTED', result.stderr)
        self.assertNotIn(canary, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
