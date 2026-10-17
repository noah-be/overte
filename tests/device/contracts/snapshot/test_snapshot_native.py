#!/usr/bin/env python3
"""Compile actual Snapshot storage/capture/360/upload and execute lifecycle races.

The render queue, preferences and application services are explicit boundaries;
Qt image codecs, encoder, capture atomics and production callback bodies are real.
No Apple/Android SDK compilation or device evidence is inferred from this test.
"""
from pathlib import Path
import hashlib
import os
import shlex
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent

def block(source, marker):
    start = source.index(marker)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'

qt = os.environ.get('OVERTE_SNAPSHOT_TEST_QT', 'Qt6')
if qt not in ('Qt5', 'Qt6'):
    raise SystemExit('OVERTE_SNAPSHOT_TEST_QT must be Qt5 or Qt6')
flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs',
    *[qt + part for part in ('Core','Gui','Concurrent','Network')]], text=True))
tools = Path(subprocess.check_output(['pkg-config','--variable=' +
    ('libexecdir' if qt == 'Qt6' else 'host_bins'),qt+'Core'], text=True).strip())
if not (tools/'moc').is_file() and os.environ.get('PKG_CONFIG_SYSROOT_DIR'):
    tools = Path(os.environ['PKG_CONFIG_SYSROOT_DIR']) / str(tools).lstrip('/')
moc = tools/'moc'
with zipfile.ZipFile(HERE / 'fixtures/GifCreator.zip') as archive:
    fixture_header = archive.read('GifCreator.h')
assert hashlib.sha256(fixture_header).hexdigest() == '275e4fd71a1d3bdc80279aee59d6abf530d628ea77aec01a2cd155220be2c8be'
with tempfile.TemporaryDirectory(prefix='overte-snapshot-native-') as temporary:
    stage = Path(temporary)
    for name in ('SnapshotAnimated.h','SnapshotAnimated.cpp','SnapshotCapture.h','SnapshotStorage.h','SnapshotUploader.h','SnapshotUploader.cpp'):
        shutil.copy2(ROOT / 'interface/src/ui' / name, stage / name)
    # Access the real private capture driver to deliver intentionally stale
    # render operators deterministically, without waiting for a GPU/device.
    header = stage / 'SnapshotAnimated.h'
    header.chmod(0o644)
    header.write_text(header.read_text().replace('private:', 'public:'))
    (stage / 'third_party').mkdir()
    (stage / 'third_party/GifCreator.h').write_bytes(fixture_header)
    for name in ('Application.h','DependencyManager.h','SettingHandle.h','Snapshot.h'):
        (stage / name).write_text('#include "services.h"\n')
    (stage / 'AddressManager.h').write_text('#include "upload-services.h"\n')
    shutil.copy2(HERE / 'upload-services.h', stage / 'upload-services.h')
    (stage / 'scripting').mkdir()
    (stage / 'scripting/WindowScriptingInterface.h').write_text('#include "services.h"\n')
    shutil.copy2(HERE / 'snapshot-native-test.cpp', stage / 'snapshot-native-test.cpp')
    shutil.copy2(HERE / 'services.h', stage / 'services.h')
    source = (ROOT / 'interface/src/ui/Snapshot.cpp').read_text()
    glm_flags = ['-isystem',os.environ['OVERTE_TEST_GLM_INCLUDE']] if os.environ.get('OVERTE_TEST_GLM_INCLUDE') else []
    dimension = source[source.index('static const float CUBEMAP_SIDE_PIXEL_DIMENSION'):source.index('void Snapshot::save360Snapshot(')]
    (stage / 'production-360-constants.inc').write_text(dimension)
    (stage / 'production-storage-constants.inc').write_text(source[source.index('const QString FILENAME_PATH_FORMAT'):source.index('Snapshot::Snapshot()')])
    (stage / 'production-capture.inc').write_text(''.join(block(source, marker) for marker in (
        'SnapshotCapture Snapshot::beginCapture(', 'void Snapshot::captureStatus(', 'void Snapshot::cancelCapture(',
        'QString Snapshot::getSnapshotsLocation(', 'QFile* Snapshot::savedFileForSnapshot(',
        'QImage Snapshot::convertToCubemap(', 'QImage Snapshot::convertToEquirectangular(',
        'Snapshot::Snapshot()', 'QString Snapshot::saveSnapshot(', 'void Snapshot::save360Snapshot(',
        'void Snapshot::takeNextSnapshot()', 'void Snapshot::restoreSecondaryCamera()',
        'void Snapshot::complete360(', 'void Snapshot::uploadSnapshot(',
        'void Snapshot::cancelUpload(', 'void Snapshot::cancelUploads(',
        'QUrl Snapshot::snapshotFileUrl(')))
    window=(ROOT/'interface/src/scripting/WindowScriptingInterface.cpp').read_text()
    (stage/'production-window.inc').write_text(''.join(block(window,marker) for marker in (
        'void WindowScriptingInterface::takeSnapshot(', 'void WindowScriptingInterface::takeSecondaryCamera360Snapshot(')))
    application=(ROOT/'interface/src/Application.cpp').read_text()
    (stage/'production-application.inc').write_text('#define Application RenderApplication\n' + ''.join(
        block(application,marker) for marker in ('void Application::takeSnapshot(',
        'void Application::takeSecondaryCamera360Snapshot(')) + '#undef Application\n')
    subprocess.run([str(moc),str(stage/'SnapshotUploader.h'),'-I'+str(ROOT/'libraries/networking/src'),
        '-o',str(stage/'SnapshotUploader.moc')],check=True,timeout=30)
    subprocess.run([str(moc),str(stage/'upload-services.h'),'-I'+str(ROOT/'libraries/networking/src'),
        '-o',str(stage/'upload-services.moc')],check=True,timeout=30)
    for name in ('services.h',):
        subprocess.run([str(moc),str(stage/name),'-o',str(stage/'services.moc')],check=True,timeout=30)
    if qt == 'Qt5' and os.environ.get('PKG_CONFIG_SYSROOT_DIR'):
        library = stage/'qt-link';library.mkdir()
        sdk = Path(os.environ['PKG_CONFIG_SYSROOT_DIR'])/'usr/lib64'
        for name in ('Core','Gui','Concurrent','Network'):
            (library/('libQt5'+name+'.so')).symlink_to(sdk/('libQt5'+name+'.so.5'))
        flags = ['-L'+str(library),*flags]
    binary = stage / 'snapshot-native-test'
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-fPIC','-pthread',
        '-O2',*glm_flags,'-I'+str(stage),'-I'+str(ROOT/'libraries/shared/src'),'-I'+str(ROOT/'libraries/networking/src'),'-isystem',str(stage/'third_party'),str(stage/'snapshot-native-test.cpp'),str(stage/'SnapshotAnimated.cpp'),str(stage/'SnapshotUploader.cpp'),
        '-o',str(binary),*flags],check=True,timeout=60)
    runtime = os.environ | {'QT_QPA_PLATFORM':'offscreen', 'QT_LOGGING_TO_CONSOLE':'1'}
    if qt == 'Qt5' and os.environ.get('PKG_CONFIG_SYSROOT_DIR'):
        runtime['QT_PLUGIN_PATH'] = str(Path(os.environ['PKG_CONFIG_SYSROOT_DIR'])/'usr/lib64/qt5/plugins')
    subprocess.run([str(binary)],check=True,timeout=30,env=runtime)
