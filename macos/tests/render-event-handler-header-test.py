#!/usr/bin/env python3
"""Verify that RenderEventHandler.h is a self-contained public header."""

from pathlib import Path
import os
import shlex
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "interface/src/graphics/RenderEventHandler.h"
source = HEADER.read_text(encoding="utf-8")

# These declarations must not depend on QEvent/QElapsedTimer or another
# translation unit having included their definitions first. QObject also
# supplies the complete QString API expanded by Q_OBJECT on Qt 5.
for required_include in ("<atomic>", "<QObject>"):
    if f"#include {required_include}" not in source:
        raise SystemExit(f"RenderEventHandler.h must include {required_include} directly")

# Compile the header as the first include whenever a host Qt development
# package is available. The static checks above still protect cross builds
# whose Qt package is only available inside their target toolchain.
pkg_config = shutil.which("pkg-config")
compiler = os.environ.get("CXX") or shutil.which("c++")
qt_package = None
if pkg_config and compiler:
    for candidate in ("Qt5Core", "Qt6Core"):
        if subprocess.run(
            [pkg_config, "--exists", candidate], check=False
        ).returncode == 0:
            qt_package = candidate
            break

if qt_package:
    flags = shlex.split(subprocess.check_output(
        [pkg_config, "--cflags", qt_package], text=True
    ))
    translation_unit = '#include "interface/src/graphics/RenderEventHandler.h"\n'
    subprocess.run(
        [compiler, "-x", "c++", "-std=c++17", "-fsyntax-only", *flags,
         f"-I{ROOT}", "-"],
        input=translation_unit,
        text=True,
        check=True,
    )

print("RenderEventHandler header contract valid")
