# SPDX-License-Identifier: Apache-2.0
import hashlib
import importlib.util
import stat
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('preparation', Path(__file__).with_name('prepare-apparmor-userns.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class TargetValidation(unittest.TestCase):
    def validate(self, content, *, recorded=None, disabled=False, obsolete=False):
        checksum = recorded or hashlib.md5(content, usedforsecurity=False).hexdigest()
        def command(arguments):
            if '--search' in arguments:
                return 'apparmor: /etc/apparmor.d/bwrap-userns-restrict\n'
            if '--showformat=${db:Status-Status}' in arguments:
                return 'installed'
            if '--showformat=${Conffiles}' in arguments:
                return f' /etc/apparmor.d/bwrap-userns-restrict {checksum}' + (' obsolete' if obsolete else '') + '\n'
            raise AssertionError('Unexpected command')
        with patch.object(m, 'trusted_file', return_value=SimpleNamespace(st_mode=stat.S_IFREG | 0o755)), \
             patch.object(m, 'package_owns_exact_executable', return_value=True), \
             patch.object(m, 'command', side_effect=command), \
             patch.object(m.os.path, 'lexists', return_value=disabled), \
             patch.object(Path, 'read_bytes', return_value=content):
            return m.inspect_target(*m.TARGETS[0])

    def test_packaged_profile_is_checked_without_altering_its_policy(self):
        policy = b'abi <abi/4.0>,\nprofile bwrap /usr/bin/bwrap {\n deny capability,\n}\n'
        result = self.validate(policy)
        self.assertTrue(result['packageConffileUnmodified'])
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

    def test_obsolete_conffile_is_not_treated_as_current_shipped_policy(self):
        with self.assertRaisesRegex(m.PolicyError, 'differs-from-recorded'):
            self.validate(b'abi <abi/4.0>,\nprofile bwrap /usr/bin/bwrap {}\n', obsolete=True)


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
                    'sha256': '1' * 64, 'packageConffileUnmodified': True}
        return mutations, command, inspect

    def prepare(self, loaded, *, inspection=None, command_override=None):
        mutations, command, inspect = self.context(loaded, inspection)
        with patch.object(m.os, 'geteuid', return_value=0), \
             patch.object(Path, 'resolve', return_value=Path('/usr/sbin/apparmor_parser')), \
             patch.object(m, 'trusted_file'), \
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
        self.assertEqual(mutations, [['/usr/sbin/apparmor_parser', '-a', '/etc/apparmor.d/unshare-userns-restrict']])
        self.assertEqual(result['targets'][0]['action'], 'preserved-existing-loaded-profile')
        self.assertEqual(result['targets'][1]['action'], 'loaded-unchanged-package-profile')
        self.assertEqual(result['normalSandboxAndNativePreflight'], 'still-required')

    def test_second_target_invalidates_batch_before_any_policy_load(self):
        def invalid(*target):
            if target[2] == 'unshare':
                raise m.PolicyError('distro-profile-differs-from-recorded-package-conffile')
        calls = []
        with self.assertRaises(m.PolicyError):
            self.prepare([{}], inspection=invalid, command_override=lambda args: calls.append(args))
        self.assertEqual(calls, [])

    def test_missing_profile_after_load_is_not_success(self):
        with self.assertRaisesRegex(m.PolicyError, 'remained-unloaded'):
            self.prepare([{}, {}])

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


if __name__ == '__main__':
    unittest.main()
