# SPDX-License-Identifier: Apache-2.0
import hashlib
import importlib.util
import os
import tempfile
import stat
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('preparation', Path(__file__).with_name('prepare-apparmor-userns.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class TargetValidation(unittest.TestCase):
    def validate(self, content, *, recorded=None, disabled=False, malformed=False):
        checksum = recorded or hashlib.md5(content, usedforsecurity=False).hexdigest()
        def command(arguments):
            if '--search' in arguments:
                return 'apparmor-profiles: /usr/share/apparmor/extra-profiles/bwrap-userns-restrict\n'
            if '--showformat=${db:Status-Status}' in arguments:
                return 'installed'
            raise AssertionError('Unexpected command')
        with patch.object(m, 'trusted_file', return_value=SimpleNamespace(st_mode=stat.S_IFREG | 0o755)), \
             patch.object(m, 'package_owns_exact_executable', return_value=True), \
             patch.object(m, 'command', side_effect=command), \
             patch.object(m.os.path, 'lexists', return_value=disabled), \
             patch.object(Path, 'read_bytes', return_value=content), \
             patch.object(Path, 'read_text', return_value=f'{checksum}  usr/share/apparmor/extra-profiles/bwrap-userns-restrict' + (' extra' if malformed else '') + '\n'):
            return m.inspect_target(*m.TARGETS[0])

    def test_packaged_profile_is_checked_without_altering_its_policy(self):
        policy = b'abi <abi/4.0>,\nprofile bwrap /usr/bin/bwrap {\n deny capability,\n}\n'
        result = self.validate(policy)
        self.assertTrue(result['packageFileUnmodified'])
        self.assertEqual(result['sha256'], hashlib.sha256(policy).hexdigest())

    def test_unconfined_substitution_with_mismatching_package_hash_is_refused(self):
        replacement = b'abi <abi/4.0>,\nprofile bwrap /usr/bin/bwrap flags=(unconfined) { userns, }\n'
        with self.assertRaisesRegex(m.PolicyError, 'differs-from-recorded'):
            self.validate(replacement, recorded='0' * 32)

    def test_disabled_policy_is_respected(self):
        with self.assertRaisesRegex(m.PolicyError, 'disabled-by-operator'):
            self.validate(b'irrelevant', disabled=True)

    def test_unknown_abi_fails_even_if_package_checksum_matches(self):
        with self.assertRaisesRegex(m.PolicyError, 'abi-not-reviewed'):
            self.validate(b'abi <abi/5.0>,\nprofile bwrap /usr/bin/bwrap {}\n')

    def test_different_main_profile_fails_even_if_package_checksum_matches(self):
        with self.assertRaisesRegex(m.PolicyError, 'main-profile-name-not-reviewed'):
            self.validate(b'abi <abi/4.0>,\nprofile unrelated /usr/bin/bwrap {}\n')

    def test_malformed_manifest_entry_is_not_current_shipped_policy(self):
        with self.assertRaisesRegex(m.PolicyError, 'missing-or-ambiguous'):
            self.validate(b'abi <abi/4.0>,\nprofile bwrap /usr/bin/bwrap {}\n', malformed=True)


class PreparationOwnership(unittest.TestCase):
    def context(self, loaded, inspection=None):
        mutations = []
        def command(arguments):
            mutations.append(arguments)
            return ''
        def inspect(*target):
            if inspection:
                inspection(*target)
            return {'filename': target[0], 'package': target[1], 'profile': target[2],
                    'sha256': '1' * 64, 'packageFileUnmodified': True}
        return mutations, command, inspect

    def prepare(self, loaded, *, inspection=None, command_override=None):
        mutations, command, inspect = self.context(loaded, inspection)
        with patch.object(m.os, 'geteuid', return_value=0), \
             patch.object(Path, 'resolve', return_value=Path('/usr/sbin/apparmor_parser')), \
             patch.object(m, 'trusted_file'), \
             patch.object(m, 'harden_profile_parent', return_value={'action': 'preserved-secure-mode'}), \
             patch.object(m, 'package_owns_exact_executable', return_value=True), \
             patch.object(m, 'loaded_profiles', side_effect=loaded), \
             patch.object(m, 'inspect_target', side_effect=inspect), \
             patch.object(m, 'command', side_effect=command_override or command):
            result = m.prepare()
        return result, mutations

    def test_existing_stronger_loaded_profiles_are_not_reloaded(self):
        current = {'bwrap': 'enforce', 'unshare': 'enforce'}
        result, mutations = self.prepare([current, current])
        self.assertEqual(mutations, [])
        self.assertEqual(result['before'], result['after'])
        self.assertTrue(all(target['action'] == 'preserved-existing-loaded-profile' for target in result['targets']))

    def test_only_absent_main_profile_loads_exact_packaged_file(self):
        before = {'bwrap': 'enforce'}
        after = {'bwrap': 'enforce', 'unshare': 'enforce'}
        result, mutations = self.prepare([before, after, after])
        self.assertEqual(mutations, [['/usr/sbin/apparmor_parser', '-a', '-K', '-b', '/etc/apparmor.d', '/usr/share/apparmor/extra-profiles/unshare-userns-restrict']])
        self.assertEqual(result['targets'][0]['action'], 'preserved-existing-loaded-profile')
        self.assertEqual(result['targets'][1]['action'], 'loaded-unchanged-package-profile')
        self.assertEqual(result['normalSandboxAndNativePreflight'], 'still-required')

    def test_second_target_invalidates_batch_before_any_policy_load(self):
        def invalid(*target):
            if target[2] == 'unshare':
                raise m.PolicyError('distro-profile-differs-from-recorded-package-file')
        calls = []
        with self.assertRaises(m.PolicyError):
            self.prepare([{}], inspection=invalid, command_override=lambda args: calls.append(args))
        self.assertEqual(calls, [])

    def test_missing_profile_after_load_is_not_success(self):
        with self.assertRaisesRegex(m.PolicyError, 'remained-unloaded'):
            self.prepare([{}, {}])

    def test_hardening_refusal_prevents_target_inspection_and_policy_load(self):
        with patch.object(m.os, 'geteuid', return_value=0), \
             patch.object(Path, 'resolve', return_value=Path('/usr/sbin/apparmor_parser')), \
             patch.object(m, 'trusted_file'), \
             patch.object(m, 'package_owns_exact_executable', return_value=True), \
             patch.object(m, 'harden_profile_parent', side_effect=m.PolicyError('distro-directory-identity-changed')), \
             patch.object(m, 'inspect_target') as inspect, patch.object(m, 'command') as command:
            with self.assertRaisesRegex(m.PolicyError, 'identity-changed'):
                m.prepare()
            inspect.assert_not_called()
            command.assert_not_called()

    def test_nonroot_actor_never_attempts_policy_mutation(self):
        with patch.object(m.os, 'geteuid', return_value=1000), patch.object(m, 'command') as command:
            with self.assertRaisesRegex(m.PolicyError, 'root-required'):
                m.prepare()
            command.assert_not_called()

    def test_group_writable_or_nonroot_executables_are_refused(self):
        path = Path('/usr/bin/bwrap')
        for owner, mode in ((1000, 0o755), (0, 0o775), (0, 0o757)):
            with patch.object(Path, 'resolve', return_value=path), \
                 patch.object(Path, 'stat', return_value=SimpleNamespace(st_uid=owner, st_mode=stat.S_IFREG | mode)):
                with self.assertRaisesRegex(m.PolicyError, 'owner-or-write-permissions-invalid'):
                    m.trusted_file(path)

    def test_package_file_parent_writability_is_rejected(self):
        path = m.PACKAGE_MANIFEST
        def info(candidate):
            return SimpleNamespace(st_uid=0,
                st_mode=(stat.S_IFREG | 0o644) if candidate == path else stat.S_IFDIR | (0o775 if candidate == path.parent else 0o755))
        with patch.object(Path, 'resolve', autospec=True, side_effect=lambda candidate, **kwargs: candidate), \
             patch.object(Path, 'stat', autospec=True, side_effect=info):
            with self.assertRaisesRegex(m.PolicyError, 'parent-directory-owner-or-write'):
                m.trusted_file(path)

    def test_manifest_symlink_is_rejected(self):
        path = m.PACKAGE_MANIFEST
        with patch.object(Path, 'resolve', return_value=Path('/tmp/operator-manifest')), \
             patch.object(Path, 'stat', return_value=SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o644)):
            with self.assertRaisesRegex(m.PolicyError, 'not-canonical'):
                m.trusted_file(path)


class DirectoryHardening(unittest.TestCase):
    """Real owned temporary descriptors/chmod; only root ownership is simulated."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name) / 'share'
        self.parent.mkdir()
        self.parent.chmod(0o777)
        self.original_stat = Path.stat
        self.original_fstat = os.fstat
        self.ancestors = set(self.parent.parents)

    def root_info(self, info, *, ancestor=False, uid=0):
        return SimpleNamespace(st_mode=(stat.S_IFDIR | 0o755) if ancestor else info.st_mode,
                               st_uid=uid, st_dev=info.st_dev, st_ino=info.st_ino)

    def contexts(self, *, target_uid=0, unsafe_ancestor=None):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(m, 'PROFILE_PARENT', self.parent))
        stack.enter_context(patch.object(m.os, 'geteuid', return_value=0))
        def path_stat(candidate, **kwargs):
            info = self.original_stat(candidate, **kwargs)
            result = self.root_info(info, ancestor=candidate in self.ancestors,
                                    uid=target_uid if candidate == self.parent else 0)
            if candidate == unsafe_ancestor:
                result.st_mode |= stat.S_IWGRP
            return result
        stack.enter_context(patch.object(Path, 'stat', autospec=True, side_effect=path_stat))
        stack.enter_context(patch.object(m.os, 'fstat', side_effect=lambda fd:
                                        self.root_info(self.original_fstat(fd), uid=target_uid)))
        return stack

    def test_real_writable_directory_tightens_without_changing_profile_bytes(self):
        file = self.parent / 'packaged-profile'
        content = b'abi <abi/4.0>,\nprofile bwrap /usr/bin/bwrap {}\n'
        file.write_bytes(content)
        file.chmod(0o644)
        with self.contexts():
            # Counterfactual: the unchanged trust guard refuses the old image.
            with self.assertRaisesRegex(m.PolicyError, 'parent-directory-owner-or-write'):
                m.trusted_file(file)
            report = m.harden_profile_parent()
            self.assertEqual(report['beforeMode'], '0777')
            self.assertEqual(report['afterMode'], '0755')
            m.trusted_file(file)
        self.assertEqual(stat.S_IMODE(self.parent.stat().st_mode), 0o755)
        self.assertEqual(file.read_bytes(), content)

    def test_secure_directory_is_idempotent_and_special_bits_preserved(self):
        self.parent.chmod(0o3755)
        with self.contexts(), patch.object(m.os, 'fchmod', wraps=os.fchmod) as chmod:
            report = m.harden_profile_parent()
            self.assertEqual(report['action'], 'preserved-secure-mode')
            self.assertEqual(report['afterMode'], '3755')
            chmod.assert_not_called()

    def test_only_group_other_write_bits_removed(self):
        self.parent.chmod(0o3771)
        with self.contexts():
            report = m.harden_profile_parent()
        self.assertEqual(report['afterMode'], '3751')
        self.assertEqual(stat.S_IMODE(self.parent.stat().st_mode), 0o3751)

    def test_nonroot_owner_refused_before_chmod(self):
        with self.contexts(target_uid=1000), patch.object(m.os, 'fchmod') as chmod:
            with self.assertRaisesRegex(m.PolicyError, 'not-root-owned'):
                m.harden_profile_parent()
            chmod.assert_not_called()

    def test_writable_ancestor_refused_before_open(self):
        with self.contexts(unsafe_ancestor=self.parent.parent), patch.object(m.os, 'open') as opened:
            with self.assertRaisesRegex(m.PolicyError, 'ancestor-is-not-trusted'):
                m.harden_profile_parent()
            opened.assert_not_called()

    def test_symlink_and_nondirectory_refused_without_touching_target(self):
        original = self.parent.with_name('original')
        self.parent.rename(original)
        self.parent.symlink_to(original, target_is_directory=True)
        with self.contexts(), patch.object(m.os, 'fchmod') as chmod:
            with self.assertRaisesRegex(m.PolicyError, 'not-canonical'):
                m.harden_profile_parent()
            chmod.assert_not_called()
        self.parent.unlink()
        self.parent.write_text('not a directory')
        with self.contexts(), self.assertRaises(OSError):
            m.harden_profile_parent()
        self.assertEqual(self.parent.read_text(), 'not a directory')

    def test_path_replacement_after_open_refused_and_descriptor_closed(self):
        original_open = os.open
        opened = []
        held = self.parent.with_name('held')
        def replace(*args, **kwargs):
            descriptor = original_open(*args, **kwargs)
            opened.append(descriptor)
            self.parent.rename(held)
            self.parent.mkdir(mode=0o777)
            return descriptor
        with self.contexts(), patch.object(m.os, 'open', side_effect=replace), \
                patch.object(m.os, 'fchmod') as chmod:
            with self.assertRaisesRegex(m.PolicyError, 'identity-changed'):
                m.harden_profile_parent()
            chmod.assert_not_called()
        with self.assertRaises(OSError):
            self.original_fstat(opened[0])
        self.assertEqual(stat.S_IMODE(held.stat().st_mode), 0o777)

    def test_post_chmod_replacement_refused_without_touching_replacement(self):
        original_chmod = os.fchmod
        held = self.parent.with_name('held')
        def replace(descriptor, mode):
            original_chmod(descriptor, mode)
            self.parent.rename(held)
            self.parent.mkdir()
            self.parent.chmod(0o777)
        with self.contexts(), patch.object(m.os, 'fchmod', side_effect=replace):
            with self.assertRaisesRegex(m.PolicyError, 'hardening-not-verified'):
                m.harden_profile_parent()
        self.assertEqual(stat.S_IMODE(held.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(self.parent.stat().st_mode), 0o777)

    def test_nonroot_actor_has_no_filesystem_mutation(self):
        with patch.object(m.os, 'geteuid', return_value=1000), patch.object(m.os, 'open') as opened:
            with self.assertRaisesRegex(m.PolicyError, 'root-required'):
                m.harden_profile_parent()
            opened.assert_not_called()


class PackageManifest(unittest.TestCase):
    def digest(self, document):
        with patch.object(m, 'trusted_file') as trusted, patch.object(Path, 'read_text', return_value=document):
            value = m.package_file_digest(m.PROFILE_DIRECTORY / 'bwrap-userns-restrict')
        trusted.assert_called_once_with(Path('/var/lib/dpkg/info/apparmor-profiles.md5sums'))
        return value

    def test_exact_current_package_entry_is_accepted(self):
        self.assertEqual(self.digest('626aa32b8f05f9ec8cde755016c9b34c  usr/share/apparmor/extra-profiles/bwrap-userns-restrict\n'),
                         '626aa32b8f05f9ec8cde755016c9b34c')

    def test_duplicate_target_entries_are_rejected_even_if_identical(self):
        line = '626aa32b8f05f9ec8cde755016c9b34c  usr/share/apparmor/extra-profiles/bwrap-userns-restrict\n'
        with self.assertRaisesRegex(m.PolicyError, 'missing-or-ambiguous'):
            self.digest(line * 2)

    def test_other_paths_conffiles_or_near_match_cannot_authorize_extra_profile(self):
        for path in ['/usr/share/apparmor/extra-profiles/bwrap-userns-restrict',
                     'etc/apparmor.d/bwrap-userns-restrict',
                     'usr/share/apparmor/extra-profiles/bwrap-userns-restrict-backup',
                     'usr/share/apparmor/extra-profiles/../extra-profiles/bwrap-userns-restrict']:
            with self.subTest(path=path), self.assertRaisesRegex(m.PolicyError, 'missing-or-ambiguous'):
                self.digest('626aa32b8f05f9ec8cde755016c9b34c  ' + path + '\n')

    def test_manifest_size_is_bounded(self):
        with self.assertRaisesRegex(m.PolicyError, 'manifest-size-limit'):
            self.digest(' ' * (1024 * 1024 + 1))

    def test_actual_unshare_child_profile_name_is_retained_in_diagnostics(self):
        document = 'unshare (enforce)\nunshare//unpriv (enforce)\nunrelated-private-app (enforce)\n'
        with patch.object(Path, 'read_text', return_value=document):
            self.assertEqual(m.loaded_profiles(), {'unshare': 'enforce', 'unshare//unpriv': 'enforce'})


if __name__ == '__main__':
    unittest.main()
