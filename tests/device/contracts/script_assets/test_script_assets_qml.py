#!/usr/bin/env python3
"""Actual selected production UI, native Qt models, local files and helper operations.

Script engines, networking and headset services are explicit native boundaries.
The desktop QFileDialog and FileDialogHelper execute unchanged production code;
mobile provider selection is substituted at its documented adapter callback.
"""
import os
import re
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = Path(__file__).resolve().parent
qt = Path(os.environ.get('OVERTE_QT5_ROOT', str(Path.home() / '.local/overte-qt5/root')))
qt5_available = (qt / 'usr/lib64/pkgconfig/Qt5QuickTest.pc').is_file() or subprocess.run(
    ['pkg-config', '--exists', 'Qt5QuickTest'], check=False).returncode == 0
major = os.environ.get('OVERTE_NATIVE_QT_MAJOR', '5' if qt5_available else '6')
assert major in ('5', '6')
environment = os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software',
    'QT_LOGGING_RULES': '*.warning=true;*.info=false',
    'OVERTE_QML_SOURCE_ROOT': str(ROOT / 'interface/resources/qml')}
libraries = []
if major == '5' and (qt / 'usr/lib64/pkgconfig/Qt5QuickTest.pc').is_file():
    environment.update({'PKG_CONFIG_PATH': str(qt / 'usr/lib64/pkgconfig'), 'PKG_CONFIG_SYSROOT_DIR': str(qt),
        'LD_LIBRARY_PATH': str(qt / 'usr/lib64'), 'QML2_IMPORT_PATH': str(qt / 'usr/lib64/qt5/qml'),
        'QT_PLUGIN_PATH': str(qt / 'usr/lib64/qt5/plugins')})
    tools = qt / 'usr/lib64/qt5/bin'
    libraries = ['-L' + str(qt / 'usr/lib64')]
else:
    tools = Path(subprocess.check_output(['pkg-config', '--variable=libexecdir' if major == '6' else '--variable=host_bins', 'Qt' + major + 'Core'], env=environment, text=True).strip())
flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs',
    *['Qt' + major + name for name in ('QuickTest', 'Quick', 'Widgets', 'Test')]], env=environment, text=True))
with tempfile.TemporaryDirectory(prefix='overte-native-script-assets-') as temporary:
    stage = Path(temporary)
    route = (ROOT / 'interface/src/Application_UI.cpp').read_text()
    start = route.index('void Application::showAssetServerWidget(')
    end = route.index('\nvoid Application::', start + 1)
    (stage / 'asset-route.inc').write_text(route[start:end])
    menu = (ROOT / 'interface/src/Menu.cpp').read_text()
    start = menu.index('    // Edit > Asset Browser')
    end = menu.index('    // Edit > Avatar Packager', start)
    (stage / 'asset-menu.inc').write_text(menu[start:end])
    api = (ROOT / 'libraries/entities/src/EntityScriptingInterface.cpp').read_text()
    signature = 'QUuid EntityScriptingInterface::addImageEntity('
    start = api.index(signature)
    end = api.index('{', start) + 1
    depth = 1
    while depth:
        depth += (api[end] == '{') - (api[end] == '}')
        end += 1
    (stage / 'image-api-body.inc').write_text(api[start:end])
    declaration = re.search(r'Q_INVOKABLE QUuid addImageEntity\([^;]+;',
        (ROOT / 'libraries/entities/src/EntityScriptingInterface.h').read_text()).group()
    (stage / 'image-api-declaration.inc').write_text(declaration)
    constants = re.findall(r'^const QString (?:NOT_)?GRABBABLE_USER_DATA = .+;', api, re.MULTILINE)
    (stage / 'image-api-constants.inc').write_text('\n'.join(constants))
    source = FIXTURES / 'native-services.cpp'
    for header, target in ((source, stage / 'native-services.moc'),
        (ROOT / 'libraries/ui/src/FileDialogHelper.h', stage / 'files-moc.cpp')):
        subprocess.run([str(tools / 'moc'), str(header), '-I' + str(stage), '-o', str(target)], check=True)
    binary = stage / 'native-script-assets'
    subprocess.run(['c++', '-std=c++17', '-fPIC', '-UNDEBUG', str(source),
        str(ROOT / 'libraries/ui/src/FileDialogHelper.cpp'), str(ROOT / 'libraries/ui/src/ui/Logging.cpp'),
        str(stage / 'files-moc.cpp'), '-I' + str(stage), '-I' + str(ROOT / 'libraries/ui/src'),
        *libraries, '-o', str(binary), *flags], env=environment, check=True, timeout=90)
    result = subprocess.run([str(binary), '-file-selector', 'android_picoInterface', '-file-selector', 'android_interface',
        '-import', str(ROOT / 'interface/resources/qml'), '-import', str(ROOT / 'tests/device/qml/imports'),
        '-input', str(FIXTURES / 'tst_script_assets.qml')], env=environment, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    print(result.stdout, end='')
    result.check_returncode()
    if re.search(r'TypeError:|ReferenceError:|Binding loop|Could not convert argument|Cannot assign|Invalid attempt to destroy', result.stdout):
        raise RuntimeError('Production QML emitted an execution error')
