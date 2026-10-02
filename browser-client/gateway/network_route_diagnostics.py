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

# Observation only: no profile transition, namespace creation or capability mutation.
# Final proc files are fixed; namespace symlinks are read only for equality.
import os
import re

PROC_LIMIT = 4096
CAP_FIELDS = {'CapInh': 'inheritable', 'CapPrm': 'permitted', 'CapEff': 'effective', 'CapBnd': 'bounding', 'CapAmb': 'ambient'}

def _read_proc(filename):
    fd = os.open(filename, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        data = os.read(fd, PROC_LIMIT + 1)
        return data if len(data) <= PROC_LIMIT else None
    finally:
        os.close(fd)

def owner_confinement_diagnostic(read=_read_proc, readlink=os.readlink):
    def bounded(filename):
        try:
            data = read(filename)
            return data if type(data) is bytes and len(data) <= PROC_LIMIT else None
        except OSError:
            return None
    status = bounded('/proc/self/status')
    caps = {label: 'unavailable' for label in CAP_FIELDS.values()}
    net_admin = {label: 'unavailable' for label in ('permitted', 'effective', 'bounding')}
    if status is not None:
        lines = status.splitlines()
        for field, label in CAP_FIELDS.items():
            values = [line.split(b':', 1)[1].strip() for line in lines if line.startswith(field.encode() + b':')]
            if len(values) != 1 or not re.fullmatch(b'[0-9a-fA-F]{1,16}', values[0]):
                caps[label] = 'invalid'
                if label in net_admin: net_admin[label] = 'invalid'
                continue
            value = int(values[0], 16)
            caps[label] = 'nonzero' if value else 'zero'
            if label in net_admin: net_admin[label] = 'present' if value & (1 << 12) else 'absent'
    label = bounded('/proc/self/attr/apparmor/current')
    if label is None: label = bounded('/proc/self/attr/current')
    profile = 'unavailable'
    if label is not None:
        label = label.strip()
        # Exact recognized shipped labels only; unknown stacked/site labels stay opaque.
        profiles = {b'unconfined': 'unconfined', b'unshare (enforce)': 'unshare',
                    b'unshare//unpriv (enforce)': 'unshare-unpriv', b'bwrap (enforce)': 'bwrap',
                    b'unpriv_bwrap (enforce)': 'unpriv-bwrap',
                    b'bwrap//&unpriv_bwrap (enforce)': 'bwrap-unpriv-stacked'}
        profile = profiles.get(label, 'unrecognized')
    relations = {}
    for kind in ('user', 'net'):
        try:
            left = readlink('/proc/self/ns/' + kind)
            right = readlink('/proc/1/ns/' + kind)
            pattern = kind + r':\[[0-9]{1,20}\]'
            relations[kind] = ('same-as-visible-pid1' if left == right else 'different-from-visible-pid1') \
                if type(left) is str and type(right) is str and re.fullmatch(pattern, left) and re.fullmatch(pattern, right) else 'invalid'
        except OSError:
            relations[kind] = 'unavailable'
    return {'profile': profile, 'capabilitySets': caps, 'netAdmin': net_admin, 'namespaceRelations': relations}
