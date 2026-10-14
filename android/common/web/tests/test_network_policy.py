#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Reject undeclared HTTP/trust changes and validate every packaged variant."""
import importlib.util
import json
from pathlib import Path
import unittest

WEB = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('embedded_network_policy', WEB / 'network_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class NetworkPolicyTest(unittest.TestCase):
    def setUp(self):
        self.config = (WEB / 'res/xml/overte_embedded_web_network_security_config.xml').read_text()
        self.capability = (WEB / 'network-capability.json').read_text()
        self.manifest = '''<manifest xmlns:android="http://schemas.android.com/apk/res/android">
          <application android:usesCleartextTraffic="true"
            android:networkSecurityConfig="@xml/overte_embedded_web_network_security_config">
            <meta-data android:name="org.overte.web.NETWORK_CAPABILITY"
              android:value="overte.android.embedded-web.http-https.v1"/>
          </application></manifest>'''
        self.inventory = '''Package name=io.github.noah_be.overte.phone id=7f
          resource 0x7f0c0003 xml/overte_embedded_web_network_security_config
            () (file) res/n1.xml type=XML
            (v28) (file) res/n2.xml type=XML
          resource 0x7f0c0004 xml/unrelated
            () (file) res/x1.xml type=XML
        '''

    def test_real_source_policy_has_explicit_application_scope(self):
        grant = policy.validate_source(self.manifest, self.config, self.capability)
        self.assertEqual(grant['androidCleartextScope'], 'application')
        self.assertTrue(grant['requiresIndependentCredentialHttps'])
        self.assertEqual(grant['documentSchemes'], ['http', 'https'])

    def test_unreviewed_source_manifest_changes_fail(self):
        for text in [self.manifest.replace('Traffic="true"', 'Traffic="false"'),
                     self.manifest.replace('Traffic="true"', 'Traffic="TRUE"'),
                     self.manifest.replace('org.overte.web.NETWORK_CAPABILITY', 'other.marker'),
                     self.manifest.replace('http-https.v1', 'http-https.v2'),
                     self.manifest.replace('@xml/overte_embedded_web_network_security_config', '@xml/other'),
                     self.manifest.replace('<meta-data', '<meta-data android:resource="@xml/other"')]:
            with self.subTest(manifest=text):
                with self.assertRaises(ValueError):
                    policy.validate_source(text, self.config, self.capability)

    def test_duplicate_marker_is_rejected(self):
        marker = '<meta-data android:name="org.overte.web.NETWORK_CAPABILITY" android:value="overte.android.embedded-web.http-https.v1"/>'
        with self.assertRaises(ValueError):
            policy.validate_source(self.manifest.replace('</application>', marker + '</application>'), self.config, self.capability)

    def test_trust_and_http_mutations_fail(self):
        for text in [self.config.replace('Permitted="true"', 'Permitted="false"'),
                     self.config.replace('src="system"', 'src="user"'),
                     self.config.replace('src="system"', 'src="@raw/custom_ca"'),
                     self.config.replace('src="system"', 'src="system" overridePins="true"'),
                     self.config.replace('</network-security-config>', '<debug-overrides/></network-security-config>'),
                     self.config.replace('</network-security-config>', '<domain-config cleartextTrafficPermitted="true"/></network-security-config>'),
                     self.config.replace('<trust-anchors>', '<trust-anchors unexpected="true">'),
                     '<!DOCTYPE foo [<!ENTITY bad "x">]>' + self.config]:
            with self.subTest(config=text):
                with self.assertRaises((ValueError, policy.ET.ParseError)):
                    policy.validate_source(self.manifest, text, self.capability)

    def test_capability_cannot_silently_widen_or_hide_effect(self):
        original = json.loads(self.capability)
        for name, value in [('schema', True), ('documentSchemes', ['http', 'https', 'file']),
                            ('androidCleartextScope', 'webview-only'), ('tlsTrustAnchors', ['system', 'user']),
                            ('requiresIndependentCredentialHttps', False), ('requiresIndependentCredentialHttps', 1),
                            ('unknownPolicy', True)]:
            with self.subTest(field=name):
                with self.assertRaises(ValueError):
                    policy.validate_source(self.manifest, self.config, json.dumps(dict(original, **{name: value})))
        with self.assertRaises(ValueError):
            policy.capability(self.capability.replace('"schema": 1,', '"schema": 1, "schema": 1,'))

    def test_packaged_optimized_files_and_resource_id_are_resolved(self):
        raw = self.manifest.replace('@xml/overte_embedded_web_network_security_config', '@ref/0x7f0c0003')
        self.assertEqual(policy.packaged_config_paths(raw, self.inventory), ['res/n1.xml', 'res/n2.xml'])
        grant = policy.validate_artifact(raw, self.inventory, {'res/n1.xml': self.config, 'res/n2.xml': self.config}, self.capability)
        self.assertEqual(grant['id'], policy.CAPABILITY_ID)

    def test_every_packaged_variant_must_be_decoded_and_checked(self):
        with self.assertRaises(ValueError):
            policy.validate_artifact(self.manifest, self.inventory, {'res/n1.xml': self.config}, self.capability)
        with self.assertRaises(ValueError):
            policy.validate_artifact(self.manifest, self.inventory,
                                    {'res/n1.xml': self.config, 'res/n2.xml': self.config.replace('src="system"', 'src="user"')}, self.capability)

    def test_wrong_ambiguous_or_unsafe_artifact_selection_fails(self):
        for manifest, inventory in [
            (self.manifest.replace('@xml/overte_embedded_web_network_security_config', '@ref/0x7f0c0004'), self.inventory),
            (self.manifest, self.inventory + self.inventory),
            (self.manifest, self.inventory.replace('res/n1.xml', '../n1.xml')),
            (self.manifest, self.inventory.replace('xml/overte_embedded_web_network_security_config', 'xml/other')),
        ]:
            with self.subTest(inventory=inventory):
                with self.assertRaises(ValueError):
                    policy.packaged_config_paths(manifest, inventory)


if __name__ == '__main__':
    unittest.main()
