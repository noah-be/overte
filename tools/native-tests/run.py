#!/usr/bin/env python3
"""Build only selected native targets, then run exactly the selected CTest names."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time


def run(build, selection, jobs):
    for report in (build / 'native-result.json', build / 'native-ctest.xml',
                   build / 'Testing/Temporary/LastTest.log'):
        report.unlink(missing_ok=True)
    for report in (build / 'native-results').glob('*.xml'):
        report.unlink()
    result = json.loads(selection.read_text())
    targets, tests = result['targets'], result['tests']
    for names in (targets, tests):
        if not names or len(names) != len(set(names)) or any(not re.fullmatch(r'[A-Za-z0-9_-]+', name) for name in names):
            raise ValueError('invalid native selection')
    pattern = '^(' + '|'.join(re.escape(name) for name in tests) + ')$'
    listing = json.loads(subprocess.check_output(['ctest', '--test-dir', str(build), '-R', pattern,
                                                  '--show-only=json-v1'], text=True))
    if {entry['name'] for entry in listing['tests']} != set(tests):
        raise ValueError('selected CTest set differs from registered tests')
    started = time.monotonic()
    subprocess.run(['cmake', '--build', str(build), '--parallel', str(jobs), '--target', *targets], check=True)
    built = time.monotonic()
    subprocess.run(['ctest', '--test-dir', str(build), '-R', pattern, '--parallel', '2',
                    '--timeout', '120', '--output-on-failure', '--no-tests=error',
                    '--output-junit', str(build.resolve() / 'native-ctest.xml')], check=True)
    result['build_seconds'] = built - started
    result['test_seconds'] = time.monotonic() - built
    result['status'] = 'PASS'
    (build / 'native-result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2, choices=range(1, 9))
    args = parser.parse_args()
    (args.build / 'native-result.json').unlink(missing_ok=True)
    run(args.build, args.selection, args.jobs)
