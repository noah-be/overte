#!/usr/bin/env python3
"""Build the small Tablet input extension against the reviewed Qt 5.15.3 SDK.

Downloads and extracts official packages into an isolated build directory; never
installs packages or replaces the host Qt. Runtime libraries come from the chosen
native worker distribution, so no second Qt runtime is loaded into Interface.
"""
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import struct
import tempfile
import selectors
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'browser-client/native-input'
PACKAGES = {
    'pool/universe/q/qtbase-opensource-src/qtbase5-dev_5.15.3+dfsg-2_amd64.deb': 'ca142897120402f6d83951dd9c6f8f30318ccad8e3490490f3e9476d8049078e',
    'pool/universe/q/qtbase-opensource-src/qtbase5-dev-tools_5.15.3+dfsg-2_amd64.deb': '6d530acbd9a8b54353b5dca05d1b956b26db2c5b5d942f9f112a5153a8da49d5',
    'pool/universe/q/qtdeclarative-opensource-src/qtdeclarative5-dev_5.15.3+dfsg-1_amd64.deb': '1ae3a692291438f4ec9449750c07c043c1c715d833357c019330206388380199',
}
BASE = 'https://archive.ubuntu.com/ubuntu/'


def run(arguments, **options):
    subprocess.run([str(argument) for argument in arguments], check=True, **options)


