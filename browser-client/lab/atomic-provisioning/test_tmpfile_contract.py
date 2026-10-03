# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Compare owned atomic-file primitives with the original user/IPC prefix."""
import ctypes
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ERRNOS = frozenset(('EEXIST', 'ENOENT', 'EPERM', 'EACCES', 'EOPNOTSUPP',
                    'EISDIR', 'EXDEV', 'EROFS', 'ENOSPC', 'EDQUOT', 'EIO',
                    'EINVAL', 'EBADF', 'ENOMEM', 'EMFILE', 'ENFILE', 'EINTR'))
SCOPE = 'owned-CPU-tmpfile-contract-not-native-or-kernel-cause'
PHASES = frozenset(('fixture-validation', 'open', 'existing-target-link',
                    'temporary-target-link', 'rename', 'readback'))
RESULTS = ERRNOS | {'not-attempted', 'success', 'unclassified'}


def checked_fixture(directory):
    """Pin an exact private directory containing only our unchanged seed."""
    root = Path(directory)
    if not root.is_absolute() or str(root.resolve(strict=True)) != os.fspath(directory):
        raise ValueError('owned-CPU-file-fixture-invalid')
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700 \
                or set(os.listdir(descriptor)) != {'settings.json'}:
            raise ValueError('owned-CPU-file-fixture-invalid')
        seed = os.open('settings.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                       dir_fd=descriptor)
        try:
            info = os.fstat(seed)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() \
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 \
                    or os.read(seed, 10) != b'owned-old':
                raise ValueError('owned-CPU-file-fixture-invalid')
        finally:
            os.close(seed)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def checked_row(raw):
    """Only fixed, bounded enums and genuine booleans reach assertion output."""
    if not isinstance(raw, bytes) or len(raw) > 4096:
        raise ValueError('owned-CPU-file-output-invalid')
    try:
        row = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError('owned-CPU-file-output-invalid') from None
    keys = {'scope', 'cause', 'completed', 'phase', 'existingTarget', 'temporaryTarget'}
    if not isinstance(row, dict) or set(row) not in (keys, keys | {'operationErrno'}) \
            or row.get('scope') != SCOPE or row.get('cause') != 'not-established' \
            or type(row.get('completed')) is not bool \
            or not isinstance(row.get('phase'), str) or row['phase'] not in PHASES \
            or any(not isinstance(row.get(key), str) or row[key] not in RESULTS
                   for key in ('existingTarget', 'temporaryTarget')) \
            or ('operationErrno' in row and (not isinstance(row['operationErrno'], str)
                or row['operationErrno'] not in ERRNOS | {'unclassified', 'fixture-invalid'})):
        raise ValueError('owned-CPU-file-output-invalid')
    return row


def run_fixture(command):
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
    except subprocess.TimeoutExpired:
        raise ValueError('owned-CPU-file-launch-timeout') from None
    except OSError:
        raise ValueError('owned-CPU-file-launch-unavailable') from None
    if result.returncode:
        raise ValueError('owned-CPU-file-launch-refused')
    return checked_row(result.stdout)


def owned_file_operations(directory):
    """No Qt/native process, network, profile change or arbitrary capture."""
    row = {'scope': SCOPE,
           'cause': 'not-established', 'completed': False, 'phase': 'fixture-validation',
           'existingTarget': 'not-attempted', 'temporaryTarget': 'not-attempted'}
    descriptor = None
    directory_fd = None
    try:
        directory_fd = checked_fixture(directory)
        row['phase'] = 'open'
        descriptor = os.open('.', os.O_TMPFILE | os.O_RDWR, 0o600, dir_fd=directory_fd)
        os.write(descriptor, b'owned-new')
        os.fchmod(descriptor, 0o644)
        os.fdatasync(descriptor)
        library = ctypes.CDLL(None, use_errno=True)
        link = library.linkat
        link.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int)
        link.restype = ctypes.c_int

        def attempt(destination):
            ctypes.set_errno(0)
            result = link(-100, f'/proc/self/fd/{descriptor}'.encode(), directory_fd,
                          destination, 0x400)  # AT_SYMLINK_FOLLOW
            if result == 0:
                return 'success'
            name = errno.errorcode.get(ctypes.get_errno())
            return name if name in ERRNOS else 'unclassified'

        row['phase'] = 'existing-target-link'
        row['existingTarget'] = attempt(b'settings.json')
        row['phase'] = 'temporary-target-link'
        temporary = b'settings.json.ABCDEF'
        row['temporaryTarget'] = attempt(temporary)
        if row['existingTarget'] != 'EEXIST' or row['temporaryTarget'] != 'success':
            return row
        row['phase'] = 'rename'
        os.replace(temporary, 'settings.json', src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        row['phase'] = 'readback'
        readback = os.open('settings.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            row['completed'] = os.read(readback, 10) == b'owned-new'
        finally:
            os.close(readback)
    except ValueError:
        row['operationErrno'] = 'fixture-invalid'
    except OSError as error:
        name = errno.errorcode.get(error.errno)
        row['operationErrno'] = name if name in ERRNOS else 'unclassified'
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory_fd is not None:
            os.close(directory_fd)
    return row


class TmpfileContract(unittest.TestCase):
    def run_owned(self, prefix):
        with tempfile.TemporaryDirectory(prefix='owned-atomic-file-contract-') as directory:
            root = Path(directory)
            (root / 'settings.json').write_bytes(b'owned-old')
            (root / 'settings.json').chmod(0o600)
            try:
                row = run_fixture([*prefix, sys.executable, str(Path(__file__).resolve()),
                                   '--owned-fixture', directory])
            except ValueError as error:
                self.fail(str(error))
            self.assertEqual(row['scope'], 'owned-CPU-tmpfile-contract-not-native-or-kernel-cause')
            self.assertEqual(row['cause'], 'not-established')
            self.assertTrue(row['completed'], json.dumps(row, sort_keys=True))
            self.assertEqual(row['existingTarget'], 'EEXIST')
            self.assertEqual(row['temporaryTarget'], 'success')
            self.assertEqual((root / 'settings.json').read_bytes(), b'owned-new')

    def test_host_atomic_tmpfile_materialization_and_readback(self):
        self.run_owned([])

    def historical_original_user_ipc_prefix_atomic_tmpfile_materialization_and_readback(self):
        self.run_owned(['/usr/bin/unshare', '--user', '--map-current-user', '--ipc', '--'])


class TmpfileBoundaryTests(unittest.TestCase):
    def test_unowned_or_changed_fixtures_refuse_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / 'settings.json'
            seed.write_bytes(b'owned-old')
            seed.chmod(0o600)
            alias = root.parent / (root.name + '-alias')
            alias.symlink_to(root, target_is_directory=True)
            try:
                for path in (alias, str(root) + '/.'):
                    self.assertFalse(owned_file_operations(path)['completed'])
                    self.assertEqual(seed.read_bytes(), b'owned-old')
                root.chmod(0o755)
                self.assertFalse(owned_file_operations(root)['completed'])
                root.chmod(0o700)
                seed.write_bytes(b'foreign-file')
                self.assertFalse(owned_file_operations(root)['completed'])
                self.assertEqual(seed.read_bytes(), b'foreign-file')
                seed.write_bytes(b'owned-old')
                (root / 'other').write_bytes(b'foreign')
                self.assertFalse(owned_file_operations(root)['completed'])
                self.assertEqual(seed.read_bytes(), b'owned-old')
                (root / 'other').unlink()
                seed.unlink()
                seed.symlink_to(root / 'absent')
                self.assertFalse(owned_file_operations(root)['completed'])
                self.assertFalse((root / 'absent').exists())
            finally:
                alias.unlink()

    def test_unknown_keys_types_enums_and_unbounded_output_are_rejected(self):
        row = {'scope': SCOPE, 'cause': 'not-established', 'completed': False,
               'phase': 'open', 'existingTarget': 'not-attempted',
               'temporaryTarget': 'not-attempted'}
        self.assertEqual(checked_row(json.dumps(row).encode()), row)
        for changed in ({**row, 'privatePath': '/private'}, {**row, 'completed': 1},
                        {**row, 'phase': '/private'}, {**row, 'temporaryTarget': []},
                        {**row, 'operationErrno': '/private'}):
            with self.assertRaisesRegex(ValueError, '^owned-CPU-file-output-invalid$'):
                checked_row(json.dumps(changed).encode())
        for raw in (b'private-json', b' ' * 4097, b'\xff', b'[]'):
            with self.assertRaisesRegex(ValueError, '^owned-CPU-file-output-invalid$'):
                checked_row(raw)

    def test_launch_failures_never_export_private_argv_or_exception_text(self):
        for failure, category in ((subprocess.TimeoutExpired(['/private'], 5), 'timeout'),
                                  (OSError('/private'), 'unavailable')):
            with patch.object(subprocess, 'run', side_effect=failure):
                with self.assertRaisesRegex(ValueError, '^owned-CPU-file-launch-' + category + '$'):
                    run_fixture(['/private'])
        result = subprocess.CompletedProcess(['/private'], 1, b'/private', b'/private')
        with patch.object(subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(ValueError, '^owned-CPU-file-launch-refused$'):
                run_fixture(['/private'])


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--owned-fixture':
        print(json.dumps(owned_file_operations(sys.argv[2]), sort_keys=True))
    else:
        unittest.main()
