#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Portable policies/DOM tests; opt-in actual Qt/JNI/Android API compilation."""
import argparse
import os
import signal
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--native', action='store_true')
parser.add_argument('--reproduce-old-hide', action='store_true', help='negative actual Qt/JNI active-only hide regression')
parser.add_argument('--qt-root', type=Path, help='optional Qt sysroot containing usr/include and usr/lib64')
parser.add_argument('--policy-include', type=Path, default=ROOT / 'libraries/shared/src')
parser.add_argument('--android-jar', type=Path)
parser.add_argument('--webkit-jar', type=Path)
parser.add_argument('--jdk', type=Path, default=Path(os.environ.get('JAVA_HOME', '/usr/lib/jvm/temurin-21-jdk')))
args = parser.parse_args()
subprocess.run([sys.executable, str(WEB / 'tests/test_network_policy.py')], check=True)
subprocess.run([sys.executable, str(WEB / 'tests/build-integration-test.py')], check=True)
subprocess.run([sys.executable, str(WEB / 'tests/audio-mutations.py')], check=True)
with tempfile.TemporaryDirectory(prefix='overte-embedded-web-') as temporary:
    stage = Path(temporary)
    subprocess.run(['javac', '-d', str(stage),
        str(WEB / 'java/org/overte/web/WebInputGate.java'),
        str(WEB / 'java/org/overte/web/WebAudioLifecycle.java'),
        str(WEB / 'java/org/overte/web/WebLifecycleDispatch.java'),
        str(WEB / 'java/org/overte/web/WebNavigationArchive.java'),
        str(WEB / 'tests/java/org/overte/web/WebAudioLifecycleTest.java'),
        str(WEB / 'tests/java/org/overte/web/WebLifecycleBoundary.java'),
        str(WEB / 'java/org/overte/web/WebDocumentState.java'),
        str(WEB / 'java/org/overte/web/WebFileChoiceLease.java'),
        str(WEB / 'java/org/overte/web/WebTextureScale.java'),
        str(WEB / 'java/org/overte/web/WebFilePickerState.java'),
        str(WEB / 'java/org/overte/web/WebPointerState.java'),
        str(WEB / 'java/org/overte/web/WebFrameGate.java'),
        str(WEB / 'java/org/overte/web/WebFramePixels.java'),
        str(WEB / 'tests/java/org/overte/web/WebLifetimeTest.java'),
        str(WEB / 'tests/java/org/overte/web/WebFrameTest.java')], check=True)
    subprocess.run(['java', '-cp', str(stage), 'org.overte.web.WebLifetimeTest'], check=True)
    subprocess.run(['java', '-cp', str(stage), 'org.overte.web.WebAudioLifecycleTest'], check=True)
    subprocess.run(['java', '-cp', str(stage), 'org.overte.web.WebFrameTest'], check=True)
    if args.android_jar or args.webkit_jar:
        if not args.android_jar or not args.webkit_jar:
            parser.error('--android-jar and --webkit-jar must be supplied together')
        subprocess.run(['javac', '-cp', str(args.android_jar) + os.pathsep + str(args.webkit_jar),
            '-d', str(stage), *map(str, sorted((WEB / 'java/org/overte/web').glob('*.java')))], check=True)
    channel = None
    if args.native:
        environment = dict(os.environ)
        if args.qt_root:
            environment['PKG_CONFIG_PATH'] = str(args.qt_root / 'usr/lib64/pkgconfig')
            environment['PKG_CONFIG_SYSROOT_DIR'] = str(args.qt_root)
            environment['LD_LIBRARY_PATH'] = str(args.qt_root / 'usr/lib64') + os.pathsep + environment.get('LD_LIBRARY_PATH', '')
            environment['QML2_IMPORT_PATH'] = str(args.qt_root / 'usr/lib64/qt5/qml')
            environment['QT_PLUGIN_PATH'] = str(args.qt_root / 'usr/lib64/qt5/plugins')
            qt_tools = args.qt_root / 'usr/lib64/qt5/bin'
        else:
            qt_tools = Path(subprocess.check_output(['pkg-config', '--variable=host_bins', 'Qt5Core'], text=True).strip())
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs',
            'Qt5Quick', 'Qt5WebChannel', 'Qt5Network'], env=environment, text=True))
        if args.qt_root:
            flags.insert(0, '-L' + str(args.qt_root / 'usr/lib64'))
        moc = stage / 'moc.cpp'
        resources = stage / 'resources.cpp'
        subprocess.run([str(qt_tools / 'moc'), str(WEB / 'src/NativeWebViewItem.h'), '-o', str(moc)], check=True)
        subprocess.run([str(qt_tools / 'rcc'), str(WEB / 'embedded-web.qrc'), '-o', str(resources)], check=True)
        binary = stage / 'native'
        subprocess.run(['c++', '-std=c++17', '-fPIC', '-UNDEBUG', str(WEB / 'src/NativeWebViewItem.cpp'),
            str(WEB / 'tests/native.cpp'), str(moc), str(resources), '-I' + str(WEB / 'src'),
            '-I' + str(args.policy_include), '-I' + str(args.jdk / 'include'), '-I' + str(args.jdk / 'include/linux'),
            '-L' + str(args.jdk / 'lib/server'), '-Wl,-rpath,' + str(args.jdk / 'lib/server'), '-ljvm', '-pthread', '-o', str(binary), *flags], env=environment, check=True)
        channel = stage / 'qwebchannel.js'
        environment['QT_QPA_PLATFORM'] = 'offscreen'
        command = [str(binary), str(channel), str(ROOT / 'interface/resources/qml/controls/+android/EmbeddedWebBackend.qml'), str(stage)]
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        subprocess.run(command, env=environment, check=True)
        if args.reproduce_old_hide:
            import resource
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            old = dict(environment, OVERTE_TEST_OLD_ACTIVE_VISIBILITY='1')
            failed = subprocess.run(command, env=old, capture_output=True, text=True)
            expected = 'field("hiddenRevision") == jlong(wire.lifecycleRevision()) && field("hiddenRevision") != jlong(before)'
            if (failed.returncode != -signal.SIGABRT or 'Assertion' not in failed.stderr
                    or expected not in failed.stderr or 'failed' not in failed.stderr):
                raise AssertionError('expected inactive-hide assertion was not observed: '
                    + str(failed.returncode) + '\n' + failed.stdout + failed.stderr)
            sys.stderr.write(failed.stderr)
            print('PASS: actual Qt/JNI original active-only hide comparison rejected by production-dispatch regression')
    subprocess.run(['node', str(WEB / 'tests/javascript.js'), *([str(channel)] if channel else [])], check=True)
