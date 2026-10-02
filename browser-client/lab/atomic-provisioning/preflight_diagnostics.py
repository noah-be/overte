# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Fixed observational enums from the original owned preflight's captured output."""
import json
import re
import os
import stat
import secrets

MAX_BYTES = 8192
MAX_COUNT = 2**31 - 1
MILESTONES = ('entry-start', 'observer-imported', 'zero-cap-asserted',
              'tracer-launch-requested', 'observer-returned', 'strict-inner-asserted')
CAPABILITIES = {'CapInh': 'inheritable', 'CapPrm': 'permitted', 'CapEff': 'effective',
                'CapBnd': 'bounding', 'CapAmb': 'ambient'}
TRACER_FAILURES = ('ptrace-operation-not-permitted', 'ptrace-permission-denied',
                   'ptrace-unclassified-error', 'unobserved-or-unclassified')
TERMINALS = ('native-terminal', 'cancelled', 'original-observer-deadline')
FAILURES = ('unobserved-or-unclassified', 'command-exec-not-found', 'command-exec-refused',
            'dynamic-loader-library-not-found', 'dynamic-loader-symbol-unavailable',
            'unshare-operation-not-permitted', 'unshare-permission-denied',
            'capability-action-refused', 'identity-action-refused', 'tracer-ptrace-operation-not-permitted',
            'tracer-ptrace-permission-denied', 'tracer-ptrace-unclassified-error',
            'tracer-exec-not-found', 'python-import-error', 'python-syntax-error',
            'python-assertion-error', 'python-runtime-error')


def capability_states(lines):
    result = {name: 'absent' for name in CAPABILITIES.values()}
    seen = set()
    # Uses exactly the already captured /proc status lines. No new proc read.
    for line in lines:
        if type(line) is not str or len(line) > 256 or ':' not in line:
            continue
        key, value = line.split(':', 1)
        if key not in CAPABILITIES:
            continue
        label = CAPABILITIES[key]
        if key in seen or not re.fullmatch(r'\s*[0-9a-fA-F]{1,16}\s*', value):
            result[label] = 'unparseable'
        elif result[label] != 'unparseable':
            result[label] = 'zero' if int(value, 16) == 0 else 'nonzero'
        seen.add(key)
    return result


def _bounded(data):
    if type(data) is not bytes:
        raise ValueError('preflight-bytes-required')
    return data[:MAX_BYTES], len(data) > MAX_BYTES


def stderr_failure(data):
    bounded, _truncated = _bounded(data)
    # No private executable/name/library/argument substring is returned.
    for raw in bounded.splitlines():
        line = raw.decode('ascii', 'replace')
        if re.fullmatch(r'(?:[^\r\n]*[/ ])?(?:unshare|setpriv|python(?:3(?:\.\d+)?)?|strace): error while loading shared libraries: [^\r\n]+: cannot open shared object file: No such file or directory', line):
            return 'dynamic-loader-library-not-found'
        if re.fullmatch(r'(?:[^\r\n]*[/ ])?(?:unshare|setpriv|python(?:3(?:\.\d+)?)?|strace): symbol lookup error: [^\r\n]+: undefined symbol: [^\r\n]+', line):
            return 'dynamic-loader-symbol-unavailable'
        if re.fullmatch(r'(?:unshare|setpriv): (?:failed to execute|execvp) [^\r\n]+: No such file or directory', line):
            return 'command-exec-not-found'
        if re.fullmatch(r'(?:unshare|setpriv): (?:failed to execute|execvp) [^\r\n]+: Permission denied', line):
            return 'command-exec-refused'
        if line == 'unshare: unshare failed: Operation not permitted':
            return 'unshare-operation-not-permitted'
        if line == 'unshare: unshare failed: Permission denied':
            return 'unshare-permission-denied'
        if re.fullmatch(r'setpriv: (?:apply bounding set|apply capabilities|set capabilities|cap_set_proc|set process securebits)(?:: | failed: )(?:Operation not permitted|Permission denied)', line):
            return 'capability-action-refused'
        if re.fullmatch(r'setpriv: (?:setresuid|setresgid|setgroups|setting no_new_privs) failed: (?:Operation not permitted|Permission denied)', line):
            return 'identity-action-refused'
        if line.startswith('strace: ') and 'ptrace(' in line:
            if line.endswith('Operation not permitted'):
                return 'tracer-ptrace-operation-not-permitted'
            if line.endswith('Permission denied'):
                return 'tracer-ptrace-permission-denied'
            return 'tracer-ptrace-unclassified-error'
        if re.fullmatch(r'strace: (?:exec|Can\x27t stat)[^\r\n]*: No such file or directory', line):
            return 'tracer-exec-not-found'
        if re.match(r'(?:ModuleNotFoundError|ImportError):', line):
            return 'python-import-error'
        if re.match(r'SyntaxError:', line):
            return 'python-syntax-error'
        if re.fullmatch(r'AssertionError(?::[^\r\n]*)?', line):
            return 'python-assertion-error'
        if re.match(r'(?:OSError|FileNotFoundError|PermissionError|RuntimeError|ValueError|TypeError|KeyError|NameError):', line):
            return 'python-runtime-error'
    return 'unobserved-or-unclassified'


