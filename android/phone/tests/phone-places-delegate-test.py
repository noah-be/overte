#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Run actual selected Places delegates; capture Qt output without treating warnings as PASS."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runner', default=os.environ.get('OVERTE_QML_TEST_RUNNER', 'qmltestrunner'))
parser.add_argument('--junit', type=Path)
parser.add_argument('--places-qml', type=Path, help='Explicit mutated production input for negative controls only')
parser.add_argument('--login-qml', type=Path, help='Explicit mutated Phone login input for negative controls only')
selection = parser.add_mutually_exclusive_group()
selection.add_argument('--places-only', action='store_true', help='Places-only Qt6/negative probe; normal Fast executes both Phone fixtures with Qt5')
selection.add_argument('--domain-only', action='store_true', help='Isolated domain-handler negative/positive probe; normal Fast executes both')
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix='phone-places-delegates-') as directory:
    stage = Path(directory)
    production = stage / 'production'
    production.mkdir()
    shutil.copy2(args.places_qml or ROOT / 'scripts/system/places/PicoPlaces.qml', production / 'PicoPlaces.qml')
    controls = stage / 'controlsUit'
    controls.mkdir()
    types = ('TouchUiMetrics', 'TouchUiProfile', 'TouchUiProfileBase')
    (controls / 'qmldir').write_text('module controlsUit\n' + ''.join(f'{name} 1.0 {name}.qml\n' for name in types))
    for name in types:
        shutil.copy2(ROOT / f'interface/resources/qml/controlsUit/{name}.qml', controls)
    fixture = stage / 'tst_phone_places_delegates.qml'
    if not args.domain_only:
        shutil.copy2(Path(__file__).with_name('qml') / fixture.name, fixture)
    if not args.places_only:
        shutil.copy2(args.login_qml or ROOT / 'interface/resources/qml/LoginDialog/+android_phoneInterface/LinkAccountBody.qml',
                     production / 'PhoneLoginBody.qml')
        shutil.copy2(Path(__file__).with_name('qml') / 'tst_phone_login_domain.qml', stage)
        # Preserve the existing shared suite's explicit UI-control boundaries;
        # the production login body, its signal handlers and metrics stay real.
        with (controls / 'qmldir').open('a') as module:
            for name in ('Button', 'TextField'):
                module.write(f'{name} 1.0 {name}.qml\n')
                shutil.copy2(ROOT / f'android/common/tests/qml/imports/controlsUit/{name}.qml', controls)
    report = args.junit or stage / 'results.xml'
    result = subprocess.run([args.runner, '-import', str(stage),
                             '-import', str(ROOT / 'android/common/tests/qml/imports'), '-input', str(stage),
                             '-o', '-,txt', '-o', str(report) + ',junitxml'],
                            env=os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software'},
                            timeout=90, check=False)
    # Qt may return zero while JUnit records runtime errors/warnings. Retain the
    # untouched report and reject that discrepancy, empty tests and skipped cases.
    try:
        root = ET.parse(report).getroot()
        cases = root.findall('testcase')
        expected = 5 if args.places_only or args.domain_only else 10
        valid = (root.tag == 'testsuite' and len(cases) == expected
                 and int(root.get('tests', '-1')) == len(cases)
                 and all(int(root.get(key, '0')) == 0 for key in ('errors', 'failures', 'skipped'))
                 and all(case.get('result', 'pass') == 'pass' for case in cases)
                 and not any(root.findall('.//' + tag) for tag in ('error', 'failure', 'skipped')))
    except (ET.ParseError, OSError, ValueError):
        valid = False
    raise SystemExit(result.returncode or (0 if valid else 1))
