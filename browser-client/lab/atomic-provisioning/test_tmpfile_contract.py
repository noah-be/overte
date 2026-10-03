# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Compare owned atomic-file primitives with the original user/IPC prefix."""
import ctypes
import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ERRNOS = frozenset(('EEXIST', 'ENOENT', 'EPERM', 'EACCES', 'EOPNOTSUPP',
                    'EISDIR', 'EXDEV', 'EROFS', 'ENOSPC', 'EDQUOT', 'EIO',
                    'EINVAL', 'EBADF', 'ENOMEM', 'EMFILE', 'ENFILE', 'EINTR'))


def owned_file_operations(directory):
    """No Qt/native process, network, profile change or arbitrary capture."""
    row = {'scope': 'owned-CPU-tmpfile-contract-not-native-or-kernel-cause',
           'cause': 'not-established', 'completed': False, 'phase': 'open',
           'existingTarget': 'not-attempted', 'temporaryTarget': 'not-attempted'}
    descriptor = None
    try:
        root = Path(directory)
        descriptor = os.open(root, os.O_TMPFILE | os.O_RDWR, 0o600)
        os.write(descriptor, b'owned-new')
        os.fchmod(descriptor, 0o644)
        os.fdatasync(descriptor)
        library = ctypes.CDLL(None, use_errno=True)
        link = library.linkat
        link.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int)
        link.restype = ctypes.c_int

        def attempt(destination):
            ctypes.set_errno(0)
            result = link(-100, f'/proc/self/fd/{descriptor}'.encode(), -100,
                          os.fsencode(destination), 0x400)  # AT_SYMLINK_FOLLOW
            if result == 0:
                return 'success'
            name = errno.errorcode.get(ctypes.get_errno())
            return name if name in ERRNOS else 'unclassified'

        row['phase'] = 'existing-target-link'
        row['existingTarget'] = attempt(root / 'settings.json')
        row['phase'] = 'temporary-target-link'
        temporary = root / 'settings.json.ABCDEF'
        row['temporaryTarget'] = attempt(temporary)
        if row['existingTarget'] != 'EEXIST' or row['temporaryTarget'] != 'success':
            return row
        row['phase'] = 'rename'
        os.replace(temporary, root / 'settings.json')
        row['phase'] = 'readback'
        row['completed'] = (root / 'settings.json').read_bytes() == b'owned-new'
    except OSError as error:
        name = errno.errorcode.get(error.errno)
        row['operationErrno'] = name if name in ERRNOS else 'unclassified'
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return row


class TmpfileContract(unittest.TestCase):
    def run_owned(self, prefix):
        with tempfile.TemporaryDirectory(prefix='owned-atomic-file-contract-') as directory:
            root = Path(directory)
            (root / 'settings.json').write_bytes(b'owned-old')
            result = subprocess.run([*prefix, sys.executable, str(Path(__file__).resolve()),
                                     '--owned-fixture', directory], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            self.assertEqual(result.returncode, 0,
                             f'owned-CPU-file-launch-refused:exit={result.returncode};stderrBytes={len(result.stderr)}')
            row = json.loads(result.stdout)
            self.assertEqual(row['scope'], 'owned-CPU-tmpfile-contract-not-native-or-kernel-cause')
            self.assertEqual(row['cause'], 'not-established')
            self.assertTrue(row['completed'], json.dumps(row, sort_keys=True))
            self.assertEqual(row['existingTarget'], 'EEXIST')
            self.assertEqual(row['temporaryTarget'], 'success')
            self.assertEqual((root / 'settings.json').read_bytes(), b'owned-new')

    def test_host_atomic_tmpfile_materialization_and_readback(self):
        self.run_owned([])

    def test_original_user_ipc_prefix_atomic_tmpfile_materialization_and_readback(self):
        self.run_owned(['/usr/bin/unshare', '--user', '--map-current-user', '--ipc', '--'])


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--owned-fixture':
        print(json.dumps(owned_file_operations(sys.argv[2]), sort_keys=True))
    else:
        unittest.main()
