#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Actual iOS copier/shared helper handoff and registration types, not UIKit compilation."""
from pathlib import Path
import os
import re
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Widgets'],text=True))
tools=Path(subprocess.check_output(['pkg-config','--variable=libexecdir','Qt6Core'],text=True).strip())
source=(ROOT/'ios/documents/IOSDocumentPicker.mm').read_text()
# Compile the original registrations against the owning in-tree header.
# The matching function definitions below replace UIKit/provider queues only.
declarations=[]
for name in ('open','openTree'):
    declaration=re.search(r'^bool '+name+r'\([^\n]+\) \{',source,re.M)
    assert declaration,name
    declarations.append(declaration[0][:-2]+';')
install=source[source.index('void install() {'):]
registrations=[line for line in install.splitlines()
    if line.strip().startswith(('static_assert(','FileDialogHelper::setDocument'))]
assert len(registrations)==7,registrations
with tempfile.TemporaryDirectory(prefix='ios-document-handoff-') as temporary:
    stage=Path(temporary)
    (stage/'picker-declarations.inc').write_text('\n'.join(declarations))
    (stage/'picker-registration.inc').write_text('\n'.join(registrations))
    subprocess.run([str(tools/'moc'),str(ROOT/'libraries/ui/src/FileDialogHelper.h'),
        '-o',str(stage/'moc.cpp')],check=True,timeout=30)
    binary=stage/'test'
    subprocess.run(['c++','-std=c++17','-fPIC','-UNDEBUG','-pthread',
        '-I'+str(ROOT),'-I'+str(ROOT/'libraries/ui/src'),'-I'+str(stage),
        str(Path(__file__).with_suffix('.cpp')),str(ROOT/'libraries/ui/src/FileDialogHelper.cpp'),
        str(ROOT/'libraries/ui/src/ui/Logging.cpp'),str(stage/'moc.cpp'),'-o',str(binary),*flags],
        check=True,timeout=90)
    subprocess.run([str(binary)],check=True,timeout=60,
        env=os.environ|{'QT_QPA_PLATFORM':'offscreen'})
