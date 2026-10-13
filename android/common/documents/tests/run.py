#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Compiled document copy behavior; optional real Qt helper/JVM/JNI and Android API checks."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
MODULE=Path(__file__).resolve().parents[1]
ROOT=MODULE.parents[2]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--android-jar',type=Path)
p.add_argument('--native',action='store_true')
p.add_argument('--qt-root',type=Path)
p.add_argument('--helper-root',type=Path,default=ROOT)
p.add_argument('--jdk',type=Path,default=Path(os.environ.get('JAVA_HOME','/usr/lib/jvm/temurin-21-jdk')))
a=p.parse_args()
with tempfile.TemporaryDirectory(prefix='overte-documents-') as temporary:
    stage=Path(temporary)
    subprocess.run(['javac','-d',str(stage),str(MODULE/'java/org/overte/documents/DocumentCopy.java'),
                    str(MODULE/'java/org/overte/documents/DocumentTree.java'),
                    *map(str,(MODULE/'tests/java').rglob('*.java'))],check=True)
    subprocess.run(['java','-cp',str(stage),'org.overte.documents.DocumentCopyTest'],check=True)
    subprocess.run(['java','-cp',str(stage),'org.overte.documents.DocumentTreeTest'],check=True)
    if a.android_jar:
        subprocess.run(['javac','-cp',str(a.android_jar),'-d',str(stage),
                        *map(str,(MODULE/'java').rglob('*.java')),
                        str(ROOT/'android/common/web/java/org/overte/web/WebFilePickerState.java')],check=True)
    if a.native:
        environment=dict(os.environ)
        if a.qt_root:
            environment.update(PKG_CONFIG_PATH=str(a.qt_root/'usr/lib64/pkgconfig'),PKG_CONFIG_SYSROOT_DIR=str(a.qt_root),
                LD_LIBRARY_PATH=str(a.qt_root/'usr/lib64'),QT_PLUGIN_PATH=str(a.qt_root/'usr/lib64/qt5/plugins'))
            qt_tools=a.qt_root/'usr/lib64/qt5/bin'
        else: qt_tools=Path(subprocess.check_output(['pkg-config','--variable=host_bins','Qt5Core'],text=True).strip())
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt5Widgets'],env=environment,text=True))
        if a.qt_root:flags.insert(0,'-L'+str(a.qt_root/'usr/lib64'))
        ui=a.helper_root/'libraries/ui/src';moc=stage/'moc.cpp'
        subprocess.run([str(qt_tools/'moc'),str(ui/'FileDialogHelper.h'),'-o',str(moc)],check=True)
        jvm=a.jdk/'lib/server';binary=stage/'native'
        subprocess.run(['c++','-std=c++17','-fPIC','-UNDEBUG',str(MODULE/'src/NativeDocumentPicker.cpp'),
                        str(MODULE/'tests/native.cpp'),str(ui/'FileDialogHelper.cpp'),str(ui/'ui/Logging.cpp'),str(moc),
                        '-I'+str(ui),'-I'+str(a.jdk/'include'),'-I'+str(a.jdk/'include/linux'),
                        '-L'+str(jvm),'-Wl,-rpath,'+str(jvm),'-ljvm','-pthread','-o',str(binary),*flags],env=environment,check=True)
        environment['QT_QPA_PLATFORM']='offscreen'
        subprocess.run([str(binary),str(stage)],env=environment,check=True)
