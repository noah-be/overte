#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
import importlib.util
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

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('observer', HERE / 'observer.py')
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
STRACE = Path(os.environ.get('ATOMIC_DIAGNOSTIC_STRACE', str(HERE / 'strace')))
ENV = dict(os.environ)
diagnostic_spec = importlib.util.spec_from_file_location('preflight_diagnostics', HERE / 'preflight_diagnostics.py')
preflight_diagnostics = importlib.util.module_from_spec(diagnostic_spec)
diagnostic_spec.loader.exec_module(preflight_diagnostics)


class ObserverTests(unittest.TestCase):
    def test_fixed_tracer_refusal_category_does_not_attribute_lsm_or_export_text(self):
        self.assertEqual(observer.tracer_failure(b'strace: ptrace(PTRACE_TRACEME, secret): Operation not permitted\n'),
                         'ptrace-operation-not-permitted')
        self.assertEqual(observer.tracer_failure(b'native: ptrace(PTRACE_TRACEME): Operation not permitted\n'),
                         'unobserved-or-unclassified')
        self.assertEqual(observer.tracer_failure(b'strace: ptrace(unknown /private/account): secret\n'),
                         'ptrace-unclassified-error')

    def test_exact_errno_and_result_projection_excludes_every_path_and_fd(self):
        p = observer.Projection()
        raw = (b'[pid 103] linkat(99, "/private/token", -100, "/secret/path", AT_SYMLINK_FOLLOW) = -1 EPERM (Operation not permitted)\n'
               b'104 rename("/private/account", "/private/settings") = 0\n'
               b'fsync(333) = -1 EIO (Input/output error)\n'
               b'renameat2(1, "/name", 2, "/other", 0) = -1 ESECRET (sensitive diagnostic)\n')
        # Real pipe fragmentation, including split result and escaped text.
        for index in range(0, len(raw), 7):
            p.add(raw[index:index + 7])
        result = p.finish()
        self.assertEqual(result['calls']['linkat']['errno'], {'EPERM': 1})
        self.assertEqual(result['calls']['rename']['success'], 1)
        self.assertEqual(result['calls']['fsync']['errno'], {'EIO': 1})
        self.assertEqual(result['calls']['renameat2']['errno'], {'unrecognized-errno': 1})
        exported = json.dumps(result)
        for secret in ('/private', '/secret', 'token', 'account', 'ESECRET', 'sensitive', '103', '333'):
            self.assertNotIn(secret, exported)

    def test_oversized_and_incomplete_lines_are_censored_without_retained_refs(self):
        p = observer.Projection()
        p.add(b'linkat(' + b'x' * (observer.MAX_LINE * 3))
        self.assertEqual(p.pending, b'')
        p.add(b') = 0\nfsync(3) = 0\nrename("x", "y") =')
        r = p.finish()
        self.assertEqual(r['oversizedLines'], 1)
        self.assertEqual(r['incompleteLines'], 1)
        self.assertEqual(r['calls']['fsync']['success'], 1)
        self.assertEqual(r['calls']['linkat']['success'], 0)
        self.assertEqual(p.pending, b'')

    def test_huge_numeric_result_is_unknown_without_exception(self):
        p = observer.Projection()
        p.add(b'rename("x", "y") = ' + b'9' * 4500 + b'\n')
        self.assertEqual(p.finish()['unparsedLines'], 1)

    def test_held_private_log_is_bounded_even_when_parent_directory_renamed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            own = root / 'owned'
            own.mkdir(mode=0o700)
            fd = os.open(own, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                capture = observer.Capture(fd, 'capture')
                renamed = root / 'renamed'
                own.rename(renamed)
                foreign = root / 'foreign'
                foreign.mkdir()
                own.symlink_to(foreign, target_is_directory=True)
                capture.add(b'x' * (observer.MAX_CAPTURE + 10000))
                capture.add(b'y' * 4096)
                self.assertEqual(capture.bytes_retained, observer.MAX_CAPTURE)
                self.assertTrue(capture.truncated)
                capture.close()
                self.assertEqual((renamed / 'capture').stat().st_size, observer.MAX_CAPTURE)
                self.assertEqual(stat.S_IMODE((renamed / 'capture').stat().st_mode), 0o600)
                self.assertEqual(list(foreign.iterdir()), [])
            finally:
                os.close(fd)

    def test_symlink_fifo_existing_log_and_public_directory_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            own = Path(tmp)
            fd = os.open(own, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                (own / 'link').symlink_to(own / 'destination')
                os.mkfifo(own / 'fifo')
                for name in ('link', 'fifo'):
                    with self.assertRaises(OSError):
                        observer.Capture(fd, name)
                for name in ('link', 'fifo'):
                    with self.assertRaises((ValueError, OSError)):
                        observer.checked_regular(own / name, 64)
                own.chmod(0o755)
                with self.assertRaises(ValueError):
                    observer.observe_owned(STRACE, [sys.executable, '-c', 'pass'], ENV, own, own)
            finally:
                os.close(fd)

    def test_genuine_owned_syscalls_and_failure_are_observed_without_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = root / 'capture'
            capture.mkdir(mode=0o700)
            code = ('import os\nfrom pathlib import Path\np=Path("private-source")\n'
                    'f=p.open("wb");f.write(b"credential-must-not-be-exported");f.flush();os.fsync(f.fileno());f.close()\n'
                    'p.rename("private-destination")\n'
                    'try:\n os.rename("missing-private-input","missing-private-output")\n'
                    'except OSError:\n pass\n')
            # A small actual child, not a simulated trace or Qt process.
            result = observer.observe_owned(STRACE, [sys.executable, '-c', code], ENV, root, capture, seconds=5)
            self.assertEqual(result['terminal'], 'native-terminal')
            self.assertEqual(result['exitCode'], 0)
            self.assertGreaterEqual(result['projection']['calls']['fsync']['success'], 1)
            self.assertEqual(result['projection']['calls']['rename']['success'], 1)
            self.assertEqual(result['projection']['calls']['rename']['errno'], {'ENOENT': 1})
            self.assertNotIn('credential', json.dumps(result))
            for p in capture.iterdir():
                self.assertTrue(p.is_file())
                self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
                self.assertLessEqual(p.stat().st_size, observer.MAX_CAPTURE)

    def test_zero_cap_own_child_and_same_namespace_user_ipc_launch_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = root / 'capture'
            capture.mkdir(mode=0o700)
            marker = root / 'preflight.py'
            marker.write_text('import os\nfrom pathlib import Path\n'
                'print("ATOMIC_PREFLIGHT:inner-start",flush=True)\n'
                'f=Path("own-file").open("wb");f.write(b"x");f.flush();os.fsync(f.fileno());f.close()\n'
                'print("ATOMIC_PREFLIGHT:inner-fsync",flush=True)\n')
            entry = root / 'entry.py'
            entry.write_text('import importlib.util,os,json\nfrom pathlib import Path\n'
                'print("ATOMIC_PREFLIGHT:entry-start",flush=True)\n'
                f's=importlib.util.spec_from_file_location("observer",{str(HERE / "observer.py")!r});m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n'
                'print("ATOMIC_PREFLIGHT:observer-imported",flush=True)\n'
                f'd=importlib.util.spec_from_file_location("preflight_diagnostics",{str(HERE / "preflight_diagnostics.py")!r});q=importlib.util.module_from_spec(d);d.loader.exec_module(q)\n'
                'caps=Path("/proc/self/status").read_text().splitlines()\n'
                'print("ATOMIC_PREFLIGHT_CAPS:"+json.dumps(q.capability_states(caps),sort_keys=True),flush=True)\n'
                'assert all(int(line.split(":",1)[1],16)==0 for line in caps if line.startswith(("CapInh:","CapPrm:","CapEff:","CapBnd:","CapAmb:")))\n'
                'print("ATOMIC_PREFLIGHT:zero-cap-asserted",flush=True)\n'
                'print("ATOMIC_PREFLIGHT:tracer-launch-requested",flush=True)\n'
                f'r=m.observe_owned({str(STRACE)!r},["/usr/bin/unshare","--user","--map-current-user","--ipc","--",{sys.executable!r},{str(marker)!r}],dict(os.environ),{str(root)!r},{str(capture)!r},seconds=5)\n'
                'print("ATOMIC_PREFLIGHT:observer-returned",flush=True)\n'
                'raw=b"";capture_status="read"\n'
                'try:\n'
                f' raw=m.checked_regular(Path({str(capture / "native-output.private.log")!r}),m.MAX_CAPTURE,private=True)\n'
                'except (OSError,ValueError):\n capture_status="read-refused"\n'
                'print("ATOMIC_PREFLIGHT_OBSERVER:"+json.dumps(q.inner_observation(r,raw,capture_status),sort_keys=True),flush=True)\n'
                'assert r["exitCode"]==0 and r["projection"]["calls"]["fsync"]["success"]>=1\n'
                'print("ATOMIC_PREFLIGHT:strict-inner-asserted",flush=True)\n')
            result = subprocess.run(['/usr/bin/unshare', '--user', '--map-current-user', '--keep-caps',
                '--ipc', '--', '/usr/bin/setpriv', '--bounding-set=-all', '--inh-caps=-all',
                '--ambient-caps=-all', '--', sys.executable, str(entry)], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=8)
            if result.returncode != 0:
                retained = preflight_diagnostics.retain_failed_preflight(os.environ.get('ATOMIC_DIAGNOSTIC_CACHE'), result.stdout, result.stderr)
                print('ATOMIC_PREFLIGHT_PRIVATE_CAPTURE:' + json.dumps(retained, sort_keys=True, separators=(',', ':')), flush=True)
            self.assertEqual(result.returncode, 0, 'unchanged-own-child-confinement-preflight-refused:' +
                json.dumps(preflight_diagnostics.project_preflight(result.returncode, result.stdout, result.stderr),
                           sort_keys=True, separators=(',', ':')))

    def test_original_deadline_kills_own_child_without_detached_tracee(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = root / 'capture'
            capture.mkdir(mode=0o700)
            code = 'import os,time;from pathlib import Path;Path("owned-pid").write_text(str(os.getpid()));time.sleep(30)'
            before = time.monotonic()
            result = observer.observe_owned(STRACE, [sys.executable, '-c', code], ENV, root, capture, seconds=.4)
            self.assertEqual(result['terminal'], 'original-observer-deadline')
            pid = int((root / 'owned-pid').read_text())
            path = Path(f'/proc/{pid}/stat')
            # Tracer wait is not the kernel's child-death acknowledgement.
            # Require the real child to stop within the same original 2.5s
            # overall bound, rather than treating pending EXITKILL as success.
            while path.exists() and time.monotonic() - before < 2.5:
                if path.read_text().split(') ', 1)[1].split()[0] == 'Z':
                    break
                time.sleep(.01)
            self.assertLess(time.monotonic() - before, 2.5)
            if path.exists():
                # Kernel-delivered EXITKILL can leave a dead zombie for its init
                # reaper. It must never leave a live owned payload.
                state = path.read_text().split(') ', 1)[1].split()[0]
                self.assertEqual(state, 'Z')

    def test_abrupt_wrapper_death_kills_tracer_and_its_own_new_session_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = root / 'capture'
            capture.mkdir(mode=0o700)
            child = root / 'child.py'
            child.write_text('import os,time\nfrom pathlib import Path\nos.setsid()\n'
                             'Path("owned-pid").write_text(str(os.getpid()))\ntime.sleep(20)\n')
            entry = root / 'entry.py'
            entry.write_text('import importlib.util,os\n'
                f's=importlib.util.spec_from_file_location("observer",{str(HERE / "observer.py")!r});m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n'
                f'm.observe_owned({str(STRACE)!r},[{sys.executable!r},{str(child)!r}],dict(os.environ),{str(root)!r},{str(capture)!r},seconds=5)\n')
            wrapper = subprocess.Popen([sys.executable, str(entry)], stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            pid = identity = None
            try:
                deadline = time.monotonic() + 2
                while not (root / 'owned-pid').exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue((root / 'owned-pid').exists())
                pid = int((root / 'owned-pid').read_text())
                info = Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()
                identity = info[19]
                wrapper.kill()
                wrapper.wait(timeout=2)
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    path = Path(f'/proc/{pid}/stat')
                    if not path.exists() or path.read_text().split(') ', 1)[1].split()[0] == 'Z':
                        break
                    time.sleep(.01)
                if path.exists():
                    self.assertEqual(path.read_text().split(') ', 1)[1].split()[0], 'Z')
            finally:
                if wrapper.poll() is None:
                    wrapper.kill()
                    wrapper.wait(timeout=2)
                # Safety cleanup cannot convert a failing assertion to success;
                # kill only the still-matching exact owned child if necessary.
                if pid and identity:
                    path = Path(f'/proc/{pid}/stat')
                    if path.exists():
                        info = path.read_text().split(') ', 1)[1].split()
                        if info[19] == identity and info[0] != 'Z':
                            os.kill(pid, signal.SIGKILL)

    def test_cli_requires_exact_owned_config_and_fixed_native_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            native = root / 'domain-server'
            native.write_text('owned-test-only')
            native.chmod(0o700)
            settings = root / 'settings.json'
            settings.write_text('{}')
            settings.chmod(0o600)
            settings_hash = hashlib.sha256(settings.read_bytes()).hexdigest()
            d = {'version': 1, 'strace': str(STRACE),
                 'straceSHA256': hashlib.sha256(STRACE.read_bytes()).hexdigest(),
                 'native': str(native), 'nativeSHA256': hashlib.sha256(native.read_bytes()).hexdigest(),
                 'unshare': '/usr/bin/unshare',
                 'unshareSHA256': hashlib.sha256(Path('/usr/bin/unshare').read_bytes()).hexdigest(),
                 'settings': str(settings), 'environment': {'HOME': os.environ['HOME']},
                 'cwd': str(root), 'output': str(root)}
            result = observer.validated_launch(d)
            self.assertEqual(result, ['/usr/bin/unshare', '--user', '--map-current-user', '--ipc',
                '--', str(native), '--user-config', str(settings), '--logOptions', 'nocolor,nojournald'])
            self.assertEqual(hashlib.sha256(settings.read_bytes()).hexdigest(), settings_hash)
            for field, value in [('attachPID', 1), ('nativeArguments', ['--user-config', '/foreign'])]:
                bad = {**d, field: value}
                with self.assertRaises(ValueError):
                    observer.validated_launch(bad)
            for env in [{'HOME': '/different'}, {'HOME': os.environ['HOME'], 'LD_PRELOAD': '/foreign'}]:
                with self.assertRaises(ValueError):
                    observer.validated_launch({**d, 'environment': env})
            with self.assertRaises(ValueError):
                observer.validated_launch({**d, 'nativeSHA256': '0' * 64})

    def test_actual_launch_wrapper_separates_host_tracer_from_native_library_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            native = root / 'domain-server'
            # A tiny owned executable, not a Qt/native domain or a service.
            native.write_text(f'#!{sys.executable}\nimport os\nfrom pathlib import Path\n'
                'assert os.environ["LD_LIBRARY_PATH"]=="/owned-native-library-probe"\n'
                'f=Path("library-env-proved").open("wb");f.write(b"owned");f.flush();os.fsync(f.fileno());f.close()\n')
            native.chmod(0o700)
            settings = root / 'settings.json'
            settings.write_text('{}')
            settings.chmod(0o600)
            capture = root / 'capture'
            capture.mkdir(mode=0o700)
            d = {'version': 1, 'strace': str(STRACE),
                 'straceSHA256': hashlib.sha256(STRACE.read_bytes()).hexdigest(),
                 'native': str(native), 'nativeSHA256': hashlib.sha256(native.read_bytes()).hexdigest(),
                 'unshare': '/usr/bin/unshare',
                 'unshareSHA256': hashlib.sha256(Path('/usr/bin/unshare').read_bytes()).hexdigest(),
                 'settings': str(settings), 'environment': {'HOME': os.environ['HOME'],
                     'LD_LIBRARY_PATH': '/owned-native-library-probe'},
                 'cwd': str(root), 'output': str(capture)}
            config = capture / 'launch.private.json'
            config.write_text(json.dumps(d))
            config.chmod(0o600)
            result = subprocess.run([sys.executable, str(HERE / 'observer.py'), '--configuration', str(config)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)['terminal'], 'native-terminal')
            self.assertEqual((root / 'library-env-proved').read_bytes(), b'owned')
            report = json.loads((capture / 'summary.json').read_text())
            self.assertGreaterEqual(report['projection']['calls']['fsync']['success'], 1)
            self.assertNotIn('/owned-native', result.stdout.decode())


if __name__ == '__main__':
    unittest.main()
