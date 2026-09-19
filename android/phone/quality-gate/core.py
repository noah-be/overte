# SPDX-License-Identifier: Apache-2.0
"""Private evidence, exact exceptions, and fail-closed command execution."""
from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

CATEGORIES = {
    'secrets': 'Secrets & Privacy', 'hygiene': 'Repository Hygiene',
    'licenses': 'Licenses & Branding', 'dependencies': 'Dependencies & Supply Chain',
    'static': 'Static Analysis', 'android': 'Android Configuration',
    'fdroid': 'F-Droid Compatibility', 'build': 'Clean Build',
    'artifact': 'APK/AAB Analysis', 'functional': 'Functional E2E Tests',
    'robustness': 'Robustness Tests', 'long': 'Long-Running Tests',
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


class Gate:
    def __init__(self, root, out, config, policy):
        self.root, self.out, self.config, self.policy = root, out, config, policy
        self.findings, self.commands, self.completed = [], [], []
        self.source_hashes = {}
        self.receipt = None
        self.category = 'secrets'
        self.commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
        self.assert_source_unchanged()
        self.files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
        self.files = sorted(p for p in self.files if p and self.in_scope(p))
        self.artifact = None
        self.attempt = None
        self.exceptions = json.loads((Path(__file__).parent / 'allowlist.json').read_text())['entries']
        for e in self.exceptions:
            if (set(e) != {'rule', 'path', 'sha256', 'reason', 'owner', 'expires'}
                    or not re.fullmatch(r'[0-9a-f]{64}', e['sha256'])
                    or not e['reason'].strip() or not e['owner'].strip()):
                raise ValueError('Invalid allowlist entry')
            dt.date.fromisoformat(e['expires'])
        self.env = {k: os.environ[k] for k in ('PATH', 'LANG', 'LC_ALL', 'TZ') if k in os.environ}
        # No inherited signing keys, Gradle properties, Conan remotes, or device selectors.
        for k, v in config.get('tool_environment', {}).items():
            if k not in {'GRYPE_DB_CACHE_DIR', 'JAVA_HOME', 'ANDROID_SDK_ROOT', 'ANDROID_HOME'}:
                raise ValueError('Unsupported tool_environment key')
            self.env[k] = str(v)
        processes = config.get('scancode_processes', 2)
        if type(processes) is not int or not 1 <= processes <= 8:
            raise ValueError('ScanCode processes must be between 1 and 8')
        db_age = config.get('vulnerability_database_max_age_hours', 120)
        if type(db_age) is not int or not 1 <= db_age <= 120:
            raise ValueError('Vulnerability database age must be between 1 and 120 hours')
        for key, default in [('command_timeout_seconds', 21600), ('build_timeout_seconds', 172800)]:
            value = config.get(key, default)
            if type(value) is not int or value <= 0:
                raise ValueError('Command timeouts must be positive integer seconds')
        self.env.update(HOME=str(out / 'tool-home'), TMPDIR=str(out / 'tmp'),
                        PYTHONDONTWRITEBYTECODE='1',
                        GRYPE_DB_AUTO_UPDATE='false', GRYPE_DB_VALIDATE_AGE='true',
                        GRYPE_DB_MAX_ALLOWED_BUILT_AGE=f'{db_age}h')
        (out / 'tool-home').mkdir()
        (out / 'tmp').mkdir()
        (out / 'logs').mkdir()

    def in_scope(self, p):
        return (p in self.policy['source_files'] or p.startswith('LICENSES/')
                or any(p.startswith(r) for r in self.policy['source_roots'])) and not any(
                    p.startswith(r) for r in self.policy['exclude_roots'])

    def assert_source_unchanged(self):
        current = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.root, text=True).strip()
        dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=self.root)
        if current != self.commit or dirty:
            raise ValueError('Gate requires an unchanged, clean committed checkout, including untracked files')

    @contextmanager
    def category_scope(self, category):
        previous = self.category
        self.category = category
        try:
            yield
        except Exception as error:
            self.fail('execution-error', f'{type(error).__name__}: see private error-{category}.txt.')
            (self.out / f'error-{category}.txt').write_text(str(error) + '\n')
        finally:
            self.category = previous

    def finding(self, rule, status, path, message, action, line=None, fdroid=False, suppressible=True):
        # Only source-snapshot paths are eligible for source exceptions. An APK
        # member with the same name must never borrow an unrelated source hash.
        sha = self.source_hashes.get(path) if self.category not in {'artifact', 'functional', 'robustness', 'long'} else None
        waived = None
        if suppressible:
            for e in self.exceptions:
                if (sha is not None and e['rule'] == rule and e['path'] == path and e['sha256'] == sha
                        and dt.date.fromisoformat(e['expires']) >= dt.date.today()):
                    waived = e
                    break
        self.findings.append(dict(category=self.category, rule=rule,
                                  status='WARNING' if waived else status, path=path, line=line,
                                  message=message, action=action, fdroid_critical=fdroid,
                                  file_sha256=sha, exception=waived))

    def fail(self, rule, message, path='', fdroid=False):
        self.finding(rule, 'FAIL', path, message, 'Supply valid evidence or fix the failure and rerun.',
                     fdroid=fdroid, suppressible=False)

    def run(self, label, argv, cwd=None, timeout=None, env=None, required=True, ok=(0,)):
        log = self.out / 'logs' / (re.sub(r'[^a-zA-Z0-9_.-]', '-', label) + '.log')
        started = time.monotonic()
        code = None
        try:
            with log.open('wb') as stream:
                proc = subprocess.Popen([str(v) for v in argv], cwd=cwd or self.root,
                                        env=env or self.env, stdout=stream, stderr=subprocess.STDOUT,
                                        start_new_session=True)
                try:
                    code = proc.wait(timeout=timeout or self.config.get('command_timeout_seconds', 21600))
                except (subprocess.TimeoutExpired, KeyboardInterrupt):
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        proc.wait()
                    raise
        except FileNotFoundError:
            self.fail('tool-missing', f'{label}: required executable is unavailable.')
        except subprocess.TimeoutExpired:
            self.fail('tool-timeout', f'{label}: time limit exceeded; inspect private log {log.name}.')
        self.commands.append(dict(label=label, exit_code=code, seconds=round(time.monotonic()-started, 2),
                                  log='logs/' + log.name))
        if code is not None and code not in ok and required:
            self.fail('command-failed', f'{label}: exit {code}; details in private log {log.name}.')
        return code, log

    def tool(self, name, version_args=('--version',)):
        expected = self.config.get('tool_versions', {}).get(name)
        rc, log = self.run('version-' + name, [name, *version_args])
        if rc != 0:
            return False
        if not isinstance(expected, str) or not expected.strip():
            self.fail('tool-pin', f'Freeze a reviewed version string for {name} in tool_versions.')
            return False
        if expected.strip() not in {line.strip() for line in log.read_text(errors='replace').splitlines()}:
            self.fail('tool-pin', f'{name}: installed version differs from the reviewed version.')
            return False
        return True

    def review(self, category, artifact=False):
        ids = self.policy['manual_reviews'].get(category, [])
        path = self.config.get('manual_evidence')
        data = json.loads(Path(path).read_text()) if path else {}
        for name in ids:
            e = data.get('reviews', {}).get(name, {})
            valid = (data.get('source_commit') == self.commit and e.get('status') == 'PASS'
                     and e.get('reviewer') and e.get('reason') and e.get('evidence_file')
                     and re.fullmatch(r'[0-9a-f]{64}', e.get('evidence_sha256', '')))
            if artifact:
                valid = valid and self.artifact is not None and data.get('artifact_sha256') == digest(self.artifact)
            if valid:
                evidence = Path(e['evidence_file'])
                valid = evidence.is_file() and not evidence.is_symlink() and digest(evidence) == e['evidence_sha256']
            if not valid:
                self.fail('review-' + name, f'Missing current, digest-bound manual review: {name}.', fdroid=category in {'licenses','fdroid'})
            else:
                self.finding('review-' + name, 'PASS', '', f'Manual review accepted: {name}.',
                             'Retain private supporting evidence.', suppressible=False)

    def report(self, selected):
        artifact_hash = None
        if self.artifact:
            try:
                artifact_hash = digest(self.artifact)
                if self.receipt and artifact_hash != self.receipt.get('artifact_sha256'):
                    raise ValueError('Artifact changed')
            except (OSError, ValueError):
                self.category = 'artifact'
                self.fail('artifact-changed', 'Artifact is missing or changed at report completion.')
        statuses = {}
        for c in CATEGORIES:
            rows = [r for r in self.findings if r['category'] == c]
            statuses[c] = ('FAIL' if c not in self.completed or any(r['status']=='FAIL' for r in rows)
                           else 'WARNING' if any(r['status']=='WARNING' for r in rows) else 'PASS')
        full_pass = set(selected) == set(CATEGORIES) and all(v != 'FAIL' for v in statuses.values())
        final = 'ANDROID F-DROID RELEASE CHECK: ' + ('PASS' if full_pass else 'FAIL')
        write_json(self.out / 'report.json', dict(schema=1, source_commit=self.commit,
                   artifact_sha256=artifact_hash,
                   complete_run=set(selected)==set(CATEGORIES), categories=statuses,
                   findings=self.findings, commands=self.commands, result=final))
        lines = ['# Android F-Droid release readiness', '', final, '',
                 'Source: `' + self.commit + '`', '', '| Category | Status |', '|---|---|']
        for c, name in CATEGORIES.items():
            lines.append(f'| {name} | {statuses[c]}' + (' (not run)' if c not in self.completed else '') + ' |')
        lines += ['', '## Findings', '', 'The complete, untruncated inventory is in report.json. This summary shows up to 50 findings per category, failures first.', '']
        for c, name in CATEGORIES.items():
            rows = sorted([r for r in self.findings if r['category'] == c], key=lambda r: {'FAIL': 0, 'WARNING': 1, 'PASS': 2}[r['status']])
            lines += [f'### {name} ({len(rows)} findings)', '']
            for r in rows[:50]:
                where = (r['path'] + (':' + str(r['line']) if r['line'] else '')).replace('|', '\\|')
                lines.append(f"- **{r['status']}** {'[F-DROID CRITICAL] ' if r['fdroid_critical'] else ''}`{r['rule']}` {where}: {r['message']} Next: {r['action']}")
            lines.append('')
        (self.out / 'report.md').write_text('\n'.join(lines) + '\n')
        print(final, flush=True)
        return 0 if full_pass else 1
