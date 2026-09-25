#!/usr/bin/env python3
"""Static release/JNI regression guard; does not replace an R8 build/device test."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / 'android/phone/apps/phoneInterface'


class R8ContractTests(unittest.TestCase):
    def test_phone_release_enables_optimizer_without_global_bypass(self):
        gradle = (MODULE / 'build.gradle').read_text()
        build_types = gradle.split('    buildTypes {', 1)[1]
        release = build_types.split('        release {', 1)[1].split('    buildFeatures', 1)[0]
        self.assertRegex(release, r'\bminifyEnabled\s+true\b')
        self.assertNotRegex(release, r'\bminifyEnabled\s+false\b')
        self.assertIn("getDefaultProguardFile('proguard-android-optimize.txt')", release)
        self.assertIn("'proguard-rules.pro'", release)
        rules = (MODULE / 'proguard-rules.pro').read_text()
        self.assertNotRegex(rules, r'(?m)^\s*-(dontshrink|dontoptimize|dontobfuscate)\b')
        self.assertNotRegex(rules, r'(?m)^\s*-keep\s+class\s+\*')

    def test_native_storage_lookups_remain_explicitly_kept(self):
        rules = (MODULE / 'proguard-rules.pro').read_text()
        cpp = '\n'.join((MODULE / 'src' / name).read_text() for name in (
            'PhoneProtectedStoreRegistration.cpp', 'PhoneProtectedAccountStore.cpp'))
        lookups = set(re.findall(r'Get(?:Static)?MethodID\(\s*\w+\s*,\s*"([^"]+)"', cpp))
        self.assertEqual({'preparedStore', 'read', 'write', 'clear', 'nativeFailure'}, lookups,
                         'Review R8 keep rules when the JNI storage API changes')
        for method in lookups:
            self.assertRegex(rules, rf'\b{method}\([^)]*\);')
        self.assertIn('-keep,includedescriptorclasses class org.overte.phone.SecureAccountStore {', rules)
        self.assertIn('-keep class org.overte.phone.SecureAccountStore$StoreException {', rules)

    def test_qt_reflection_and_phone_native_activity_are_kept(self):
        rules = (MODULE / 'proguard-rules.pro').read_text()
        self.assertIn('-keep class org.qtproject.qt5.android.** { *; }', rules)
        cpp = (MODULE / 'src/PhoneUrlHandler.cpp').read_text()
        classes = set(re.findall(r'Java_(org_overte_phone_\w+?)_native\w+\(', cpp))
        self.assertEqual({'org_overte_phone_PhoneInterfaceActivity'}, classes)
        for name in classes:
            self.assertIn('-keep class ' + name.replace('_', '.') + ' { *; }', rules)


if __name__ == '__main__':
    unittest.main()
