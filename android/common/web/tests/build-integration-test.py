#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Configure the production adapters after the applications' plain link calls.

Qt targets are configuration substitutes. This checks real CMake integration,
not C++ compilation, Android linking or device behavior.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
ADAPTERS = (('web', 'embedded_web'), ('snapshot', 'snapshot'),
            ('documents', 'documents'))

with tempfile.TemporaryDirectory(prefix='overte-android-adapter-configure-') as tmp:
    stage = Path(tmp)
    (stage / 'main.cpp').write_text('int main() { return 0; }\n')
    lines = ['cmake_minimum_required(VERSION 3.17)',
             'project(AndroidAdapterLinkIntegration LANGUAGES CXX)']
    for name in ('Quick', 'WebChannel', 'Network', 'Core', 'Qml'):
        lines.append(f'add_library(Qt5::{name} INTERFACE IMPORTED)')
    lines.append('add_library(ui INTERFACE)')
    for folder, _ in ADAPTERS:
        path = (ROOT / 'android/common' / folder / 'target.cmake').as_posix()
        lines.append(f'include("{path}")')
    for application in ('phoneInterface', 'picoInterface'):
        lines += [f'add_executable({application} main.cpp)',
                  f'target_link_libraries({application} Qt5::Core)']
        for _, helper in ADAPTERS:
            lines.append(f'overte_target_{helper}({application})')
        lines.append(f'target_link_libraries({application} Qt5::Quick)')
    (stage / 'CMakeLists.txt').write_text('\n'.join(lines) + '\n')
    subprocess.run(['cmake', '-S', str(stage), '-B', str(stage / 'build')],
                   check=True)
print('Actual CMake configured all three adapters for both application targets')
