#!/usr/bin/env python3
"""Require current selected CodeQL results, not merely successful analyzer exits.

Policy: every open CodeQL finding in a selected category blocks this candidate,
without a severity threshold. Dismissed findings do not block. Nothing here
publishes SARIF, retries an analyzer, accepts a caller's API facts, or grants reuse.
Only asynchronous Code Scanning result processing receives a bounded wait.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlencode, quote

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = 'noah-l-frank/overte'
REPOSITORY_ID = 1319052603
PREFIX = 'repos/' + REPOSITORY
WORKFLOW = '.github/workflows/codeql.yml'
ANALYSIS_KEY = WORKFLOW + ':analyze'
MAX_PAGES = 10
PROCESSING_SECONDS = 90
TARGETS = frozenset({'main', 'apple-main', 'apple-ios', 'android-main', 'android-phone', 'android-vr', 'android-vr-pico'})
_SHA = re.compile(r'[0-9a-f]{40}')
_REF = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_./-]*')
_SPEC = importlib.util.spec_from_file_location('trusted_codeql_results_selection', ROOT / 'tools/repository-checks/codeql.py')
codeql = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(codeql)


class ResultError(ValueError):
    """A selected analysis or its current security result is not proven."""


def require(condition, message):
    if not condition:
        raise ResultError(message)


def positive(value):
    require(type(value) is int and value > 0, 'invalid server identity')
    return value


def sha(value):
    require(type(value) is str and _SHA.fullmatch(value) and set(value) != {'0'}, 'invalid server source identity')
    return value


def branch(value):
    require(type(value) is str and _REF.fullmatch(value) and '..' not in value
            and not value.endswith(('/', '.', '.lock')) and '@{' not in value
            and '//' not in value and all(not x.startswith('.') for x in value.split('/')),
            'invalid server branch identity')
    return value


def timestamp(value):
    require(type(value) is str and len(value) <= 40, 'missing execution timestamp')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ResultError('invalid execution timestamp') from None
    require(result.tzinfo is not None and result.utcoffset().total_seconds() == 0,
            'execution timestamp is not UTC')
    return result


def repository(value):
    require(type(value) is dict and value.get('full_name') == REPOSITORY
            and value.get('id') == REPOSITORY_ID, 'foreign or unknown repository')


def languages(value):
    require(type(value) is list and value == [x for x in codeql.LANGUAGES if x in value],
            'unknown, repeated or unordered selected language')
    return value


def unique_json(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON field')
        result[key] = value
    return result


def document(raw):
    return json.loads(raw, object_pairs_hook=unique_json,
                      parse_constant=lambda _: (_ for _ in ()).throw(ResultError('nonfinite JSON')))


def default_api():
    # Only trusted sibling modules are imported; no candidate code is executed.
    sys.path.insert(0, str(ROOT / 'tools/test-evidence'))
    from producer_api import GitHubReadOnly
    return GitHubReadOnly()


class Verifier:
    def __init__(self, root, event, environment, *, api=None, clock=time.monotonic, sleep=time.sleep):
        self.root, self.event, self.env = Path(root), event, environment
        self.api = api if api is not None else default_api()
        self.clock, self.sleep = clock, sleep
        require(type(event) is dict and environment.get('GITHUB_ACTIONS') == 'true', 'Actions server context required')
        require(environment.get('GITHUB_REPOSITORY') == REPOSITORY
                and environment.get('GITHUB_REPOSITORY_ID') == str(REPOSITORY_ID), 'foreign Actions repository')
        repository(event.get('repository'))
        self.event_name = environment.get('GITHUB_EVENT_NAME')
        require(self.event_name in {'pull_request', 'push', 'schedule'}, 'unsupported CodeQL result event')
        self.source = sha(environment.get('GITHUB_SHA'))
        try:
            self.run_id = positive(int(environment.get('GITHUB_RUN_ID', '')))
            self.attempt = positive(int(environment.get('GITHUB_RUN_ATTEMPT', '')))
            self.expected = languages(document(environment.get('CODEQL_EXPECTED_LANGUAGES', '')))
        except (ValueError, TypeError):
            raise ResultError('invalid Actions run or selected-language context') from None
        self.ref = environment.get('GITHUB_REF')
        if self.event_name == 'pull_request':
            pr = event.get('pull_request')
            require(type(pr) is dict, 'missing event PR')
            self.number = positive(event.get('number'))
            require(pr.get('number') == self.number, 'event PR number mismatch')
            self.base, self.head = sha(pr.get('base', {}).get('sha')), sha(pr.get('head', {}).get('sha'))
            self.base_ref, self.head_ref = branch(pr['base'].get('ref')), branch(pr['head'].get('ref'))
            repository(pr['base'].get('repo'))
            repository(pr['head'].get('repo'))
            require(self.ref == f'refs/pull/{self.number}/merge'
                    and environment.get('GITHUB_BASE_REF') == self.base_ref
                    and environment.get('GITHUB_HEAD_REF') == self.head_ref, 'event PR source mismatch')
        else:
            require(type(self.ref) is str and self.ref.startswith('refs/heads/'), 'branch event required')
            self.base_ref = branch(self.ref[len('refs/heads/'):])
            require(environment.get('GITHUB_REF_TYPE') == 'branch', 'branch event type required')
            self.head_ref, self.head = self.base_ref, self.source
            self.base = sha(event.get('before')) if self.event_name == 'push' else self.source
            if self.event_name == 'push':
                require(event.get('ref') == self.ref and event.get('after') == self.source
                        and event.get('deleted') is False, 'push event source mismatch')
            self.number = None
        require(self.base_ref in TARGETS, 'unsupported permanent target branch')
        require(environment.get('GITHUB_WORKFLOW_SHA') == self.source
                and environment.get('GITHUB_WORKFLOW_REF') == REPOSITORY + '/' + WORKFLOW + '@' + self.ref,
                'executed workflow source does not match this server candidate')

    def get(self, endpoint):
        # Endpoints are constructed only inside this trusted controller.
        return self.api.json(PREFIX + ('/' + endpoint if endpoint else ''))

    def obj(self, endpoint):
        value = self.get(endpoint)
        require(type(value) is dict, 'required API object missing')
        return value

    def pages(self, endpoint, *, field=None, identity='id'):
        records, seen, expected = [], set(), None
        for page in range(1, MAX_PAGES + 1):
            response = self.get(endpoint + ('&' if '?' in endpoint else '?') + f'per_page=100&page={page}')
            if field:
                require(type(response) is dict and type(response.get('total_count')) is int
                        and response['total_count'] >= 0, 'incomplete counted API inventory')
                total = response['total_count']
                require(expected is None or expected == total, 'API inventory changed during pagination')
                expected, response = total, response.get(field)
            require(type(response) is list and len(response) <= 100, 'invalid API page')
            for item in response:
                require(type(item) is dict, 'invalid API record')
                key = positive(item.get(identity)) if identity else json.dumps(item, sort_keys=True, allow_nan=False)
                require(key not in seen, 'repeated API page or identity')
                seen.add(key)
            records.extend(response)
            if field:
                require(len(records) <= expected, 'API inventory exceeds declared total')
                if len(records) == expected:
                    return records
                require(len(response) == 100, 'truncated counted API inventory')
            elif len(response) < 100:
                return records
        raise ResultError('API inventory exceeds bounded pagination')

    def ref_sha(self, ref):
        value = self.obj('git/ref/' + quote(ref, safe='/'))
        require(value.get('ref') == 'refs/' + ref and value.get('object', {}).get('type') == 'commit',
                'live branch identity missing')
        return sha(value['object'].get('sha'))

    def context(self):
        repo = self.obj('')
        repository(repo)
        workflow = self.obj('actions/workflows/codeql.yml')
        require(workflow.get('path') == WORKFLOW and workflow.get('state') == 'active', 'CodeQL workflow identity missing')
        run = self.obj(f'actions/runs/{self.run_id}')
        repository(run.get('repository'))
        repository(run.get('head_repository'))
        require(positive(run.get('id')) == self.run_id and positive(run.get('run_attempt')) == self.attempt
                and run.get('workflow_id') == positive(workflow.get('id'))
                and run.get('event') == self.event_name and run.get('path') == WORKFLOW
                and run.get('head_sha') == self.head and run.get('head_branch') == self.head_ref,
                'run source, workflow or latest attempt mismatch')
        require((run.get('status'), run.get('conclusion')) in {('in_progress', None), ('completed', 'success')},
                'current run failed, cancelled or unavailable')
        start = timestamp(run.get('run_started_at'))
        attempt = self.obj(f'actions/runs/{self.run_id}/attempts/{self.attempt}')
        repository(attempt.get('repository'))
        repository(attempt.get('head_repository'))
        require((attempt.get('status'), attempt.get('conclusion')) in {('in_progress', None), ('completed', 'success')},
                'current run attempt failed or was cancelled')
        for key in ('id', 'run_attempt', 'workflow_id', 'event', 'path', 'head_sha', 'head_branch', 'run_started_at'):
            require(attempt.get(key) == run.get(key), 'run attempt changed or is not original current execution')
        if self.number:
            pr = self.obj(f'pulls/{self.number}')
            require(pr.get('number') == self.number and pr.get('state') == 'open'
                    and pr.get('merge_commit_sha') == self.source, 'PR candidate changed')
            for side, expected_ref, expected_sha in (('base', self.base_ref, self.base), ('head', self.head_ref, self.head)):
                value = pr.get(side, {})
                repository(value.get('repo'))
                require(value.get('ref') == expected_ref and value.get('sha') == expected_sha
                        and self.ref_sha('heads/' + expected_ref) == expected_sha, 'PR branch changed')
            commit = self.obj('git/commits/' + self.source)
            require(commit.get('sha') == self.source and type(commit.get('parents')) is list
                    and [p.get('sha') for p in commit['parents']] == [self.base, self.head], 'PR ordered merge parents mismatch')
        else:
            require(self.ref_sha('heads/' + self.base_ref) == self.source, 'branch has advanced beyond this analysis')
            if self.event_name == 'schedule':
                require(repo.get('default_branch') == self.base_ref, 'schedule is not the default branch')
        return {'workflow_id': workflow['id'], 'run_started_at': run['run_started_at'], 'start': start}

    def plan(self):
        try:
            actual = subprocess.check_output(['git', '--no-replace-objects', 'rev-parse', '--verify', 'HEAD^{commit}'],
                                             cwd=self.root, text=True, stderr=subprocess.PIPE, timeout=30).strip()
            require(actual == self.source, 'candidate checkout is not the server source')
            trees = [codeql.inputs.full_tree(self.root, x) for x in (self.base, self.source)]
        except (OSError, subprocess.SubprocessError, codeql.inputs.InputError):
            raise ResultError('complete immutable candidate and base unavailable') from None
        workflows = {codeql._SELECTIVE_WORKFLOW, getattr(codeql, '_RESULTS_WORKFLOW', codeql._SELECTIVE_WORKFLOW)}
        for tree in trees:
            for path, old in codeql._REVIEWED_CONTROLS.items():
                allowed = workflows if path == WORKFLOW else {old}
                require(tree.get(path) in [{'mode': '100644', 'type': 'blob', 'sha': value} for value in allowed],
                        'analysis workflow or configuration is not approved')
        plan = codeql.select_repository(self.root, self.base, self.source, event=self.event_name)
        require(plan['languages'] == self.expected, 'caller language plan differs from independent immutable selection')
        return plan['languages']

    def jobs(self, context, selected):
        records = self.pages(f'actions/runs/{self.run_id}/attempts/{self.attempt}/jobs', field='jobs')
        selectors = [job for job in records if job.get('name') == 'Select affected CodeQL languages']
        require(len(selectors) == 1, 'independent language-selector job missing or ambiguous')
        selector = selectors[0]
        require(positive(selector.get('run_id')) == self.run_id and positive(selector.get('run_attempt')) == self.attempt
                and selector.get('head_sha') == self.head and selector.get('status') == 'completed'
                and selector.get('conclusion') == 'success'
                and context['start'] <= timestamp(selector.get('started_at')) <= timestamp(selector.get('completed_at')),
                'independent language-selector job did not succeed in this attempt')
        windows = {'_selector': (timestamp(selector['started_at']), timestamp(selector['completed_at']),
                                 positive(selector.get('id')))}
        for language in selected:
            matches = [job for job in records if job.get('name') == f'CodeQL ({language})']
            require(len(matches) == 1, 'selected CodeQL job missing or ambiguous')
            job = matches[0]
            require(positive(job.get('run_id')) == self.run_id and positive(job.get('run_attempt')) == self.attempt
                    and job.get('head_sha') == self.head and job.get('status') == 'completed'
                    and job.get('conclusion') == 'success', 'selected CodeQL job did not succeed in current attempt')
            started, completed = timestamp(job.get('started_at')), timestamp(job.get('completed_at'))
            require(context['start'] <= started <= completed, 'selected CodeQL job belongs to an older attempt')
            steps = job.get('steps')
            require(type(steps) is list and all(type(step) is dict for step in steps), 'selected job steps missing')
            analyzes = [step for step in steps if step.get('name') == 'Analyze']
            require(len(analyzes) == 1 and analyzes[0].get('status') == 'completed'
                    and analyzes[0].get('conclusion') == 'success', 'selected Analyze step missing, skipped or failed')
            step_start, step_end = timestamp(analyzes[0].get('started_at')), timestamp(analyzes[0].get('completed_at'))
            require(started <= step_start <= step_end <= completed, 'Analyze step is outside the successful job')
            windows[language] = (step_start, step_end, positive(job.get('id')))
        return windows

    def analyses(self, selected, windows):
        records = self.pages('code-scanning/analyses?' + urlencode({'ref': self.ref, 'tool_name': 'CodeQL'}))
        for record in records:
            require(record.get('ref') == self.ref and record.get('tool', {}).get('name') == 'CodeQL',
                    'analysis inventory does not match its authenticated reference and tool filter')
            sha(record.get('commit_sha'))
        chosen = {}
        for language in selected:
            category = '/language:' + language
            matches = []
            for record in records:
                if record.get('ref') != self.ref or record.get('commit_sha') != self.source or record.get('category') != category:
                    continue
                require(record.get('analysis_key') == ANALYSIS_KEY and record.get('tool', {}).get('name') == 'CodeQL'
                        and record.get('error') == '' and type(record.get('rules_count')) is int
                        and record['rules_count'] > 0, 'selected analysis has errors or unknown analysis identity')
                require(document(record.get('environment', '')) == {'language': language}, 'selected analysis environment mismatch')
                created = timestamp(record.get('created_at'))
                if windows[language][0] <= created <= windows[language][1]:
                    matches.append(record)
            require(len(matches) <= 1, 'current selected analysis is ambiguous')
            if matches:
                chosen[language] = matches[0]
        return chosen

    def open_alerts(self, selected):
        alerts = self.pages('code-scanning/alerts?' + urlencode({'ref': self.ref, 'state': 'open', 'tool_name': 'CodeQL'}), identity='number')
        for alert in alerts:
            require(alert.get('state') == 'open' and alert.get('tool', {}).get('name') == 'CodeQL', 'open-alert inventory is inconsistent')
            instances = self.pages(f'code-scanning/alerts/{positive(alert.get("number"))}/instances?' + urlencode({'ref': self.ref}), identity=None)
            require(instances, 'open alert has no authenticated instances')
            for instance in instances:
                require(instance.get('ref') == self.ref and type(instance.get('category')) is str, 'alert instance reference or category missing')
                require(instance.get('state') in {'open', 'fixed', 'dismissed'}, 'alert instance state missing or unknown')
                if instance['state'] != 'open' or instance['category'] not in {'/language:' + language for language in selected}:
                    continue
                require(instance.get('commit_sha') == self.source, 'selected open-alert instance is stale')
                raise ResultError('open CodeQL finding in a selected category blocks this candidate')

    def verify(self, *, processing_seconds=PROCESSING_SECONDS):
        require(type(processing_seconds) in (int, float) and 0 <= processing_seconds <= PROCESSING_SECONDS,
                'invalid result-processing bound')
        before = self.context()
        selected = self.plan()
        windows = self.jobs(before, selected)
        deadline = self.clock() + processing_seconds
        while selected:
            chosen = self.analyses(selected, windows)
            if len(chosen) == len(selected):
                break
            require(self.clock() < deadline, 'selected current analysis missing after bounded processing wait')
            self.sleep(min(5, max(0, deadline - self.clock())))
        else:
            chosen = {}
        if selected:
            self.open_alerts(selected)
            for record in chosen.values():
                current = self.obj(f'code-scanning/analyses/{positive(record.get("id"))}')
                require(current == record, 'selected analysis changed during verification')
            require(self.analyses(selected, windows) == chosen, 'selected analysis inventory changed during verification')
            self.open_alerts(selected)
        require(self.jobs(before, selected) == windows, 'selected job execution changed during verification')
        require(self.context() == before, 'server candidate or run context changed during verification')
        return {'schema': 1, 'run_id': self.run_id, 'run_attempt': self.attempt, 'languages': selected,
                'analyses': [{'id': chosen[x]['id'], 'category': chosen[x]['category'],
                              'rules_count': chosen[x]['rules_count'], 'job_id': windows[x][2]} for x in selected],
                'open_selected_findings': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--event-file', type=Path, required=True)
    args = parser.parse_args()
    try:
        require(str(args.event_file) == os.environ.get('GITHUB_EVENT_PATH'), 'event file is not the Actions server event')
        require(args.event_file.is_file() and not args.event_file.is_symlink()
                and args.event_file.stat().st_size <= 2_000_000, 'invalid bounded server event file')
        result = Verifier(args.root, document(args.event_file.read_bytes()), os.environ).verify()
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OSError, RuntimeError, subprocess.SubprocessError):
        print('Selected CodeQL security results could not be verified; details withheld.', file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
