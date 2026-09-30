#!/usr/bin/env python3
"""Run a Qt test with isolated settings; skips and empty results are not success."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


def run(command, report):
    report = report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    report.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix='overte-native-') as temporary:
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', XDG_CONFIG_HOME=temporary,
                   XDG_CACHE_HOME=temporary, XDG_DATA_HOME=temporary, XDG_RUNTIME_DIR=temporary)
        result = subprocess.run([*command, '-o', str(report) + ',xml', '-o', '-,txt'], env=env)
    if result.returncode:
        return result.returncode
    document = ET.parse(report).getroot()
    incidents = document.findall('.//Incident')
    if not incidents or any(item.get('type') != 'pass' for item in incidents):
        raise ValueError('native test had no passing incidents, or reported failure/skip')
    actual = [fn for fn in document.findall('TestFunction') if fn.get('name') not in ('initTestCase', 'cleanupTestCase')]
    if not actual:
        raise ValueError('native test executed no test functions')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        if not command:
            raise ValueError('missing test executable')
        sys.exit(run(command, args.report))
    except (ValueError, OSError, ET.ParseError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
