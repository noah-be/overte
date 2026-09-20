# SPDX-License-Identifier: Apache-2.0
"""Separate inherited-history risk decisions; never revocation or false positives.

Secret fragments are read from bound Git objects into memory, never logged or
passed in argv. This check covers literal reintroduction in tracked source only;
independent source/artifact scanners still handle new or transformed secrets.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace

from history_review import reviewed_exception, validate_reviews


EXTRA = {'group', 'probes', 'disposition', 'reviewed_revision'}


def load_risks(path):
    data = json.loads(Path(path).read_text())
    if (not isinstance(data, dict) or set(data) != {'schema', 'entries'}
            or data['schema'] != 1 or not isinstance(data['entries'], list)):
        raise ValueError('Invalid historical risk registry')
    for e in data['entries']:
        if (not isinstance(e, dict) or not EXTRA <= e.keys()
                or e['disposition'] != 'inherited-history-risk-accepted'
                or not isinstance(e['group'], str) or not e['group'].strip()
                or not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', e['reviewed_revision'])
                or not isinstance(e['probes'], list) or not e['probes']):
            raise ValueError('Invalid historical risk decision')
        for p in e['probes']:
            if (not isinstance(p, dict) or set(p) != {'offset', 'length', 'sha256'}
                    or type(p['offset']) is not int or p['offset'] < 0
                    or type(p['length']) is not int or not 20 <= p['length'] <= 256
                    or not re.fullmatch(r'[a-f0-9]{64}', p['sha256'])):
                raise ValueError('Invalid historical fragment binding')
    validate_reviews({'schema': 1, 'entries': [
        {k: v for k, v in e.items() if k not in EXTRA} for e in data['entries']]})
    return data['entries']


def reviewed_risk(g, row, path):
    entries = getattr(g, 'history_risks', [])
    entry = reviewed_exception(SimpleNamespace(root=g.root, history_exceptions=entries), row, path)
    if not entry:
        return None
    try:
        result = subprocess.run(['git', 'show', entry['commit'] + ':' + entry['path']],
                                cwd=g.root, capture_output=True, timeout=30)
        blob = result.stdout
        if result.returncode or hashlib.sha256(blob).hexdigest() != entry['blob_sha256']:
            return None
        probes = []
        for p in entry['probes']:
            fragment = blob[p['offset']:p['offset'] + p['length']]
            if (len(fragment) != p['length'] or b'\n' in fragment or b'\r' in fragment
                    or b'\0' in fragment or hashlib.sha256(fragment).hexdigest() != p['sha256']):
                return None
            probes.append(fragment)
        # Both index and working tree, all tracked paths, not just Android scope.
        # --no-textconv avoids configured external conversion commands.
        for extra in ([], ['--cached']):
            result = subprocess.run(
                ['git', 'grep', '--no-textconv', '-l', '-F', *extra, '-f', '-', '--', '.'],
                input=b'\n'.join(probes) + b'\n', cwd=g.root,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            if result.returncode != 1:  # A match OR an error keeps the finding FAIL.
                return None
        return entry
    except (OSError, subprocess.TimeoutExpired):
        return None
