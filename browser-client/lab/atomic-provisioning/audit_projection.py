# SPDX-License-Identifier: Apache-2.0
"""Bounded passive projection; never infer success or absence of a denial."""
import re

MAX_BYTES = 65536
MAX_LINES = 128
MAX_LINE = 2048
_PREFIX = re.compile(r'^(?:\[\s*[0-9.]+\]\s*)?(?:audit:\s*)?type=1400 audit\([0-9.]+:[0-9]+\):\s*')
_FIELD = re.compile(r'([a-z_]+)=(?:"([^"\\\r\n]*)"|([A-Za-z0-9_:./-]+))(?=\s|$)')


def project(raw, owned_pid=None):
    result = {
        'status': 'unobserved', 'censored': False,
        'matchingSetpcapDenials': 0, 'sameOwnedPidDenials': 0,
        'ownershipCorrelation': 'unknown',
    }
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        result.update(status='bounded-input-refused', censored=True)
        return result
    if owned_pid is not None and (type(owned_pid) is not int or not 1 <= owned_pid <= 2**31-1):
        result.update(status='ownership-input-refused')
        return result
    lines = raw.splitlines()
    if len(lines) > MAX_LINES:
        result.update(status='bounded-input-refused', censored=True)
        return result
    for line in lines:
        if len(line) > MAX_LINE:
            result['censored'] = True
            continue
        try:
            text = line.decode('ascii', 'strict')
        except UnicodeDecodeError:
            continue
        prefix = _PREFIX.match(text)
        if not prefix:
            continue
        fields = {}
        duplicate = False
        remaining = text[prefix.end():]
        while remaining:
            match = _FIELD.match(remaining)
            if not match:
                duplicate = True
                break
            key, quoted, bare = match.groups()
            if key in fields:
                duplicate = True
                break
            fields[key] = quoted if quoted is not None else bare
            remaining = remaining[match.end():].lstrip()
        if duplicate:
            continue
        expected = {'apparmor': 'DENIED', 'operation': 'capable',
                    'profile': 'unshare//unpriv', 'comm': 'setpriv',
                    'capability': '8', 'capname': 'setpcap'}
        if not all(fields.get(key) == value for key, value in expected.items()):
            continue
        pid = fields.get('pid', '')
        if not pid.isdecimal() or len(pid) > 10 or not 1 <= int(pid) <= 2**31-1:
            continue
        result['matchingSetpcapDenials'] += 1
        if owned_pid is not None and int(pid) == owned_pid:
            result['sameOwnedPidDenials'] += 1
    if result['sameOwnedPidDenials']:
        result.update(status='owned-setpcap-audit-denial', ownershipCorrelation='same-owned-pid')
    elif result['matchingSetpcapDenials']:
        result.update(status='uncorrelated-setpcap-audit-denial')
    else:
        result.update(status='no-matching-audit-record')
    # Missing/audit-lost/nonmatching records never prove absence of a kernel
    # refusal, absence of CAP_SETPCAP, or success of the original command.
    return result
