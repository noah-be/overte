# SPDX-License-Identifier: Apache-2.0
"""CPU records, namespace files and owned supervision; never run DomainServer."""
import ctypes
import hashlib
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
from unittest.mock import patch
import native_launch as launch

SOURCE = Path(__file__).resolve().parent


class ManagedLaunchRecords(unittest.TestCase):
    def fixture(self, root):
        lab = root / 'lab';lab.mkdir(mode=0o700)
        native = lab / 'server/opt/overte/domain-server';native.parent.mkdir(parents=True)
        native.write_bytes(b'owned-native-CPU-fixture');native.chmod(0o700)
        settings = lab / 'config/domain.json';settings.parent.mkdir();settings.write_text('{}')
        env = {'HOME': os.environ.get('HOME'), 'OVERTE_LAB_ROOT': str(lab),
               'LD_LIBRARY_PATH': f'{lab}/server/opt/overte/lib:{lab}/appimage/squashfs-root/usr/lib',
               'HIFI_DOMAIN_SERVER_HTTP_PORT': '45100', 'HIFI_DOMAIN_SERVER_HTTPS_PORT': '45101',
               'HIFI_DOMAIN_SERVER_PORT': '45102', 'HIFI_DOMAIN_SERVER_DTLS_PORT': '45103',
               'PRIVATE_CPU_MARKER': 'cpu-only-private-environment'}
        return lab, native, env

    def test_native_environment_is_sealed_and_never_enters_host_argv_environment_or_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);lab, native, env = self.fixture(root)
            with patch.object(launch, 'NATIVE_SHA256', hashlib.sha256(native.read_bytes()).hexdigest()):
                with launch.managed_command(lab, root, env) as (argv, host, fd, policy):
                    self.assertNotIn('cpu-only-private-environment', json.dumps(argv))
                    self.assertNotIn('PRIVATE_CPU_MARKER', host)
                    self.assertNotIn('LD_LIBRARY_PATH', host)
                    doc = launch.checked_managed_record(os.pread(fd, 65537, 0))
                    self.assertEqual(doc['environment'], env)
                    self.assertEqual(doc['policy'], policy)
                    with self.assertRaises(OSError):os.write(fd, b'caller-replacement')
                with self.assertRaises(OSError):os.fstat(fd)
            self.assertFalse(any(path.name.endswith('.private.json') for path in lab.rglob('*')))

    def test_changed_native_loader_override_home_and_aggregate_overflow_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);lab, native, env = self.fixture(root)
            with self.assertRaisesRegex(ValueError, '^managed-native-executable-refused$'):
                launch.managed_document(lab, root, env)
            with patch.object(launch, 'NATIVE_SHA256', hashlib.sha256(native.read_bytes()).hexdigest()):
                for changed in ({**env, 'LD_PRELOAD': '/private'}, {**env, 'HOME': '/changed'},
                                {**env, 'LD_LIBRARY_PATH': '/caller-native'}):
                    with self.assertRaisesRegex(ValueError, '^managed-launch-environment-refused$'):
                        launch.managed_document(lab, root, changed)
                with self.assertRaisesRegex(ValueError, '^managed-launch-record-size-refused$'):
                    with launch.managed_command(lab, root, {**env, **{f'LARGE_{i}': 'x'*8192 for i in range(9)}}):pass

    def test_duplicate_record_unknown_field_and_unsealed_descriptor_refuse(self):
        for raw in (b'{"version":1,"version":1}', b'{"privatePath":"/private"}', b' ' * 65537):
            with self.assertRaises(ValueError):launch.checked_managed_record(raw)
        fd = os.memfd_create('owned-unsealed-CPU-record', os.MFD_ALLOW_SEALING)
        try:
            with self.assertRaisesRegex(ValueError, '^managed-launch-record-unsealed$'):launch.exec_managed(fd)
        finally:os.close(fd)

    def test_kernel_policy_mode_never_admits_an_unknown_profile(self):
        good = {'zeroCapabilities': True, 'noNewPrivileges': True, 'userIsolated': True,
                'ipcIsolated': True, 'identityStable': True, 'seccompFiltered': True,
                'allThreadsConfined': True, 'profile': 'preserved-enforcing-selinux-context'}
        launch.require_managed_confinement(good, {'kind': 'selinux', 'context': 'CPU-only'})
        for row in ({**good, 'profile': 'unqualified'}, {**good, 'allThreadsConfined': False},
                    {**good, 'zeroCapabilities': 1}):
            with self.assertRaises(ValueError):launch.require_managed_confinement(row, {'kind': 'selinux', 'context': 'CPU-only'})
        with self.assertRaises(ValueError):launch.require_managed_confinement(good, {'kind': 'apparmor', 'context': ''})
        with self.assertRaises(ValueError):launch.require_managed_confinement(good, {'kind': 'caller', 'context': 'CPU-only'})


