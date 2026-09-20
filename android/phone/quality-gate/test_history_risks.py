# SPDX-License-Identifier: Apache-2.0
"""Offline inherited-history contracts using disposable Git repositories."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from history_risks import load_risks, reviewed_risk


class HistoricalRisks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git('init', '-q')
        hooks = self.root / 'empty-hooks'
        hooks.mkdir()
        self.git('config', 'core.hooksPath', str(hooks))
        self.git('config', 'commit.gpgSign', 'false')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.value = b'SYNTHETIC-NEVER-A-SERVICE-CREDENTIAL'
        self.source = b'prefix ' + self.value + b' suffix\n'
        (self.root / 'old.txt').write_bytes(self.source)
        self.git('add', '.')
        self.git('commit', '-qm', 'Synthetic historical input')
        self.commit = self.git('rev-parse', 'HEAD').decode().strip()
        self.git('rm', '-q', 'old.txt')
        (self.root / 'current.txt').write_text('clean current source\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Remove synthetic input')
        self.entry = dict(commit=self.commit, path='old.txt', rule='gitleaks-fixture',
            blob_sha256=hashlib.sha256(self.source).hexdigest(), locations=[[1, 1]],
            reason='Synthetic inherited-risk review', owner='Fixture', expires='2099-01-01',
            group='Synthetic', disposition='inherited-history-risk-accepted',
            reviewed_revision=self.git('rev-parse', 'HEAD').decode().strip(),
            probes=[dict(offset=7, length=len(self.value), sha256=hashlib.sha256(self.value).hexdigest())])
        self.g = SimpleNamespace(root=self.root, history_risks=[self.entry])
        self.row = dict(Commit=self.commit, RuleID='fixture', StartLine=1, EndLine=1)

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.DEVNULL)

    def test_absent_history_is_warning_eligible_but_reintroduction_is_not(self):
        self.assertIsNotNone(reviewed_risk(self.g, self.row, 'old.txt'))
        # Reintroduction at a different path outside Android scope, including binary data.
        current = self.root / 'current.txt'
        current.write_bytes(b'\0' + self.value + b'\0')
        self.assertIsNone(reviewed_risk(self.g, self.row, 'old.txt'))
        self.git('add', '.')
        current.write_text('working tree clean but index contains the value')
        self.assertIsNone(reviewed_risk(self.g, self.row, 'old.txt'))

    def test_binding_expiry_and_unavailable_evidence_fail_closed(self):
        for field, value in [('commit', '0' * 40), ('blob_sha256', '0' * 64),
                             ('expires', '2000-01-01'), ('locations', [[2, 2]]),
                             ('rule', 'gitleaks-other'), ('path', 'other.txt')]:
            with self.subTest(field=field):
                e = copy.deepcopy(self.entry)
                e[field] = value
                self.g.history_risks = [e]
                self.assertIsNone(reviewed_risk(self.g, self.row, 'old.txt'))
        for field, value in [('offset', 8), ('length', 25), ('sha256', '0' * 64)]:
            e = copy.deepcopy(self.entry)
            e['probes'][0][field] = value
            self.g.history_risks = [e]
            self.assertIsNone(reviewed_risk(self.g, self.row, 'old.txt'))
        self.g.history_risks = [self.entry]
        real_run = subprocess.run
        def broken_grep(args, **kwargs):
            if args[1] == 'grep':
                return SimpleNamespace(returncode=2)
            return real_run(args, **kwargs)
        with patch('history_risks.subprocess.run', side_effect=broken_grep):
            self.assertIsNone(reviewed_risk(self.g, self.row, 'old.txt'))

    def test_registry_rejects_broad_or_incomplete_decisions(self):
        path = self.root / 'registry.json'
        data = {'schema': 1, 'entries': [self.entry]}
        path.write_text(json.dumps(data))
        self.assertEqual(load_risks(path), [self.entry])
        for field, value in [('disposition', 'revoked'), ('probes', []),
                             ('wildcard', '*'), ('reviewed_revision', 'main')]:
            changed = copy.deepcopy(data)
            changed['entries'][0][field] = value
            path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                load_risks(path)
        data['entries'].append(self.entry)
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            load_risks(path)


if __name__ == '__main__':
    unittest.main()
