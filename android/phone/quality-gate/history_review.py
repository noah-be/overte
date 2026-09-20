# SPDX-License-Identifier: Apache-2.0
"""Exact historical false positives; never accepts credential revocation waivers."""
import datetime as dt
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


def load_reviews(path):
    return validate_reviews(json.loads(Path(path).read_text()))


def validate_reviews(data):
    if set(data) != {'schema', 'entries'} or data['schema'] != 1 or not isinstance(data['entries'], list):
        raise ValueError('Invalid historical review document')
    identities = set()
    for e in data['entries']:
        if (set(e) != {'commit', 'path', 'rule', 'blob_sha256', 'locations', 'reason', 'owner', 'expires'}
                or not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', e['commit'])
                or not re.fullmatch(r'[a-f0-9]{64}', e['blob_sha256'])
                or not e['rule'].startswith('gitleaks-') or not e['reason'].strip() or not e['owner'].strip()
                or not e['path'] or PurePosixPath(e['path']).is_absolute()
                or '..' in PurePosixPath(e['path']).parts or '\\' in e['path']
                or not isinstance(e['locations'], list) or not e['locations']):
            raise ValueError('Invalid historical review entry')
        dt.date.fromisoformat(e['expires'])
        for location in e['locations']:
            if (not isinstance(location, list) or len(location) != 2
                    or any(type(n) is not int for n in location) or not 1 <= location[0] <= location[1]):
                raise ValueError('Invalid historical review location')
            identity = (e['commit'], e['path'], e['rule'], *location)
            if identity in identities:
                raise ValueError('Duplicate historical review location')
            identities.add(identity)
    return data['entries']


def reviewed_exception(g, row, path):
    # Called only by the history scanner. Source/artifact scans have no access
    # to these exceptions. Check exact detector identity before reading Git.
    if any(type(row.get(key)) is not int for key in ('StartLine', 'EndLine')):
        return None
    for e in g.history_exceptions:
        if (e['commit'] != row['Commit'] or e['path'] != path
                or e['rule'] != 'gitleaks-' + row['RuleID']
                or [row.get('StartLine'), row.get('EndLine')] not in e['locations']
                or dt.date.fromisoformat(e['expires']) < dt.date.today()):
            continue
        result = subprocess.run(['git', 'show', e['commit'] + ':' + path],
                                cwd=g.root, capture_output=True, timeout=30)
        if result.returncode == 0 and hashlib.sha256(result.stdout).hexdigest() == e['blob_sha256']:
            return e
    return None