def inner_observation(report, captured_native_output, capture_status='read'):
    data, truncated = _bounded(captured_native_output)
    lines = data.splitlines()
    terminal = report.get('terminal')
    code = report.get('exitCode')
    tracer = report.get('tracerFailure')
    fsync = report.get('projection', {}).get('calls', {}).get('fsync', {}).get('success')
    return {'terminal': terminal if terminal in TERMINALS else 'unknown',
            'exitCode': code if type(code) is int and -128 <= code <= 255 else None,
            'fsyncSuccess': fsync if type(fsync) is int and 0 <= fsync <= MAX_COUNT else None,
            'tracerFailure': tracer if tracer in TRACER_FAILURES else 'unobserved-or-unclassified',
            'innerStarted': b'ATOMIC_PREFLIGHT:inner-start' in lines,
            'innerFsyncReturned': b'ATOMIC_PREFLIGHT:inner-fsync' in lines,
            'outputFailure': stderr_failure(data),
            'outputPrefixTruncated': truncated,
            'captureStatus': capture_status if capture_status in ('read', 'read-refused') else 'unknown',
            'nativeOutputTruncated': report.get('nativeOutputTruncated') is True,
            'tracerOutputTruncated': report.get('tracerOutputTruncated') is True}


def _inner(value):
    expected = {'terminal', 'exitCode', 'fsyncSuccess', 'tracerFailure', 'innerStarted',
                'innerFsyncReturned', 'outputFailure', 'outputPrefixTruncated', 'captureStatus',
                'nativeOutputTruncated', 'tracerOutputTruncated'}
    if type(value) is not dict or set(value) != expected:
        return None
    if value['captureStatus'] not in ('read', 'read-refused', 'unknown'):
        return None
    if value['terminal'] not in (*TERMINALS, 'unknown') or value['tracerFailure'] not in TRACER_FAILURES or value['outputFailure'] not in FAILURES:
        return None
    if value['exitCode'] is not None and (type(value['exitCode']) is not int or not -128 <= value['exitCode'] <= 255):
        return None
    if value['fsyncSuccess'] is not None and (type(value['fsyncSuccess']) is not int or not 0 <= value['fsyncSuccess'] <= MAX_COUNT):
        return None
    if any(type(value[k]) is not bool for k in ('innerStarted', 'innerFsyncReturned', 'outputPrefixTruncated',
                                             'nativeOutputTruncated', 'tracerOutputTruncated')):
        return None
    return {k: value[k] for k in expected}


def project_preflight(returncode, stdout, stderr):
    out, out_truncated = _bounded(stdout)
    err, err_truncated = _bounded(stderr)
    seen, caps, inner, malformed = [], None, None, 0
    for raw in out.splitlines():
        if raw.startswith(b'ATOMIC_PREFLIGHT:'):
            milestone = raw[len(b'ATOMIC_PREFLIGHT:'):].decode('ascii', 'replace')
            if milestone in MILESTONES and milestone not in seen:
                seen.append(milestone)
        elif raw.startswith(b'ATOMIC_PREFLIGHT_CAPS:'):
            try:
                value = json.loads(raw[len(b'ATOMIC_PREFLIGHT_CAPS:'):])
            except (ValueError, UnicodeError, RecursionError):
                malformed += 1
                continue
            if type(value) is dict and set(value) == set(CAPABILITIES.values()) and all(v in ('zero', 'nonzero', 'absent', 'unparseable') for v in value.values()):
                caps = {k: value[k] for k in CAPABILITIES.values()}
            else:
                malformed += 1
        elif raw.startswith(b'ATOMIC_PREFLIGHT_OBSERVER:'):
            try:
                value = _inner(json.loads(raw[len(b'ATOMIC_PREFLIGHT_OBSERVER:'):]))
            except (ValueError, UnicodeError, RecursionError):
                value = None
            if value is None:
                malformed += 1
            else:
                inner = value
    return {'schemaVersion': 1, 'scope': 'unchanged-owned-zero-cap-user-ipc-preflight',
            'outerExitCode': returncode if type(returncode) is int and -128 <= returncode <= 255 else None,
            'lastMilestone': seen[-1] if seen else 'none-observed',
            'milestones': seen, 'capabilityStates': caps, 'innerObservation': inner,
            'outerStderrFailure': stderr_failure(err), 'stdoutPrefixTruncated': out_truncated,
            'stderrPrefixTruncated': err_truncated, 'malformedFixedRecords': malformed,
            'cause': 'not-established'}


def retain_failed_preflight(directory, stdout, stderr):
    """Private prefixes from the ORIGINAL completed invocation, never another run.

    Optional reviewed staging directory; no stderr/path/environment is reflected.
    Parent/root tooling alone may inspect files; ordinary curated upload unchanged.
    """
    result = {'status': 'not-configured', 'stdoutRetainedBytes': 0,
              'stderrRetainedBytes': 0, 'stdoutTruncated': False, 'stderrTruncated': False}
    if directory is None:
        return result
    parent = owned = None
    try:
        if type(directory) is not str or type(stdout) is not bytes or type(stderr) is not bytes:
            raise ValueError('private-preflight-input-refused')
        parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        info = os.fstat(parent)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700 or not stat.S_ISDIR(info.st_mode):
            raise ValueError('private-preflight-directory-refused')
        name = 'preflight-failure-' + secrets.token_hex(8)
        os.mkdir(name, 0o700, dir_fd=parent)
        owned = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        for label, data in (('stdout', stdout), ('stderr', stderr)):
            prefix, truncated = _bounded(data)
            fd = os.open(label + '-prefix.private.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=owned)
            try:
                remaining = memoryview(prefix)
                while remaining:
                    written = os.write(fd, remaining)
                    if written <= 0:
                        raise OSError('private-preflight-write-refused')
                    remaining = remaining[written:]
            finally:
                os.close(fd)
            result[label + 'RetainedBytes'] = len(prefix)
            result[label + 'Truncated'] = truncated
        result['status'] = 'retained-private'
    except (OSError, ValueError, TypeError):
        result['status'] = 'retention-refused'
    finally:
        if owned is not None:
            os.close(owned)
        if parent is not None:
            os.close(parent)
    return result
