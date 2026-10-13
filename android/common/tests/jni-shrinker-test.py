#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Optimize actual common Java with R8 and verify every C++ JNI method descriptor."""
import argparse
from pathlib import Path
import re
import shutil
import zipfile
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--r8-jar',type=Path,required=True)
p.add_argument('--android-jar',type=Path,required=True)
p.add_argument('--webkit-jar',type=Path,required=True)
p.add_argument('--core-jar',type=Path,required=True)
p.add_argument('--annotation-jar',type=Path,required=True)
p.add_argument('--java-home',type=Path,default=Path(shutil.which('javac')).resolve().parents[1])
a=p.parse_args()
modules={'web':('org.overte.web.EmbeddedWebView','NativeWebViewItem.cpp'),
         'snapshot':('org.overte.snapshot.SnapshotAdapter','NativeSnapshotAdapter.cpp'),
         'documents':('org.overte.documents.DocumentAdapter','NativeDocumentPicker.cpp')}
libraries=[a.android_jar,a.webkit_jar,a.core_jar,a.annotation_jar]
with tempfile.TemporaryDirectory(prefix='overte-jni-r8-') as temporary:
    stage=Path(temporary);classes=stage/'classes';classes.mkdir()
    sources=[path for name in modules for path in (ROOT/'android/common'/name/'java').rglob('*.java')]
    subprocess.run(['javac','--release','8','-cp',':'.join(map(str,libraries)),'-d',str(classes),*map(str,sources)],check=True)
    program=stage/'input.jar';output=stage/'optimized.jar'
    subprocess.run(['jar','cf',str(program),'-C',str(classes),'.'],check=True)
    # JVM classfile output retains invokedynamic; Android's API stub intentionally
    # omits LambdaMetafactory. Supply its actual JDK declaration, not a fake stub.
    lambda_library=stage/'jdk-lambda.jar'
    with zipfile.ZipFile(a.java_home/'jmods/java.base.jmod') as runtime, zipfile.ZipFile(lambda_library,'w') as library:
        name='java/lang/invoke/LambdaMetafactory.class'
        library.writestr(name,runtime.read('classes/'+name))
    libraries.append(lambda_library)
    command=['java','-cp',str(a.r8_jar),'com.android.tools.r8.R8','--release','--classfile','--output',str(output)]
    for library in libraries:command += ['--lib',str(library)]
    control=stage/'unprotected.jar'
    unprotected_command=command.copy()
    unprotected_command[unprotected_command.index('--output')+1]=str(control)
    subprocess.run([*unprotected_command,str(program)],check=True)
    with zipfile.ZipFile(control) as unprotected:
        if any(name.replace('.','/')+'.class' in unprotected.namelist() for name,_ in modules.values()):
            raise AssertionError('negative control unexpectedly retains a JNI endpoint without keep rules')
    for module in modules:command += ['--pg-conf',str(ROOT/'android/common'/module/'proguard-rules.pro')]
    subprocess.run([*command,str(program)],check=True)
    checked=0
    for module,(name,source) in modules.items():
        native=(ROOT/'android/common'/module/'src'/source).read_text()
        required=set(re.findall(r'call\("([A-Za-z0-9_]+)",\s*"([^"\n]+)"',native))
        text=subprocess.check_output(['javap','-p','-s','-classpath',str(output),name],text=True)
        retained=set(re.findall(r'([A-Za-z0-9_]+)\([^;\n]*\);\s*descriptor: (\S+)',text))
        missing=required-retained
        if missing:raise AssertionError(f'{name}: lost or renamed JNI descriptors {sorted(missing)}')
        # Java-to-native methods also keep the spelling used by exported JNI symbols.
        exports=set(re.findall('Java_'+name.replace('.','_')+r'_([A-Za-z0-9_]+)\(',native))
        original=subprocess.check_output(['javap','-p','-s','-classpath',str(program),name],text=True)
        original_methods=set(re.findall(r'([A-Za-z0-9_]+)\([^;\n]*\);\s*descriptor: (\S+)',original))
        callbacks={pair for pair in original_methods if pair[0] in exports}
        if callbacks-retained:raise AssertionError(f'{name}: lost native callback descriptors {sorted(callbacks-retained)}')
        checked += len(required)+len(exports)
    print(f'PASS: actual R8 optimized production Java retains {checked} C++ JNI lookups/callbacks; classfile host output, no APK qualification')
