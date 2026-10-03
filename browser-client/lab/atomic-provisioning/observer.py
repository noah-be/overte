#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Private owned-launch observation. Never attach to an existing process."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

SYSCALLS = ('linkat', 'rename', 'renameat', 'renameat2', 'fsync', 'fdatasync')
ERRNOS = frozenset(('EPERM', 'EACCES', 'ENOENT', 'EEXIST', 'ENOTDIR', 'EISDIR',
                    'EXDEV', 'EROFS', 'ENOSPC', 'EDQUOT', 'EIO', 'EINVAL', 'EBADF',
                    'ENOMEM', 'EMFILE', 'ENFILE', 'EINTR', 'ENOSYS', 'EOPNOTSUPP'))
MAX_CAPTURE = 256 * 1024
MAX_LINE = 16384
MAX_CONFIG = 65536
# The hosted original launch has 129 inherited entries. Keep its full environment
# within a finite entry bound and the unchanged serialized 64 KiB record bound.
MAX_ENV_ENTRIES = 256
MAX_SECONDS = 30
_RESULT = re.compile(r'^(?:\[pid\s+\d+\]\s+|\d+\s+)?(?:\d{9,12}\.\d{1,9}\s+)?(?P<call>linkat|rename|renameat|renameat2|fsync|fdatasync)\(.*\)\s+=\s+(?P<value>-?\d+)(?:\s+(?P<errno>[A-Z][A-Z0-9]+)\s+\([^\r\n]*\))?\s*$')


def tracer_failure(data):
    # This is observational only, not an inference about a particular LSM.
    for line in data.splitlines():
        if line.startswith(b'strace: ') and b'ptrace(' in line:
            if line.endswith(b'Operation not permitted'):
                return 'ptrace-operation-not-permitted'
            if line.endswith(b'Permission denied'):
                return 'ptrace-permission-denied'
            return 'ptrace-unclassified-error'
    return 'unobserved-or-unclassified'


