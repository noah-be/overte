#!/usr/bin/env python3
"""Compile the actual native provider copy core; UIKit/SDK remains separate."""
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
with tempfile.TemporaryDirectory(prefix='ios-document-import-') as temporary:
    binary=Path(temporary)/'test'
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-fPIC','-pthread',
        '-I'+str(ROOT),str(Path(__file__).with_suffix('.cpp')),'-o',str(binary),*flags],check=True,timeout=60)
    subprocess.run([str(binary)],check=True,timeout=60)
