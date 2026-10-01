# SPDX-License-Identifier: Apache-2.0
"""Fixed RTNETLINK categories from already-captured owned route-command stderr."""
MAX_STDERR = 4096
MESSAGES = {
    b'RTNETLINK answers: Operation not permitted': 'permission-denied',
    b'RTNETLINK answers: Permission denied': 'permission-denied',
    b'RTNETLINK answers: File exists': 'route-exists',
    b'RTNETLINK answers: Network is unreachable': 'network-unreachable',
    b'RTNETLINK answers: Invalid argument': 'invalid-request',
    b'RTNETLINK answers: No such process': 'missing-route',
    b'RTNETLINK answers: No buffer space available': 'kernel-resource-unavailable',
}

def route_failure_diagnostic(error):
    data = error.stderr if isinstance(error.stderr, bytes) else b''
    category = 'unclassified-route-error'
    for line in data[:MAX_STDERR].splitlines():
        candidate = MESSAGES.get(line.strip())
        if candidate is not None:
            category = candidate
            break
    code = error.returncode
    return {'category': category, 'stderrBytes': min(len(data), (1 << 53) - 1),
            'truncated': len(data) > MAX_STDERR,
            'exitCode': code if type(code) is int and 0 <= code <= 255 else None}
