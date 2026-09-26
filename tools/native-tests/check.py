#!/usr/bin/env python3
"""Select native checks from the exact candidate and aggregate without silent skips."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
# Explicitly host-owned paths. Unknown paths are deliberately NOT cheap by default.
HOST_ROOTS = ('docs/', 'scripts/', 'unpublishedScripts/', 'server-console/',
              'tests/device/', 'tests/javascript/', 'tests/mocha/', 'tests/performance/',
              'provenance/', 'ios/', 'android/', 'launchers/', 'pkg-scripts/')
HOST_TOOLS = ('branch-', 'repository-', 'sync-test-reuse/', 'workflow-security/',
              'issue-intake/', 'dependency-releases/', 'release/', 'sbom/',
              'ios-build-qualification/')
CORE_ROOTS = ('tests/shared/',)
RUNTIME_ASSETS = {'.qml', '.js', '.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif',
                  '.wav', '.mp3', '.ogg', '.html', '.css'}


def plan(paths: list[str], regular: bool = True, *, verified_empty: bool = False) -> dict:
    if verified_empty:
        if paths:
            raise ValueError('verified empty delta contains paths')
        return {'mode': 'skip', 'paths': [], 'reasons': ['verified empty candidate delta']}
    reasons, relevant = [], []
    core_only = set()
    for path in paths:
        if (not isinstance(path, str) or not path or '\x00' in path or '\\' in path
                or PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts):
            raise ValueError('invalid changed path')
        if path.endswith('.md'):
            continue
        # Routing/runner changes need an actual small native smoke plus their
        # host regressions, not a rebuild of unrelated product applications.
        if path in ('tools/native-tests/check.py', 'tools/native-tests/select.py',
                    'tools/native-tests/run.py', 'tools/native-tests/qt-test.py', 'tests/native-ci-test.py'):
            relevant.append(path)
            core_only.add(path)
            continue
        # Build definitions take precedence even inside otherwise cheap directories.
        name = PurePosixPath(path).name
        if (name == 'CMakeLists.txt' or path.endswith(('.cmake', '.qrc'))
                or path in ('conanfile.py', 'conan.lock', '.gitmodules', '.github/native-tests.json')
                or path.startswith(('tools/native-tests/', 'tests/native-', 'cmake/',
                                        '.github/workflows/native-', '.github/actions/conan-install/'))):
            relevant.append(path)
        elif path.startswith('interface/resources/') and PurePosixPath(path).suffix.lower() in RUNTIME_ASSETS:
            # Native core tests do not exercise UI/media content. Host QML/JS
            # checks and device journeys own it; changed QRC definitions above
            # still require validating the native resource build.
            continue
        elif path.startswith(HOST_ROOTS):
            continue
        elif path.startswith('tools/') and path[6:].startswith(HOST_TOOLS):
            continue
        elif path.startswith('tests/') and path.endswith(('.py', '.json', '.js', '.sh', '.qml')):
            continue
        elif path.startswith('.github/'):
            continue
        elif path in ('LICENSE', 'COPYING', '.gitignore', '.gitattributes', 'requirements.txt'):
            continue
        else:
            relevant.append(path)
    if not regular:
        reasons.append('non-regular file change; broad validation required')
    if not paths:
        reasons.append('no trustworthy change inventory; broad validation required')
    mode = 'full' if reasons else 'skip'
    if relevant:
        # Shared is the first bounded, dependency-light native component lane.
        # Other C++ areas retain the full dependency graph and target selection.
        mode = 'core' if all((p in core_only or p.startswith(CORE_ROOTS)) and PurePosixPath(p).name != 'CMakeLists.txt'
                             for p in relevant) and not reasons else 'full'
        reasons.append('native inputs changed')
    return {'mode': mode, 'paths': relevant, 'force_broad': not regular or not paths,
            'reasons': reasons or ['host-only changes']}


def candidate_changes(candidate: Path, event: dict, sha: str):
    spec = importlib.util.spec_from_file_location('repository_checks', ROOT / 'tools/repository-checks/check.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.changed_paths(candidate, event, sha, allow_executable=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    route = commands.add_parser('plan')
    route.add_argument('--candidate', type=Path, required=True)
    route.add_argument('--event', type=Path, required=True)
    route.add_argument('--sha', required=True)
    route.add_argument('--output', type=Path)
    route.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'plan':
            event = json.loads(args.event.read_text())
            paths, regular = candidate_changes(args.candidate, event, args.sha)
            result = plan(paths, regular, verified_empty=isinstance(event.get('pull_request'), dict) and not paths)
            result['sha'] = args.sha
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2) + '\n')
            if args.output:
                with args.output.open('a') as stream:
                    stream.write(f"mode={result['mode']}\n")
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print(f'Native checks failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
