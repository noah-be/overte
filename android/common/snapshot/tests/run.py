#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Compiled portable export policies; optional actual Qt/QML/JVM/JNI and SDK API checks."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

MODULE = Path(__file__).resolve().parents[1]
ROOT = MODULE.parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native', action='store_true')
parser.add_argument('--qt-root', type=Path)
parser.add_argument('--storage-include', type=Path, default=ROOT / 'interface/src/ui')
parser.add_argument('--jdk', type=Path, default=Path(os.environ.get('JAVA_HOME', '/usr/lib/jvm/temurin-21-jdk')))
parser.add_argument('--android-jar', type=Path)
parser.add_argument('--core-jar', type=Path)
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix='overte-snapshot-') as temporary:
    stage = Path(temporary)
    sources = [MODULE / f'java/org/overte/snapshot/{name}.java' for name in ('SnapshotFilePolicy', 'SnapshotCopy', 'SnapshotLease')]
    sources += list((MODULE / 'tests/java').rglob('*.java'))
    subprocess.run(['javac', '-d', str(stage), *map(str, sources)], check=True)
    subprocess.run(['java', '-cp', str(stage), 'org.overte.snapshot.SnapshotPolicyTest'], check=True)
    if args.android_jar or args.core_jar:
        if not args.android_jar or not args.core_jar:
            parser.error('both actual Android SDK and AndroidX Core artifacts are required')
        sources = list((MODULE / 'java').rglob('*.java'))
        sources += [ROOT / 'android/common/web/java/org/overte/web/WebFilePickerState.java']
        subprocess.run(['javac', '-cp', str(args.android_jar) + os.pathsep + str(args.core_jar),
                        '-d', str(stage), *map(str, sources)], check=True)
    if args.native:
        environment = dict(os.environ)
        if args.qt_root:
            environment.update(PKG_CONFIG_PATH=str(args.qt_root / 'usr/lib64/pkgconfig'),
                               PKG_CONFIG_SYSROOT_DIR=str(args.qt_root),
                               LD_LIBRARY_PATH=str(args.qt_root / 'usr/lib64'),
                               QML2_IMPORT_PATH=str(args.qt_root / 'usr/lib64/qt5/qml'),
                               QT_PLUGIN_PATH=str(args.qt_root / 'usr/lib64/qt5/plugins'))
            qt_tools = args.qt_root / 'usr/lib64/qt5/bin'
        else:
            qt_tools = Path(subprocess.check_output(['pkg-config', '--variable=host_bins', 'Qt5Core'], text=True).strip())
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt5Quick'], env=environment, text=True))
        if args.qt_root:
            flags.insert(0, '-L' + str(args.qt_root / 'usr/lib64'))
        moc = stage / 'moc.cpp'
        subprocess.run([str(qt_tools / 'moc'), str(MODULE / 'src/NativeSnapshotAdapter.h'), '-o', str(moc)], check=True)
        binary = stage / 'native'
        jvm = args.jdk / 'lib/server'
        subprocess.run(['c++', '-std=c++17', '-fPIC', '-UNDEBUG', str(MODULE / 'src/NativeSnapshotAdapter.cpp'),
                        str(MODULE / 'tests/native.cpp'), str(moc), '-I' + str(MODULE / 'src'),
                        '-I' + str(args.storage_include), '-I' + str(args.jdk / 'include'), '-I' + str(args.jdk / 'include/linux'),
                        '-L' + str(jvm), '-Wl,-rpath,' + str(jvm), '-ljvm', '-pthread', '-o', str(binary), *flags],
                       env=environment, check=True)
        environment['QT_QPA_PLATFORM'] = 'offscreen'
        subprocess.run([str(binary), str(stage), str(ROOT / 'interface/resources/qml/controls/+android/SnapshotPlatformBackend.qml')],
                       env=environment, check=True)
