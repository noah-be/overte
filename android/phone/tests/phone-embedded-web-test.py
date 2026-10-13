#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Phone geometry/picker behavior; optional actual Android/Qt/AndroidX API compilation."""
from pathlib import Path
import argparse
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--android-jar', type=Path)
parser.add_argument('--qt-jar', type=Path)
parser.add_argument('--webkit-jar', type=Path)
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix='phone-embedded-web-') as stage:
    sources = [ROOT / f'android/phone/apps/phoneInterface/src/main/java/org/overte/phone/{name}.java'
               for name in ('PhoneWebGeometry',)]
    sources += [ROOT / f'android/phone/tests/instrumentation/{name}HostTest.java'
                for name in ('PhoneWebGeometry',)]
    subprocess.run(['javac', '-d', stage, *map(str, sources)], check=True)
    for name in ('PhoneWebGeometry',):
        subprocess.run(['java', '-cp', stage, f'org.overte.phone.{name}HostTest'], check=True)
    artifacts = [args.android_jar, args.qt_jar, args.webkit_jar]
    if any(artifacts):
        if not all(path and path.is_file() for path in artifacts):
            parser.error('API compilation requires all three actual artifact paths')
        # Compile PhoneEmbeddedWebHost and PhoneInterfaceActivity with production Qt
        # bindings and common runtime. PermissionsActivity alone needs generated APK R.
        production = list((ROOT / 'android/phone/apps/phoneInterface/src/main/java').rglob('*.java'))
        production = [path for path in production if path.name != 'PermissionsActivity.java']
        production += list((ROOT / 'android/common/libraries/qt/src/main/java').rglob('*.java'))
        production += list((ROOT / 'android/common/web/java').rglob('*.java'))
        production += list((ROOT / 'security/redaction/java').rglob('*.java'))
        subprocess.run(['javac', '-classpath', ':'.join(map(str, artifacts)), '-d', stage,
                        *map(str, production)], check=True)
        print('PASS: production Phone Activity/Host, Qt bindings and common Web compile against actual SDK artifacts')
