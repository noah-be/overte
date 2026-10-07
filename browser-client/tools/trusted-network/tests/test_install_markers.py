# SPDX-License-Identifier: Apache-2.0
"""Real marker files and installer ordering; no root/system/namespace operations."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('marker_installer', BASE / 'workflow/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class MarkerPreservation(unittest.TestCase):
    def scope(self):
        owned = tempfile.TemporaryDirectory(prefix='overte-owned-marker-contract-')
        self.addCleanup(owned.cleanup)
        root = Path(owned.name)
        self.enterContext(patch.object(installer, 'PROFILE', root / 'overte-browser-network'))
        self.enterContext(patch.object(installer, 'PREFIX', root / 'installed-prefix'))
        return root

    def test_regular_disabled_marker_refused_and_unchanged(self):
        root = self.scope()
        (root / 'disable').mkdir()
        marker = root / 'disable/overte-browser-network'
        marker.write_bytes(b'operator-disabled-state')
        with self.assertRaisesRegex(installer.Refusal, 'state-marker-preserved'):
            installer.preserve_owned_policy_markers()
        self.assertEqual(marker.read_bytes(), b'operator-disabled-state')

    def test_dangling_and_existing_symlink_markers_preserved_for_both_modes(self):
        for mode in ('disable', 'force-complain'):
            for exists in (False, True):
                with self.subTest(mode=mode, target_exists=exists):
                    root = self.scope()
                    (root / mode).mkdir()
                    original = root / 'original-profile'
                    if exists:
                        original.write_bytes(b'old-profile')
                    marker = root / mode / 'overte-browser-network'
                    marker.symlink_to(original)
                    before = os.readlink(marker)
                    with self.assertRaisesRegex(installer.Refusal, 'state-marker-preserved'):
                        installer.preserve_owned_policy_markers()
                    self.assertTrue(marker.is_symlink())
                    self.assertEqual(os.readlink(marker), before)

    def test_marker_refuses_before_parser_or_any_installation_mutation(self):
        root = self.scope()
        (root / 'disable').mkdir()
        marker = root / 'disable/overte-browser-network'
        marker.symlink_to(root / 'missing')
        with patch.object(installer.os, 'geteuid', return_value=0), \
                patch.object(installer, 'verified_bundle', return_value=({'python': '/usr/bin/python3.12'}, {})), \
                patch.object(installer, 'trusted_directory'), \
                patch.object(installer.subprocess, 'run') as run, \
                patch.object(installer, 'verify_python_imports') as imports:
            with self.assertRaisesRegex(installer.Refusal, 'state-marker-preserved'):
                installer.install(root / 'unused-bundle', '0' * 64)
            run.assert_not_called()
            imports.assert_not_called()
        self.assertFalse(installer.PREFIX.exists())
        self.assertFalse(installer.PROFILE.exists())
        self.assertTrue(marker.is_symlink())

    def test_unrelated_marker_is_preserved_without_blocking_owned_name(self):
        root = self.scope()
        directory = root / 'disable'
        directory.mkdir()
        marker = directory / 'unrelated-profile'
        marker.write_bytes(b'untouched')
        with patch.object(installer, 'trusted_directory') as trusted:
            installer.preserve_owned_policy_markers()
            trusted.assert_called_once_with(directory)
        self.assertEqual(marker.read_bytes(), b'untouched')

    def test_absent_marker_directories_add_no_write_or_directory(self):
        root = self.scope()
        installer.preserve_owned_policy_markers()
        self.assertEqual(list(root.iterdir()), [])

    def test_alias_marker_directory_refused_without_touching_target(self):
        root = self.scope()
        actual = root / 'actual-directory'
        actual.mkdir()
        alias = root / 'disable'
        alias.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(installer.Refusal, 'install-directory-alias'):
            installer.preserve_owned_policy_markers()
        self.assertTrue(alias.is_symlink())
        self.assertEqual(list(actual.iterdir()), [])

    def test_nonroot_writable_marker_directory_refuses(self):
        root = self.scope()
        directory = root / 'force-complain'
        directory.mkdir(mode=0o777)
        directory.chmod(0o777)
        with self.assertRaisesRegex(installer.Refusal, 'not-root-trusted'):
            installer.preserve_owned_policy_markers()
        self.assertFalse(installer.PROFILE.exists())


if __name__ == '__main__':
    unittest.main()
