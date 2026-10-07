"""Own Python subreaper topology only; no bwrap/native/browser/service launch."""
import ast
import ctypes
import errno
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parent / 'manage.py'
PROOF_OUTPUT = None


def identity(pid):
    directory = Path('/proc') / str(pid)
    try:
        data = (directory / 'stat').read_bytes()
        if len(data) > 4096:
            raise RuntimeError('own-stat-bound')
        fields = data.rsplit(b') ', 1)[1].split()
        return dict(pid=pid, birth=fields[19].decode('ascii'), parent=int(fields[1]),
                    group=int(fields[2]), session=int(fields[3]), uid=directory.stat().st_uid, state=fields[0].decode())
    except (FileNotFoundError, ProcessLookupError):
        return None


def write_role(root, role, row):
    fd = os.open(root / (role + '.json'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        raw = json.dumps(row).encode()
        if os.write(fd, raw) != len(raw):
            raise RuntimeError('own-role-write')
    finally:
        os.close(fd)
    # Publish readiness only after the fixed record has been fully closed.
    ready = os.open(root / (role + '.ready'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(ready)


def parent_guard(parent):
    library = ctypes.CDLL(None, use_errno=True)
    if library.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent:
        os._exit(125)


def role_main(role, root):
    expiry = time.monotonic() + 10.0
    if role == 'child':
        # Deliberately preserve this controlled Python child across its
        # intermediate parent's death, like the historical CPU topology.
        library = ctypes.CDLL(None, use_errno=True)
        if library.prctl(1, 0, 0, 0, 0) != 0:
            raise RuntimeError('own-child-clear-pdeath')
        write_role(root, role, identity(os.getpid()))
    else:
        if role == 'leader':
            ready = time.monotonic() + 5.0
            while not (root / 'go').exists() and time.monotonic() < ready:
                time.sleep(0.01)
            if not (root / 'go').exists():
                return
        next_role = 'intermediate' if role == 'leader' else 'child'
        expected = os.getpid()
        child = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()),
                                  '--cpu-role', next_role, str(root)],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'},
                                 preexec_fn=lambda: parent_guard(expected))
        write_role(root, role, identity(os.getpid()))
        if role == 'leader':
            child.wait(timeout=9.0)
    while time.monotonic() < expiry:
        time.sleep(0.02)


class ManagedAncestryOwnedCPU(unittest.TestCase):
    def test_real_pre_pinned_child_reparents_and_original_stop_proves_retirement(self):
        self.assertEqual(sys.platform, 'linux', 'required Linux guard is not skipped')
        self.assertTrue(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'))
        library = ctypes.CDLL(None, use_errno=True)
        prior = ctypes.c_int()
        self.assertEqual(library.prctl(37, ctypes.byref(prior), 0, 0, 0), 0)
        temporary = tempfile.TemporaryDirectory(prefix='own-ancestry-topology-')
        root = Path(temporary.name)
        root.chmod(0o700)
        process = owner = None
        held = []
        known = {}
        triggered = False
        restored = False
        total_deadline = time.monotonic() + 14.0
        tree = ast.parse(SOURCE.read_text())
        definition = next(node for node in tree.body
                          if isinstance(node, ast.ClassDef) and node.name == '_OwnedStop')
        scope = dict(Path=Path, os=os, signal=signal, time=time)
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(SOURCE), 'exec'), scope)

        def check(row):
            fresh = identity(row['pid'])
            if fresh is not None:
                self.assertEqual(tuple(fresh[key] for key in ('birth', 'uid', 'group', 'session')),
                                 tuple(row[key] for key in ('birth', 'uid', 'group', 'session')))
            return fresh

        def admit(row):
            self.assertEqual(row['uid'], os.getuid())
            self.assertEqual(row['group'], process.pid)
            self.assertEqual(row['session'], process.pid)
            check(row)
            owner.admit(row)
            known[row['pid']] = dict(row)
            held.append(owner.descriptors[row['pid']])

        def read_role(role):
            path = root / (role + '.json')
            marker = root / (role + '.ready')
            if not marker.exists():
                return None
            ready = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                marker_info = os.fstat(ready)
                self.assertTrue(stat.S_ISREG(marker_info.st_mode))
                self.assertEqual((marker_info.st_uid, marker_info.st_nlink, stat.S_IMODE(marker_info.st_mode), marker_info.st_size),
                                 (os.getuid(), 1, 0o600, 0))
            finally:
                os.close(ready)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                self.assertTrue(stat.S_ISREG(info.st_mode))
                self.assertEqual((info.st_uid, info.st_nlink, stat.S_IMODE(info.st_mode)),
                                 (os.getuid(), 1, 0o600))
                raw = os.read(fd, 2049)
                self.assertLessEqual(len(raw), 2048)
                row = json.loads(raw)
                self.assertEqual(set(row), {'pid', 'birth', 'parent', 'group', 'session', 'uid', 'state'})
                self.assertTrue(type(row['pid']) is int and row['pid'] > 1)
                fresh = check(row)
                self.assertIsNotNone(fresh)
                self.assertEqual({key: value for key, value in fresh.items() if key != 'state'},
                                 {key: value for key, value in row.items() if key != 'state'})
                self.assertNotEqual(fresh['state'], 'Z')
                return fresh
            finally:
                os.close(fd)

        def discover_for_cleanup():
            # Only bounded child lists of authenticated own processes, and the
            # controller's own adopted direct children. No foreign /proc scan.
            pending = list(known.values())
            myself = identity(os.getpid())
            pending.append(myself)
            seen = set()
            while pending:
                parent = pending.pop()
                if parent['pid'] in seen:
                    continue
                seen.add(parent['pid'])
                self.assertLessEqual(len(seen), 8)
                if identity(parent['pid']) is None:
                    continue
                if parent['pid'] != os.getpid():
                    check(parent)
                path = Path('/proc') / str(parent['pid']) / 'task' / str(parent['pid']) / 'children'
                try:
                    data = path.read_bytes()
                except (FileNotFoundError, ProcessLookupError):
                    continue
                self.assertLessEqual(len(data), 1024)
                children = data.split()
                self.assertLessEqual(len(children), 8)
                for raw in children:
                    self.assertTrue(raw.isdigit())
                    row = identity(int(raw))
                    if row is None:
                        continue
                    self.assertEqual(row['parent'], parent['pid'])
                    if row['group'] != process.pid or row['session'] != process.pid:
                        self.assertEqual(parent['pid'], os.getpid())
                        continue
                    if row['pid'] not in known:
                        admit(row)
                    pending.append(row)

        def cleanup():
            if owner is None:
                if process is not None:
                    # The leader cannot spawn before controller-owned go.
                    process.wait(timeout=5.5)
                    self.assertIsNone(identity(process.pid))
                return
            discover_for_cleanup()
            for pid, row in list(known.items()):
                if check(row) is None:
                    continue
                fd = owner.descriptors[pid]
                try:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            deadline = min(total_deadline, time.monotonic() + 2.5)
            while time.monotonic() < deadline:
                for pid, row in list(known.items()):
                    fresh = check(row)
                    if fresh is not None and fresh['parent'] == os.getpid():
                        try:
                            os.waitid(os.P_PIDFD, owner.descriptors[pid], os.WEXITED | os.WNOHANG)
                        except ChildProcessError:
                            pass
                if all(identity(pid) is None for pid in known):
                    break
                time.sleep(0.01)
            self.assertTrue(all(identity(pid) is None for pid in known), 'owned rows not reaped')
            self.assertTrue(owner.group_absent(process.pid), 'owned group not absent')
            process.wait(timeout=0.5)

        try:
            self.assertEqual(library.prctl(36, 1, 0, 0, 0), 0)
            active = ctypes.c_int()
            self.assertEqual(library.prctl(37, ctypes.byref(active), 0, 0, 0), 0)
            self.assertEqual(active.value, 1)
            process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()),
                                        '--cpu-role', 'leader', str(root)],
                                       start_new_session=True, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'})
            leader = identity(process.pid)
            self.assertIsNotNone(leader)
            self.assertEqual(leader['parent'], os.getpid())
            owner = scope['_OwnedStop']({'pid': leader['pid'], 'startTicks': leader['birth']})
            admit(leader)
            (root / 'go').touch(mode=0o600)
            deadline = time.monotonic() + 5.0
            intermediate = child = None
            while time.monotonic() < deadline:
                if intermediate is None:
                    intermediate = read_role('intermediate')
                    if intermediate is not None:
                        self.assertEqual(intermediate['parent'], leader['pid'])
                        admit(intermediate)
                if intermediate is not None:
                    child = read_role('child')
                    if child is not None:
                        self.assertEqual(child['parent'], intermediate['pid'])
                        admit(child)
                        break
                time.sleep(0.01)
            self.assertIsNotNone(child, 'owned readiness exceeded fixed five seconds')
            self.assertEqual(len(known), 3)
            original_children = owner.children

            def captured_children(row):
                nonlocal triggered
                captured = original_children(row)
                if row['pid'] == intermediate['pid'] and not triggered:
                    self.assertIn(child['pid'], captured)
                    for observed in known.values():
                        check(observed)
                    self.assertEqual(len(owner.descriptors), 3)
                    signal.pidfd_send_signal(owner.descriptors[intermediate['pid']], signal.SIGKILL)
                    deadline = min(total_deadline, time.monotonic() + 1.0)
                    while time.monotonic() < deadline:
                        fresh = check(child)
                        if fresh is not None and fresh['parent'] == os.getpid():
                            self.assertNotEqual(fresh['state'], 'Z')
                            triggered = True
                            return captured
                        time.sleep(0.005)
                    self.fail('owned child did not reparent within fixed bound')
                return captured

            owner.children = captured_children
            started = time.monotonic()
            owner.retire()
            self.assertTrue(triggered)
            self.assertLess(time.monotonic() - started, 3.1)
            self.assertTrue(all(identity(pid) is None for pid in known))
            self.assertTrue(owner.group_absent(process.pid))
        finally:
            try:
                cleanup()
            finally:
                try:
                    if owner is not None:
                        owner.close()
                        for fd in held:
                            with self.assertRaises(OSError) as error:
                                os.fstat(fd)
                            self.assertEqual(error.exception.errno, errno.EBADF)
                finally:
                    self.assertEqual(library.prctl(36, prior.value, 0, 0, 0), 0)
                    readback = ctypes.c_int()
                    self.assertEqual(library.prctl(37, ctypes.byref(readback), 0, 0, 0), 0)
                    self.assertEqual(readback.value, prior.value)
                    restored = True
                    temporary.cleanup()
            self.assertTrue(restored)
            if PROOF_OUTPUT is not None:
                proof = dict(knownProcesses=len(known), kernelReparentObserved=triggered,
                             ownedRowsAbsent=True, ownedGroupAbsent=True, pidfdsClosed=True,
                             subreaperRestored=True, explicitSubreaperTopology=True, stopBudgetSeconds=3)
                fd = os.open(PROOF_OUTPUT, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    raw = (json.dumps(proof) + '\n').encode()
                    self.assertEqual(os.write(fd, raw), len(raw))
                finally:
                    os.close(fd)


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--cpu-role' and sys.argv[2] in ('leader', 'intermediate', 'child'):
        role_main(sys.argv[2], Path(sys.argv[3]))
    else:
        unittest.main(verbosity=2)
