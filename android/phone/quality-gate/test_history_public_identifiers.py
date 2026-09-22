# SPDX-License-Identifier: Apache-2.0
"""Offline contracts for the 11 public-identifier historical dispositions.

Reads exact existing Git objects only; does not scan history or contact services.
Never prints historical source lines or identifier values.
"""
import copy
import hashlib
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
import unittest

from history_review import load_reviews, reviewed_exception


ROOT = Path(__file__).resolve().parents[3]
REVIEW = Path(__file__).with_name('history-allowlist.json')
IDENTITIES = {
    ('a304cd7077289dbf7d2eeb656b4f21f7ce5352aa', '.github/workflows/pr_build.yml', 23): 'sentry',
    ('a304cd7077289dbf7d2eeb656b4f21f7ce5352aa', '.github/workflows/linux_server_build.yml', 242): 'sentry',
    ('d786308aab64b55f8a5401fc809e1c0ff310f080', '.github/workflows/linux_server_build.yml', 207): 'sentry',
    ('ee705d285e3b5e0d65accffdf8bfbfab9c6448f1', '.github/workflows/linux_server_build.yml', 210): 'sentry',
    ('d09be20e7f3981b96b6dbeed3ecec8bc29ea5ada', '.github/workflows/linux_server_build.yml', 210): 'sentry',
    ('2780f375eabafa8591904bd4037edfbe98001874', '.github/workflows/pr_build.yml', 25): 'sentry',
    ('2780f375eabafa8591904bd4037edfbe98001874', '.github/workflows/linux_server_build.yml', 216): 'sentry',
    ('d9255eed953517a87c95cb9e3b10445e32e3f13e', '.github/workflows/pr_build.yml', 17): 'sentry',
    ('f39088fb0b72313a614e614660e5e97f6bb8cb90', '.github/workflows/master_build.yml', 52): 'oauth',
    ('f39088fb0b72313a614e614660e5e97f6bb8cb90', '.github/workflows/master_build.yml', 57): 'oauth',
    ('d4b3a9ba49f4e131065aa05ac90d70aeb2544da3', '.github/workflows/cmake.yml', 61): 'oauth',
}


def blob(commit, path):
    return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)


class HistoricalPublicIdentifiers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # These integration assertions need the original historical objects.
        # A shallow CI checkout cannot verify their contents. Keep this explicit
        # rather than treating unavailable history as a changed disposition.
        shallow = subprocess.check_output(
            ['git', 'rev-parse', '--is-shallow-repository'], cwd=ROOT, text=True).strip()
        if shallow == 'true':
            for commit, path, _ in IDENTITIES:
                available = subprocess.run(['git', 'cat-file', '-e', commit + ':' + path],
                                           cwd=ROOT, capture_output=True)
                if available.returncode:
                    raise unittest.SkipTest(
                        'Historical source-binding integration tests require a full Git checkout; '
                        'source/artifact checks and synthetic exception tests remain enabled')

    def test_exact_source_binding_and_public_roles(self):
        entries = load_reviews(REVIEW)
        for (commit, path, line), role in IDENTITIES.items():
            with self.subTest(commit=commit, path=path, line=line):
                matches = [e for e in entries if e['commit'] == commit and e['path'] == path
                           and e['locations'] == [[line, line]]]
                self.assertEqual(len(matches), 1)
                entry = matches[0]
                source = blob(commit, path)
                self.assertTrue(hashlib.sha256(source).hexdigest() == entry['blob_sha256'])
                text = source.decode().splitlines()[line - 1]
                if role == 'sentry':
                    # Check role without ever exposing the literal on failure.
                    self.assertTrue(bool(re.search(r'/minidump/?\?sentry_key=[a-f0-9]{32}', text)))
                    self.assertTrue('sentry_secret' not in text and 'CMAKE_BACKTRACE_TOKEN' not in text)
                else:
                    self.assertTrue(bool(re.search(r'\b(?:ANDROID_)?OAUTH_CLIENT_ID\s*[:=]', text)))
                    gradle = blob(commit, 'android/apps/interface/build.gradle').decode()
                    login = blob(commit, 'android/apps/interface/src/main/java/io/highfidelity/hifiinterface/fragment/LoginFragment.java').decode()
                    self.assertTrue('System.getenv("OAUTH_CLIENT_ID")' in gradle)
                    self.assertTrue('System.getenv("OAUTH_CLIENT_SECRET")' in gradle)
                    self.assertTrue('sb.append("?client_id=").append(OAUTH_CLIENT_ID)' in login)

    def test_exceptions_do_not_cover_changed_findings(self):
        entries = load_reviews(REVIEW)
        gate = SimpleNamespace(root=ROOT, history_exceptions=entries)
        for commit, path, line in IDENTITIES:
            row = {'Commit': commit, 'RuleID': 'generic-api-key', 'StartLine': line, 'EndLine': line}
            self.assertIsNotNone(reviewed_exception(gate, row, path))
            for field, value in [('Commit', '0' * 40), ('RuleID', 'private-key'),
                                 ('StartLine', line + 1000), ('EndLine', line + 1000)]:
                changed = copy.deepcopy(row)
                changed[field] = value
                self.assertIsNone(reviewed_exception(gate, changed, path))
            self.assertIsNone(reviewed_exception(gate, row, 'unrelated-file'))


if __name__ == '__main__':
    unittest.main()