class OwnedSupervisor(unittest.TestCase):
    def test_controller_exit_preserves_service_and_registered_group_death_stops_every_owned_child(self):
        library = ctypes.CDLL(None, use_errno=True)
        prior = ctypes.c_int()
        self.assertEqual(library.prctl(37, ctypes.byref(prior), 0, 0, 0), 0)
        self.assertEqual(library.prctl(36, 1, 0, 0, 0), 0)
        supervisor = native = None
        identity = None
        try:
            with tempfile.TemporaryDirectory(prefix='owned-CPU-domain-supervision-') as directory:
                root = Path(directory)
                marker = root / 'marker.py'
                marker.write_text('import json,os,time,stat\nfrom pathlib import Path\n'
                    'status=dict(x.split(":",1) for x in Path("/proc/self/status").read_text().splitlines() if ":" in x)\n'
                    'assert all(int(status[x],16)==0 for x in ("CapInh","CapPrm","CapEff","CapBnd","CapAmb"))\n'
                    'assert status["NoNewPrivs"].strip()=="1" and status["Seccomp"].strip()=="2"\n'
                    'record=Path("/run/overte-owned-domain/cpu.json")\n'
                    'assert record.read_bytes()==b"private-CPU-scope-only"\n'
                    'assert stat.S_IMODE(record.stat().st_mode)==0o600 and record.stat().st_uid==os.getuid()\n'
                    'Path("payload.pid").write_text(str(os.getpid()))\n'
                    'print("OWNED_CPU_READY",flush=True)\ntime.sleep(30)\n')
                entry = root / 'supervisor.py'
                entry.write_text('import os,sys\nfrom pathlib import Path\n'
                    f'sys.path.insert(0,{str(SOURCE)!r})\nimport native_launch as m\n'
                    'root=Path(sys.argv[1]);record=m.sealed_record(b"private-CPU-scope-only");policy=m.sealed_filter()\n'
                    'command=m.base_command((str(root),),str(root))+["--tmpfs","/run","--perms","0700","--dir","/run/overte-owned-domain","--perms","0600","--ro-bind-data",str(record),"/run/overte-owned-domain/cpu.json","--seccomp",str(policy),"--",sys.executable,str(root/"marker.py")]\n'
                    'try:\n code=m.supervise(command,(record,policy))\n'
                    'finally:\n os.close(record);os.close(policy)\n'
                    'raise SystemExit(code)\n')
                controller = root / 'controller.py'
                controller.write_text('import json,subprocess,sys\nfrom pathlib import Path\n'
                    f'sys.path.insert(0,{str(SOURCE)!r})\nimport native_launch as m\n'
                    'root=Path(sys.argv[1])\nwith (root/"cpu.log").open("wb") as log:\n'
                    ' p=subprocess.Popen([sys.executable,str(root/"supervisor.py"),str(root)],env=m.host_environment(),stdout=log,stderr=log,start_new_session=True)\n'
                    'ticks=Path(f"/proc/{p.pid}/stat").read_text().split(") ",1)[1].split()[19]\n'
                    '(root/"owner.json").write_text(json.dumps({"pid":p.pid,"ticks":ticks}))\n')
                started = time.monotonic()
                result = subprocess.run([sys.executable, str(controller), directory], env=launch.host_environment(),
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
                self.assertEqual(result.returncode, 0, 'owned-CPU-controller-refused')
                identity = json.loads((root / 'owner.json').read_text());supervisor = identity['pid']
                deadline = min(started + 8, time.monotonic() + 2)
                while time.monotonic() < deadline:
                    try:
                        raw = (root / 'payload.pid').read_text()
                        if raw.isdecimal() and 'OWNED_CPU_READY' in (root / 'cpu.log').read_text():
                            native = int(raw);break
                    except FileNotFoundError:pass
                    time.sleep(.01)
                self.assertIsNotNone(native, 'owned-CPU-payload-not-ready')
                # The initial manager has exited normally, but its registered
                # supervisor and the actual payload must still be alive.
                for pid in (supervisor, native):
                    fields = Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()
                    self.assertNotEqual(fields[0], 'Z', 'owned-CPU-service-ended-with-controller')
                self.assertEqual(Path(f'/proc/{supervisor}/stat').read_text().split(') ', 1)[1].split()[19], identity['ticks'])
                self.assertEqual(os.getpgid(supervisor), supervisor)
                os.killpg(supervisor, signal.SIGTERM)
                deadline = time.monotonic() + 2.5
                pending = {supervisor, native}
                while pending and time.monotonic() < deadline:
                    for pid in list(pending):
                        try:
                            fields = Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()
                        except (FileNotFoundError, ProcessLookupError):pending.remove(pid);continue
                        if fields[0] == 'Z':pending.remove(pid)
                    time.sleep(.01)
                self.assertFalse(pending, 'owned-CPU-descendant-survived-group-shutdown')
        finally:
            if supervisor is not None and identity is not None:
                try:
                    fields = Path(f'/proc/{supervisor}/stat').read_text().split(') ', 1)[1].split()
                    if fields[19] == identity['ticks'] and fields[0] != 'Z' and os.getpgid(supervisor) == supervisor:
                        os.killpg(supervisor, signal.SIGKILL)
                except (FileNotFoundError, ProcessLookupError):pass
            for pid in (supervisor, native):
                if pid is not None:
                    try:os.waitpid(pid, os.WNOHANG)
                    except ChildProcessError:pass
            library.prctl(36, prior.value, 0, 0, 0)


if __name__ == '__main__':unittest.main()
