# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""CPU-only proposed launch order; original native launcher/gate stays unchanged.

Use the signed system bwrap profile, retire capabilities before its final exec,
and measure the actual child. The optional fixed filter only refuses unnamed
temporary creation and openat2; it cannot relax an inherited policy. No Qt,
DomainServer, services, loader injection or profile changes are involved.
"""
import ctypes
import errno
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile
import unittest
from confined_launch import base_command, sealed_filter

HERE = Path(__file__).resolve().parent
CAPS = ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb')
KEYS = frozenset(('scope', 'zeroCapabilities', 'noNewPrivileges', 'userIsolated',
                  'ipcIsolated', 'profile', 'tracedSync', 'atomicReadback',
                  'tmpfileDenied', 'openat2Denied', 'operationErrno', 'x32Denied'))
PROFILES = frozenset(('signed-bwrap-child-enforce', 'local-unqualified', 'unknown'))


def child(directory, parent_user, parent_ipc, filtered):
    row = dict.fromkeys(KEYS, False)
    row['scope'] = 'CPU-proposed-launch-not-native-acceptance'
    row['profile'] = 'unknown'
    row['operationErrno'] = 'none'
    try:
        root = Path(directory)
        spec = importlib.util.spec_from_file_location('owned_tmpfile', HERE / 'test_tmpfile_contract.py')
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        dfd = fixture.checked_fixture(directory)
        try:
            status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines()
                          if ':' in line)
            row['zeroCapabilities'] = all(int(status[name], 16) == 0 for name in CAPS)
            row['noNewPrivileges'] = status['NoNewPrivs'].strip() == '1'
            row['userIsolated'] = os.readlink('/proc/self/ns/user') != parent_user
            row['ipcIsolated'] = os.readlink('/proc/self/ns/ipc') != parent_ipc
            label = Path('/proc/self/attr/current').read_text().strip()
            if label == 'bwrap//&unpriv_bwrap (enforce)':
                row['profile'] = 'signed-bwrap-child-enforce'
            elif not os.environ.get('GITHUB_ACTIONS'):
                row['profile'] = 'local-unqualified'
            if not all(row[name] for name in ('zeroCapabilities', 'noNewPrivileges', 'userIsolated', 'ipcIsolated')):
                return row
            if filtered:
                library = ctypes.CDLL(None, use_errno=True)
                library.syscall.restype = ctypes.c_long
                # Exercise both real open ABI entry points, not a BPF simulator.
                for number, arguments in (
                        (2, (ctypes.c_char_p(os.fsencode(root)), os.O_TMPFILE | os.O_RDWR, 0o600)),
                        (257, (dfd, ctypes.c_char_p(b'.'), os.O_TMPFILE | os.O_RDWR, 0o600))):
                    ctypes.set_errno(0)
                    result = library.syscall(ctypes.c_long(number), *arguments)
                    if result != -1 or ctypes.get_errno() != 95:
                        if result >= 0:
                            os.close(result)
                        return row
                row['tmpfileDenied'] = True
                ctypes.set_errno(0)
                result = library.syscall(ctypes.c_long(437), dfd, ctypes.c_char_p(b'.'), None, 0)
                row['openat2Denied'] = result == -1 and ctypes.get_errno() == 38
                if not row['openat2Denied']:
                    return row
                resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                pid = os.fork()
                if pid == 0:
                    library.syscall(ctypes.c_long(0x40000000 | 39))
                    os._exit(1)
                _, status = os.waitpid(pid, 0)
                row['x32Denied'] = os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGSYS
                if not row['x32Denied']:
                    return row
                temporary = os.open('settings.json.ABCDEF', os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                    | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
                try:
                    os.write(temporary, b'owned-new')
                    os.fchmod(temporary, 0o644)
                    os.fdatasync(temporary)
                finally:
                    os.close(temporary)
                os.replace('settings.json.ABCDEF', 'settings.json', src_dir_fd=dfd, dst_dir_fd=dfd)
                row['atomicReadback'] = (root / 'settings.json').read_bytes() == b'owned-new'
            else:
                row['atomicReadback'] = fixture.owned_file_operations(directory)['completed']
        finally:
            os.close(dfd)
        spec = importlib.util.spec_from_file_location('owned_observer', HERE / 'observer.py')
        observer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(observer)
        capture = root / 'capture'
        capture.mkdir(mode=0o700)
        marker = root / 'marker.py'
        marker.write_text('import os\nfrom pathlib import Path\n'
                          'caps=dict(x.split(":",1) for x in Path("/proc/self/status").read_text().splitlines() if ":" in x)\n'
                          'assert all(int(caps[x],16)==0 for x in ("CapInh","CapPrm","CapEff","CapBnd","CapAmb"))\n'
                          'assert caps["NoNewPrivs"].strip()=="1"\n'
                          'f=Path("trace-owned").open("xb");f.write(b"x");f.flush();os.fsync(f.fileno());f.close()\n')
        tracer = Path(os.environ.get('ATOMIC_DIAGNOSTIC_STRACE', '/usr/bin/strace'))
        observed = observer.observe_owned(tracer, [sys.executable, str(marker)], dict(os.environ),
                                          root, capture, seconds=5)
        row['tracedSync'] = observed['exitCode'] == 0 and observed['projection']['calls']['fsync']['success'] >= 1
    except OSError as error:
        name = errno.errorcode.get(error.errno)
        row['operationErrno'] = name if name in ('ENOENT', 'EPERM', 'EACCES', 'EROFS', 'EINVAL') else 'unclassified'
    except (ValueError, KeyError):
        row['operationErrno'] = 'input-refused'
    return row


class ConfinedLaunchTests(unittest.TestCase):
    def run_owned(self, filtered):
        fd = None
        with tempfile.TemporaryDirectory(prefix='owned-confinement-order-') as directory:
            root = Path(directory)
            seed = root / 'settings.json'
            seed.write_bytes(b'owned-old')
            seed.chmod(0o600)
            command = base_command((directory,), directory)
            try:
                if filtered:
                    fd = sealed_filter()
                    command += ['--seccomp', str(fd)]
                command += ['--', sys.executable, str(Path(__file__).resolve()), '--owned-child',
                            directory, os.readlink('/proc/self/ns/user'), os.readlink('/proc/self/ns/ipc'),
                            'filtered' if filtered else 'original-tmpfile']
                try:
                    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, timeout=8, pass_fds=() if fd is None else (fd,))
                except (OSError, subprocess.TimeoutExpired):
                    self.fail('confined-CPU-launch-unavailable-or-timeout')
                self.assertEqual(result.returncode, 0, 'confined-CPU-launch-refused')
                self.assertLessEqual(len(result.stdout), 4096, 'confined-CPU-output-limit')
                try:
                    row = json.loads(result.stdout)
                except (ValueError, UnicodeError):
                    self.fail('confined-CPU-output-invalid')
                self.assertIs(type(row), dict, 'confined-CPU-output-type-invalid')
                self.assertEqual(set(row), KEYS, 'confined-CPU-output-fields-invalid')
                self.assertEqual(row['scope'], 'CPU-proposed-launch-not-native-acceptance')
                self.assertIn(row['profile'], PROFILES)
                self.assertIn(row['operationErrno'], ('none', 'ENOENT', 'EPERM', 'EACCES', 'EROFS', 'EINVAL', 'unclassified', 'input-refused'))
                for name in KEYS - {'scope', 'profile', 'operationErrno'}:
                    self.assertIs(type(row[name]), bool, 'confined-CPU-output-type-invalid')
                print('ATOMIC_CONFINED_CPU:' + json.dumps(row, sort_keys=True), flush=True)
                for name in ('zeroCapabilities', 'noNewPrivileges', 'userIsolated', 'ipcIsolated',
                             'tracedSync'):
                    self.assertTrue(row[name], json.dumps(row, sort_keys=True))
                if os.environ.get('GITHUB_ACTIONS'):
                    self.assertEqual(row['profile'], 'signed-bwrap-child-enforce')
                if filtered:
                    self.assertTrue(row['atomicReadback'], json.dumps(row, sort_keys=True))
                    self.assertTrue(row['tmpfileDenied'])
                    self.assertTrue(row['openat2Denied'])
                    self.assertTrue(row['x32Denied'])
            finally:
                if fd is not None:
                    os.close(fd)

    def test_retire_caps_before_final_exec_and_trace_real_cpu_writes(self):
        self.run_owned(False)

    def test_fixed_denial_keeps_zero_caps_and_exclusive_temp_atomic_rename(self):
        self.run_owned(True)


if __name__ == '__main__':
    if len(sys.argv) == 6 and sys.argv[1] == '--owned-child':
        print(json.dumps(child(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] == 'filtered'), sort_keys=True))
    else:
        unittest.main()
