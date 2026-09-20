#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Local-only Android Phone release gate. Running this file executes selected checks."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys

# Keep the reviewed source checkout read-only during orchestration.
sys.dont_write_bytecode = True
from core import CATEGORIES, Gate, digest, write_json
import source_checks as source
import runtime_checks as runtime


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New private directory outside the repository')
    parser.add_argument('--only', choices=list(CATEGORIES), action='append', help='Repeat for partial checks; never grants full release PASS')
    args = parser.parse_args()
    os.umask(0o077)
    root = Path(__file__).resolve().parents[3]
    out = args.output.expanduser().resolve()
    if out == root or root in out.parents or out.exists():
        parser.error('Output must be a new directory outside the repository')
    config = json.loads(args.config.read_text())
    if config.get('schema') != 1:
        parser.error('Unsupported configuration schema')
    if root in args.config.resolve().parents:
        parser.error('Private configuration must be outside the repository')
    policy = json.loads((Path(__file__).parent / 'policy.json').read_text())
    out.mkdir(parents=True, mode=0o700)
    gate = Gate(root, out, config, policy)
    write_json(out / 'run-inputs.json', dict(source_commit=gate.commit,
               config_sha256=digest(args.config), policy_sha256=digest(Path(__file__).parent / 'policy.json'),
               allowlist_sha256=digest(Path(__file__).parent / 'allowlist.json')))
    write_json(out / 'history-review-input.json', dict(
        sha256=digest(Path(__file__).with_name('history-allowlist.json'))))
    selected = args.only or list(CATEGORIES)
    handlers = dict(secrets=source.secrets, hygiene=source.hygiene, licenses=source.licenses,
                    dependencies=source.dependencies, static=runtime.static, android=source.android,
                    fdroid=source.fdroid, build=runtime.build, artifact=runtime.artifact,
                    functional=lambda g: runtime.e2e(g, 'functional'),
                    robustness=lambda g: runtime.e2e(g, 'robustness'), long=lambda g: runtime.e2e(g, 'long'))
    try:
        source.materialize(gate)
        for category in CATEGORIES:
            if category not in selected:
                continue
            gate.category = category
            print('Running: ' + CATEGORIES[category], flush=True)
            try:
                handlers[category](gate)
            except Exception as error:
                # Exception text may contain a selector/credential/path: keep it out of console/report.
                gate.fail('execution-error', f'{type(error).__name__}: check prerequisites and private diagnostic file.')
                (out / ('error-' + category + '.txt')).write_text(str(error) + '\n')
            gate.completed.append(category)
            failures = sum(r['category']==category and r['status']=='FAIL' for r in gate.findings)
            warnings = sum(r['category']==category and r['status']=='WARNING' for r in gate.findings)
            print(f'{CATEGORIES[category]}: {"FAIL" if failures else "WARNING" if warnings else "PASS"} ({failures} failures, {warnings} warnings)', flush=True)
        if 'secrets' in selected:
            print('Inspecting generated diagnostics for private information', flush=True)
            try:
                source.evidence_privacy(gate)
            except Exception as error:
                gate.category = 'secrets'
                gate.fail('diagnostic-scan-error', f'{type(error).__name__}: generated diagnostics were not fully inspected.')
    except KeyboardInterrupt:
        gate.fail('interrupted', 'Run interrupted; incomplete categories cannot pass.')
    finally:
        try:
            gate.assert_source_unchanged()
        except Exception:
            gate.category = 'hygiene'
            gate.fail('source-changed', 'Source checkout changed during the run; results cannot qualify this revision.')
        result = gate.report(selected)
    # A partial run reports full readiness FAIL, but has useful per-group exit semantics.
    if args.only:
        return 1 if any(r['status']=='FAIL' for r in gate.findings) or any(c not in gate.completed for c in selected) else 0
    return result


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(f'ANDROID F-DROID RELEASE CHECK: FAIL ({type(error).__name__}; initialization failed)', file=sys.stderr)
        sys.exit(2)