def build(output, runtime):
    # Check the loaded runtime itself, not filenames which could be aliases.
    version_probe = 'import ctypes,sys; library=ctypes.CDLL(sys.argv[1]); library.qVersion.restype=ctypes.c_char_p; print(library.qVersion().decode("ascii"))'
    runtime_version = subprocess.check_output([sys.executable, '-c', version_probe, str(runtime / 'libQt5Core.so.5')],
        env={**os.environ, 'LD_LIBRARY_PATH': str(runtime)}, text=True).strip()
    components = runtime_version.split('.')
    if len(components) != 3 or not all(component.isdecimal() for component in components) or \
            components[:2] != ['5', '15'] or int(components[2]) < 3:
        raise RuntimeError('Native Tablet input requires the reviewed Qt 5.15 ABI, runtime patch 3 or later')
    output.mkdir(parents=True, exist_ok=True)
    sdk = output / 'sdk'
    sdk.mkdir(exist_ok=True)
    artifacts = []
    for name, expected in PACKAGES.items():
        package = output / Path(name).name
        if not package.exists():
            urllib.request.urlretrieve(BASE + name, package)
        if hashlib.sha256(package.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f'Official SDK checksum mismatch: {package.name}')
        members = subprocess.check_output(['ar', 't', package], text=True).splitlines()
        archives = [member for member in members if member in ['data.tar.xz', 'data.tar.zst', 'data.tar.gz']]
        if len(archives) != 1:
            raise RuntimeError('Expected exactly one official SDK data archive')
        archive = output / archives[0]
        with archive.open('wb') as stream:
            run(['ar', 'p', package, archives[0]], stdout=stream)
        run(['tar', '--extract', '--no-same-owner', '--file', archive, '--directory', sdk])
        archive.unlink()
        artifacts.append({'url': BASE + name, 'sha256': expected})
    include = sdk / 'usr/include/x86_64-linux-gnu/qt5'
    moc = sdk / 'usr/lib/qt5/bin/moc'
    environment = {**os.environ, 'LD_LIBRARY_PATH': str(runtime)}
    flags = ['-std=c++17', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror', '-I', include]
    for module in ['QtCore', 'QtGui', 'QtQml', 'QtQuick']:
        flags.extend(['-I', include / module])
    run([moc, *flags[6:], SOURCE / 'native-input.cpp', '-o', output / 'native-input.moc'], env=environment)
    modules = output / 'qml/BrowserNativeInput'
    modules.mkdir(parents=True, exist_ok=True)
    libraries = [runtime / f'libQt5{module}.so.5' for module in ['Quick', 'Qml', 'Gui', 'Core']]
    if not all(library.is_file() for library in libraries):
        raise RuntimeError('The native worker distribution lacks the required matching Qt5 libraries')
    # A worker may already have the old plugin mapped. Never truncate that inode;
    # the successful new library replaces the directory entry atomically instead.
    descriptor, temporary_library = tempfile.mkstemp(prefix='.browsernativeinput-', suffix='.so', dir=modules)
    os.close(descriptor)
    temporary_library = Path(temporary_library)
    try:
        run(['g++', *flags, '-I', output, '-shared', SOURCE / 'native-input.cpp', '-o', temporary_library, *libraries])
        temporary_library.chmod(0o755)
        os.replace(temporary_library, modules / 'libbrowsernativeinput.so')
    finally:
        temporary_library.unlink(missing_ok=True)
    descriptor, temporary_qmldir = tempfile.mkstemp(prefix='.qmldir-', dir=modules)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write((SOURCE / 'qmldir').read_bytes())
        os.chmod(temporary_qmldir, 0o644)
        os.replace(temporary_qmldir, modules / 'qmldir')
    finally:
        Path(temporary_qmldir).unlink(missing_ok=True)
    shutil.copyfile(SOURCE / 'input-test.qml', output / 'input-test.qml')
    run(['g++', *flags, SOURCE / 'input-test.cpp', '-o', output / 'input-test', *libraries])
    run([moc, *flags[6:], SOURCE / 'grab-test.cpp', '-o', output / 'grab-test.moc'], env=environment)
    run(['g++', *flags, '-I', output, SOURCE / 'grab-test.cpp', '-o', output / 'grab-test', *libraries])
    (output / 'artifacts.json').write_text(json.dumps({'qtSDKVersion': '5.15.3', 'qtRuntimeVersion': runtime_version, 'packages': artifacts,
        'sourceSha256': hashlib.sha256((SOURCE / 'native-input.cpp').read_bytes()).hexdigest()}, indent=2) + '\n')
    print(f'Built native input QML module: {modules}')
    return output / 'input-test'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/browser-lab/native-input')
    parser.add_argument('--qt-libraries', type=Path, default=ROOT / 'build/browser-lab/appimage/squashfs-root/usr/lib')
    parser.add_argument('--qt-plugins', type=Path, help='Matching Qt5 plugin directory when testing a system Qt runtime')
    parser.add_argument('--qt-qml', type=Path, help='Matching Qt5 QML directory when testing a system Qt runtime')
    parser.add_argument('--test', action='store_true', help='Run real native QML assertions using the matching worker Qt runtime')
    options = parser.parse_args()
    output = options.output.resolve()
    runtime = options.qt_libraries.resolve()
    test = build(output, runtime)
    if options.test:
        environment = {**os.environ, 'LD_LIBRARY_PATH': str(runtime),
            'QT_QPA_PLATFORM': 'xcb', 'QT_QUICK_BACKEND': 'software',
            'QT_PLUGIN_PATH': str((options.qt_plugins or runtime.parent / 'plugins').resolve()),
            'QML2_IMPORT_PATH': str((options.qt_qml or runtime.parent / 'qml').resolve())}
        # The release ships only xcb. Use our own authenticated virtual display,
        # never the visitor/operator desktop or its clipboard.
        xvfb = shutil.which('Xvfb') or ROOT / 'build/browser-lab/host-tools/usr/bin/Xvfb'
        with tempfile.TemporaryDirectory(prefix='overte-native-input-') as temporary:
            authority = Path(temporary) / 'Xauthority'
            cookie = os.urandom(16)
            field = lambda value: struct.pack('>H', len(value)) + value
            authority.write_bytes(struct.pack('>H', 65535) + field(b'') + field(b'') + field(b'MIT-MAGIC-COOKIE-1') + field(cookie))
            authority.chmod(0o600)
            display_process = subprocess.Popen([str(xvfb), '-displayfd', '1', '-auth', str(authority),
                '-nolisten', 'tcp', '-screen', '0', '640x480x24'], stdout=subprocess.PIPE, text=True)
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(display_process.stdout, selectors.EVENT_READ)
                    if not selector.select(10):
                        raise RuntimeError('The isolated native input test display did not start')
                number = display_process.stdout.readline().strip()
                if not number.isdecimal():
                    raise RuntimeError('The isolated native input display returned an invalid number')
                environment.update(DISPLAY=':' + number, XAUTHORITY=str(authority))
                run([test, output / 'qml', output / 'input-test.qml'], env=environment)
                run([output / 'grab-test', output / 'qml'], env=environment)
            finally:
                display_process.terminate()
                try:
                    display_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    display_process.kill()
                    display_process.wait()
