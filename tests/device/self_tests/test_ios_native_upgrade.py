"""Prepared artifact boundaries for real native installation and upgrade."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import copy
import hashlib
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapters.ios import native_upgrade
from adapters.ios.adapter import IOSAdapter


class NativeUpgrade(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='native-upgrade-')
        self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'source.ipa'
        self.make_package()
        self.config={'kind':'native-signed-ipa-upgrade','bundleId':'org.example.client','teamId':'A'*10,
                     'source':{'path':str(self.path),'sha256':hashlib.sha256(self.path.read_bytes()).hexdigest(),
                               'sourceRevision':'a'*40,'version':'1.0'},
                     'candidate':{'path':str(self.path.with_name('candidate.ipa')),'sha256':'b'*64,
                                  'sourceRevision':'b'*40,'version':'2.0'}}
        self.target={'platform':'ios','physical':True,'appId':'org.example.client',
                     'testBuild':{'resultsDirectory':'owned'},'probe':{'kind':'ios-documents'},
                     'nativeUpgrade':self.config}

    def make_package(self,bundle='org.example.client',signed=True):
        # Structural test package only. Device installation and the prepared
        # signer establish real signature acceptance in physical runs.
        with zipfile.ZipFile(self.path,'w') as archive:
            root='Payload/Overte.app/'
            archive.writestr(root+'Info.plist',plistlib.dumps({'CFBundleIdentifier':bundle,
                'CFBundleSupportedPlatforms':['iPhoneOS'],'OverteE2ETestBuildContractVersion':1}))
            if signed:
                archive.writestr(root+'embedded.mobileprovision',b'structural-test-profile')
                archive.writestr(root+'_CodeSignature/CodeResources',b'structural-test-signature')
        self.path.chmod(0o600)

    def test_exact_package_bytes_are_bound_before_native_installation(self):
        config=native_upgrade.configuration(self.target)
        self.assertEqual(native_upgrade.package(config,'source'),self.path.read_bytes())
        self.path.write_bytes(self.path.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'digest'):
            native_upgrade.package(config,'source')

    def test_foreign_or_unsigned_packages_are_rejected(self):
        for bundle,signed in (('org.example.foreign',True),('org.example.client',False)):
            self.make_package(bundle,signed)
            self.config['source']['sha256']=hashlib.sha256(self.path.read_bytes()).hexdigest()
            with self.subTest(bundle=bundle,signed=signed),self.assertRaises(ValueError):
                native_upgrade.package(self.config,'source')

    def test_symlinks_and_public_artifacts_are_rejected(self):
        link=self.path.with_name('link.ipa');link.symlink_to(self.path)
        config=copy.deepcopy(self.config);config['source']['path']=str(link)
        with self.assertRaises(ValueError):native_upgrade.package(config,'source')
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):native_upgrade.package(self.config,'source')

    def test_version_pair_must_be_distinct_and_explicit(self):
        for field in ('path','sha256','sourceRevision','version'):
            config=copy.deepcopy(self.config);config['candidate'][field]=config['source'][field]
            with self.subTest(field=field),self.assertRaises(ValueError):
                native_upgrade.configuration({'appId':'org.example.client','nativeUpgrade':config})

    def test_arbitrary_install_paths_are_rejected_before_device_session_creation(self):
        adapter=IOSAdapter.__new__(IOSAdapter)
        adapter.target=Mock(return_value=self.target);adapter.ensure_session=Mock()
        with self.assertRaises(RuntimeError):
            adapter.invoke('selected','app.install',{'path':'/foreign.ipa'})
        adapter.ensure_session.assert_not_called()


if __name__=='__main__':unittest.main()
