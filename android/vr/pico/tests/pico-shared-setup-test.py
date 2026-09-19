#!/usr/bin/env python3
"""Compile the real setup selection with C++ preprocessing, without native headers.

This checks translation-unit and conditional selection only. Existing JNI/Qt
caller tests cover their own runtime seams; full native compilation is pending.
"""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[4]
COMMON = ROOT / 'interface/src/Application_Setup.cpp'
PICO = ROOT / 'android/vr/pico/apps/picoInterface'


def preprocess(source, defines):
    # Do not resolve native/SDK includes or start a native build. Keep every
    # actual body and conditional in the selected production translation unit.
    source = re.sub(r'^\s*#\s*include[^\n]*', '', source, flags=re.M)
    return subprocess.run(['c++', '-E', '-P', '-x', 'c++', '-',
        '-DQT_VERSION=0x060800', '-DQT_VERSION_CHECK(a,b,c)=((a<<16)|(b<<8)|c)',
        *['-D' + define for define in defines]], input=source,
        text=True, capture_output=True, timeout=15)


class SetupSelection(unittest.TestCase):
    def wrapper(self):
        path = PICO / 'overrides/Application_Setup.cpp'
        source = path.read_text()
        includes = re.findall(r'^#include "([^"]+)"$', source, re.M)
        self.assertEqual(len(includes), 1)
        self.assertEqual((path.parent / includes[0]).resolve(), COMMON)
        self.assertLess(len(source.splitlines()), 15)
        return source

    def test_real_consumers_choose_one_shared_implementation(self):
        cmake = (PICO / 'CMakeLists.txt').read_text()
        self.assertIn('list(FILTER PICO_INTERFACE_SOURCES EXCLUDE REGEX "Application_Setup', cmake)
        self.assertEqual(cmake.count('${CMAKE_CURRENT_SOURCE_DIR}/overrides/Application_Setup.cpp'), 1)
        common = COMMON.read_text()
        for pico in (False, True):
            with self.subTest(pico=pico):
                defines = ['Q_OS_ANDROID', 'ANDROID_APP_PICO_INTERFACE' if pico
                           else 'ANDROID_APP_PHONE_INTERFACE']
                result = preprocess((self.wrapper() if pico else '') + common, defines)
                self.assertEqual(result.returncode, 0, result.stderr)
                for signature in ('bool setupEssentials(', 'void Application::initialize(',
                                  'void Application::setupSignalsAndOperators('):
                    self.assertEqual(result.stdout.count(signature), 1)
                self.assertEqual('overte::pico::protectedAccountStore()' in result.stdout, pico)
                self.assertEqual('android_rcc_bundle.rcc' in result.stdout, pico)
                self.assertEqual('_window->showFullScreen();' in result.stdout, not pico)
                self.assertEqual('phone::graphics::parseClampedUnsigned(' in result.stdout, not pico)
                self.assertEqual('_window->setUpdatesEnabled(false);' in result.stdout, pico)

    def test_pico_wrapper_rejects_foreign_target(self):
        result = preprocess(self.wrapper() + COMMON.read_text(),
                            ['Q_OS_ANDROID', 'ANDROID_APP_PHONE_INTERFACE'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Pico setup requires the Pico application target', result.stderr)


if __name__ == '__main__':
    unittest.main()
