#!/usr/bin/env python3
"""Verify the actual two bundle templates retain add-only Photos consent."""
from pathlib import Path
import plistlib
import unittest

ROOT=Path(__file__).resolve().parents[2]
class BundleConsent(unittest.TestCase):
    def test_both_real_bundle_templates_require_explicit_add_only_consent(self):
        for name in ('InterfaceInfo.plist.in','InterfaceE2EInfo.plist.in'):
            with self.subTest(template=name):
                data=plistlib.loads((ROOT/'ios/resources'/name).read_bytes())
                self.assertIn('Save to device',data['NSPhotoLibraryAddUsageDescription'])
                self.assertNotIn('NSPhotoLibraryUsageDescription',data)
                self.assertIn('grant permission',data['NSMicrophoneUsageDescription'])
if __name__=='__main__':unittest.main()
