#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Phone geometry/picker behavior; optional actual Android/Qt/AndroidX API compilation."""
from pathlib import Path
import argparse
import subprocess
import tempfile
import re
ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--android-jar', type=Path)
parser.add_argument('--qt-jar', type=Path)
parser.add_argument('--webkit-jar', type=Path)
parser.add_argument('--core-jar', type=Path)
parser.add_argument('--common-web-preview', type=Path, help='explicit read-only Android parent prerequisite before propagation')
parser.add_argument('--expected-common-sha', help='full Git SHA for that clean prerequisite checkout')
args = parser.parse_args()
web_source = ROOT / 'android/common/web/java'
if args.common_web_preview or args.expected_common_sha:
    if not args.common_web_preview or not re.fullmatch('[0-9a-f]{40}', args.expected_common_sha or ''):
        parser.error('common preview requires its path and exact full Git SHA')
    preview = args.common_web_preview.resolve()
    actual = subprocess.check_output(['git', '-C', str(preview), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(preview), 'status', '--porcelain'], text=True).strip()
    if actual != args.expected_common_sha or dirty:
        parser.error('common preview is dirty or does not match the explicit SHA')
    web_source = preview / 'android/common/web/java'
    if not web_source.is_dir():
        parser.error('common preview has no production Web source directory')
with tempfile.TemporaryDirectory(prefix='phone-embedded-web-') as stage:
    sources = [ROOT / f'android/phone/apps/phoneInterface/src/main/java/org/overte/phone/{name}.java'
               for name in ('PhoneWebGeometry',)]
    sources += [ROOT / f'android/phone/tests/instrumentation/{name}HostTest.java'
                for name in ('PhoneWebGeometry',)]
    subprocess.run(['javac', '-d', stage, *map(str, sources)], check=True)
    for name in ('PhoneWebGeometry',):
        subprocess.run(['java', '-cp', stage, f'org.overte.phone.{name}HostTest'], check=True)
    snapshot = Path(stage) / 'snapshot-host'
    snapshot.mkdir()
    host_sources = list((ROOT / 'android/phone/tests/instrumentation/snapshot').rglob('*.java'))
    host_sources += [ROOT / 'android/phone/apps/phoneInterface/src/main/java/org/overte/phone/PhoneSnapshotHost.java',
                     ROOT / 'android/common/snapshot/java/org/overte/snapshot/SnapshotHost.java',
                     ROOT / 'android/phone/apps/phoneInterface/src/main/java/org/overte/phone/PhoneDocumentsHost.java',
                     ROOT / 'android/common/documents/java/org/overte/documents/DocumentHost.java']
    subprocess.run(['javac', '-d', str(snapshot), *map(str, host_sources)], check=True)
    subprocess.run(['java', '-cp', str(snapshot), 'org.overte.phone.PhoneSnapshotHostTest'], check=True)
    subprocess.run(['java', '-cp', str(snapshot), 'org.overte.phone.PhoneDocumentsHostTest'], check=True)
    artifacts = [args.android_jar, args.qt_jar, args.webkit_jar, args.core_jar]
    if any(artifacts):
        if not all(path and path.is_file() for path in artifacts):
            parser.error('API compilation requires all four actual artifact paths')
        # Compile PhoneEmbeddedWebHost, PhoneSnapshotHost, PhoneDocumentsHost and PhoneInterfaceActivity with production Qt
        # bindings and common runtime. PermissionsActivity alone needs generated APK R.
        production = list((ROOT / 'android/phone/apps/phoneInterface/src/main/java').rglob('*.java'))
        production = [path for path in production if path.name != 'PermissionsActivity.java']
        production += list((ROOT / 'android/common/libraries/qt/src/main/java').rglob('*.java'))
        production += list(web_source.rglob('*.java'))
        production += list((ROOT / 'android/common/snapshot/java').rglob('*.java'))
        production += list((ROOT / 'android/common/documents/java').rglob('*.java'))
        production += list((ROOT / 'security/redaction/java').rglob('*.java'))
        subprocess.run(['javac', '-classpath', ':'.join(map(str, artifacts)), '-d', stage,
                        *map(str, production)], check=True)
        print('PASS: production Phone Activity/Host, Qt bindings and common Web/Snapshot/Documents compile against actual SDK artifacts')