def checked_regular(path, maximum, *, executable=False, private=False):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('input-path-not-canonical')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() and executable is False:
            raise ValueError('input-not-owned-regular')
        if private and stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('input-not-private')
        if info.st_size > maximum or executable and not info.st_mode & 0o111:
            raise ValueError('input-size-or-executable-invalid')
        data = bytearray()
        while len(data) <= maximum:
            part = os.read(fd, min(65536, maximum + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        if len(data) > maximum:
            raise ValueError('input-size-invalid')
        return bytes(data)
    finally:
        os.close(fd)


class Capture:
    """Held regular FD, capped raw bytes; continue draining after censoring."""
    def __init__(self, directory_fd, name):
        self.fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                          0o600, dir_fd=directory_fd)
        self.bytes_seen = self.bytes_retained = 0
        self.truncated = False
    def add(self, data):
        self.bytes_seen = min(2**53 - 1, self.bytes_seen + len(data))
        remaining = MAX_CAPTURE - self.bytes_retained
        retained = memoryview(data)[:remaining]
        while retained:
            count = os.write(self.fd, retained)
            retained = retained[count:]
            self.bytes_retained += count
        self.truncated |= len(data) > remaining
    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class Projection:
    def __init__(self):
        self.pending = b''
        self.dropping_line = False
        self.calls = {name: {'success': 0, 'failure': 0, 'unclassifiedResult': 0,
                             'errno': {}} for name in SYSCALLS}
        self.unparsed_lines = self.oversized_lines = self.incomplete_lines = 0
    def add(self, data):
        for piece in data.splitlines(keepends=True):
            complete = piece.endswith(b'\n')
            if self.dropping_line:
                if complete:
                    self.dropping_line = False
                continue
            if len(self.pending) + len(piece) > MAX_LINE:
                self.pending = b''
                self.oversized_lines += 1
                self.dropping_line = not complete
                continue
            self.pending += piece
            if complete:
                self.line(self.pending.rstrip(b'\r\n'))
                self.pending = b''
    def line(self, raw):
        match = _RESULT.fullmatch(raw.decode('ascii', errors='replace'))
        if not match:
            if raw:
                self.unparsed_lines += 1
            return
        row = self.calls[match['call']]
        if len(match['value']) > 20:
            self.unparsed_lines += 1
            return
        result = int(match['value'])
        if result == 0 and match['errno'] is None:
            row['success'] += 1
        elif result == -1 and match['errno']:
            row['failure'] += 1
            label = match['errno'] if match['errno'] in ERRNOS else 'unrecognized-errno'
            row['errno'][label] = row['errno'].get(label, 0) + 1
        else:
            row['unclassifiedResult'] += 1
    def finish(self):
        if self.pending or self.dropping_line:
            self.incomplete_lines += 1
        self.pending = b''
        self.dropping_line = False
        return {'calls': self.calls, 'unparsedLines': self.unparsed_lines,
                'oversizedLines': self.oversized_lines, 'incompleteLines': self.incomplete_lines,
                'scope': 'owned-process-atomic-syscalls-not-settings-causality'}


def child_death_guard(expected):
    # A killed wrapper must not leave a tracer. PTRACE_O_EXITKILL below then
    # kills the tracer's own tracees, without signalling any unrelated process.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != expected:
        os._exit(125)


def observe_owned(strace, command, environment, cwd, directory, *, seconds=MAX_SECONDS):
    """Internal CPU tests may supply their own child; public CLI validates domain."""
    if type(seconds) not in (int, float) or not 0 < seconds <= MAX_SECONDS:
        raise ValueError('observer-deadline-invalid')
    directory = Path(directory)
    if not directory.is_absolute() or directory.resolve() != directory:
        raise ValueError('output-path-not-canonical')
    dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(dfd)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(dfd)
        raise ValueError('output-directory-not-private-owned')
    trace = native = tracer = None
    read_fd = write_fd = None
    process = None
    selector = selectors.DefaultSelector()
    projection = Projection()
    tracer_prefix = bytearray()
    stopped = False
    prior = {}
    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True
    try:
        trace = Capture(dfd, 'atomic-syscalls.private.log')
        native = Capture(dfd, 'native-output.private.log')
        tracer = Capture(dfd, 'tracer-output.private.log')
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
        argv = [str(strace), '-f', '-qq', '-ttt', '-I', '1', '--kill-on-exit',
                '-e', 'trace=' + ','.join(SYSCALLS), '-e', 'signal=none',
                '-o', f'/proc/self/fd/{write_fd}', '--', *command]
        for name in (signal.SIGTERM, signal.SIGINT):
            prior[name] = signal.signal(name, stop)
        deadline = time.monotonic() + seconds
        parent_pid = os.getpid()
        process = subprocess.Popen(argv, env=environment, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   pass_fds=(write_fd,), start_new_session=True,
                                   preexec_fn=lambda: child_death_guard(parent_pid))
        os.close(write_fd)
        write_fd = None
        for fd, kind in [(read_fd, 'trace'), (process.stdout.fileno(), 'native'),
                         (process.stderr.fileno(), 'tracer')]:
            os.set_blocking(fd, False)
            selector.register(fd, selectors.EVENT_READ, kind)
        reason = 'native-terminal'
        while selector.get_map() or process.poll() is None:
            if stopped or time.monotonic() >= deadline:
                reason = 'cancelled' if stopped else 'original-observer-deadline'
                break
            for key, _events in selector.select(min(.05, max(0, deadline - time.monotonic()))):
                data = os.read(key.fd, 8192)
                if not data:
                    selector.unregister(key.fd)
                    continue
                if key.data == 'trace':
                    trace.add(data)
                    projection.add(data)
                elif key.data == 'native':
                    native.add(data)
                else:
                    tracer.add(data)
                    native.add(data)
                    tracer_prefix.extend(data[:max(0, 8192 - len(tracer_prefix))])
        # No detach or foreign attach. The exact owned process group is killed
        # if still present; PID remains owned by Popen until after this signal.
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2)
        # Drain already-buffered bytes after terminal state, with fixed 200ms
        # cleanup bound. No live tracee is kept to extend an observation.
        end = time.monotonic() + .2
        while selector.get_map() and time.monotonic() < end:
            for key, _events in selector.select(.01):
                data = os.read(key.fd, 8192)
                if not data:
                    selector.unregister(key.fd)
                    continue
                capture = trace if key.data == 'trace' else native if key.data == 'native' else tracer
                capture.add(data)
                if key.data == 'tracer':
                    native.add(data)
                if key.data == 'trace':
                    projection.add(data)
                elif key.data == 'tracer':
                    tracer_prefix.extend(data[:max(0, 8192 - len(tracer_prefix))])
        report = {'schemaVersion': 1, 'terminal': reason, 'exitCode': process.returncode,
                  'trace': {'retainedBytes': trace.bytes_retained, 'observedBytes': trace.bytes_seen,
                            'truncated': trace.truncated},
                  'nativeOutputTruncated': native.truncated,
                  'tracerOutputTruncated': tracer.truncated, 'projection': projection.finish(),
                  'tracerFailure': tracer_failure(tracer_prefix),
                  'limits': ['ptrace-may-affect-timing', 'no-settings-target-causality-from-sync-fd',
                             'unknown-or-split-trace-lines-explicit', 'no-shipping-or-CI-pass-claim']}
        result_fd = os.open('summary.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o600, dir_fd=dfd)
        with os.fdopen(result_fd, 'w') as output:
            json.dump(report, output, indent=2)
            output.write('\n')
        return report
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
        for name, old in prior.items():
            signal.signal(name, old)
        selector.close()
        if read_fd is not None:
            os.close(read_fd)
        if write_fd is not None:
            os.close(write_fd)
        if process is not None:
            process.stdout.close()
            process.stderr.close()
        for capture in (trace, native, tracer):
            if capture is not None:
                capture.close()
        os.close(dfd)


def validated_launch(document):
    if type(document) is not dict or set(document) != {'version', 'strace', 'straceSHA256',
            'native', 'nativeSHA256', 'settings', 'unshare', 'unshareSHA256',
            'environment', 'cwd', 'output'} or type(document['version']) is not int or document['version'] != 1:
        raise ValueError('launch-schema-invalid')
    for name in ('strace', 'native', 'settings', 'unshare', 'cwd', 'output'):
        value = document[name]
        if type(value) is not str or not value or len(value) > 4096 or any(c in value for c in '\x00\r\n'):
            raise ValueError('launch-path-invalid')
    for name in ('strace', 'native', 'unshare'):
        data = checked_regular(document[name], 64 * 1024 * 1024, executable=True)
        if hashlib.sha256(data).hexdigest() != document[name + 'SHA256']:
            raise ValueError('launch-executable-hash-mismatch')
    if Path(document['native']).name != 'domain-server' or Path(document['unshare']).name != 'unshare':
        raise ValueError('launch-executable-kind-invalid')
    checked_regular(document['settings'], 1024 * 1024)
    env = document['environment']
    if type(env) is not dict or len(env) > MAX_ENV_ENTRIES or any(type(k) is not str or type(v) is not str
            or not k or len(k) > 128 or len(v) > 8192 or '\x00' in k + v for k, v in env.items()):
        raise ValueError('launch-environment-invalid')
    if any(name in env for name in ('LD_PRELOAD', 'LD_AUDIT', 'PYTHONPATH', 'PYTHONHOME')):
        raise ValueError('launch-environment-code-override')
    if env.get('HOME') != os.environ.get('HOME'):
        raise ValueError('launch-inherited-home-changed')
    # prepare() calls this directly before writing this exact representation;
    # enforce the reader's byte bound here too, including indentation/newline.
    if len((json.dumps(document, indent=2) + '\n').encode()) > MAX_CONFIG:
        raise ValueError('launch-record-size-invalid')
    command = [document['unshare'], '--user', '--map-current-user', '--ipc', '--',
               document['native'], '--user-config', document['settings'],
               '--logOptions', 'nocolor,nojournald']
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration', required=True)
    parser.add_argument('--exec-native', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--confined-diagnostic', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--confined-final-native', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--parent-user', help=argparse.SUPPRESS)
    parser.add_argument('--parent-ipc', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        raw = checked_regular(args.configuration, MAX_CONFIG, private=True)
        document = json.loads(raw)
        command = validated_launch(document)
        if (args.parent_user or args.parent_ipc) and not args.confined_final_native:
            raise ValueError('confined-final-arguments-refused')
        if args.confined_final_native:
            from confined_launch import exec_final
            if not args.parent_user or not args.parent_ipc or args.exec_native or args.confined_diagnostic:
                raise ValueError('confined-final-arguments-refused')
            exec_final(document, command, args.parent_user, args.parent_ipc)
        if args.exec_native:
            if args.confined_diagnostic:
                from confined_launch import exec_confined
                exec_confined(document, args.configuration)
            from confined_launch import launch_managed_document
            return launch_managed_document(document)
        # Native Qt library directories must not be applied to the host tracer.
        # The reviewed same-file child loads the private environment only at the
        # exact native launch; no credentials/environment values enter argv.
        host_environment = {key: os.environ[key] for key in ('HOME', 'PATH', 'LANG', 'LC_ALL', 'TMPDIR') if key in os.environ}
        host_environment['PYTHONDONTWRITEBYTECODE'] = '1'
        child = [sys.executable, str(Path(__file__).resolve()), '--configuration',
                 args.configuration, '--exec-native']
        if args.confined_diagnostic:
            child.append('--confined-diagnostic')
        report = observe_owned(document['strace'], child, host_environment,
                               document['cwd'], document['output'])
        # Fixed status only. Raw output and filenames remain inside private files.
        print(json.dumps({'terminal': report['terminal'], 'exitCode': report['exitCode'],
                          'traceTruncated': report['trace']['truncated']}))
        return 0 if report['exitCode'] == 0 else 1
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError, json.JSONDecodeError):
        print('{"terminal":"observer-preflight-or-owned-lifecycle-refused"}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
