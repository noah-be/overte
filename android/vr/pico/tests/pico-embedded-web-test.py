#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Real Qt5 native endpoint, selected Pico QML, keyboard layout and source lifecycle."""
import os
import argparse
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
WEB = ROOT / 'android/common/web'
TESTS = Path(__file__).resolve().parent

class PicoEmbeddedWebTest(unittest.TestCase):
    def test_selected_native_world_tablet_and_keyboard(self):
        qt = Path(os.environ.get('OVERTE_QT5_ROOT', str(Path.home() / '.local/overte-qt5/root')))
        environment = os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software'}
        if (qt / 'usr/lib64/pkgconfig/Qt5WebChannel.pc').is_file():
            environment.update({
                'PKG_CONFIG_PATH': str(qt / 'usr/lib64/pkgconfig'), 'PKG_CONFIG_SYSROOT_DIR': str(qt),
                'LD_LIBRARY_PATH': str(qt / 'usr/lib64'), 'QML2_IMPORT_PATH': str(qt / 'usr/lib64/qt5/qml'),
                'QT_PLUGIN_PATH': str(qt / 'usr/lib64/qt5/plugins')})
            tools = qt / 'usr/lib64/qt5/bin'
            library = ['-L' + str(qt / 'usr/lib64')]
        else:
            # Standard Qt5 development installations remain usable in CI.
            tools = Path(subprocess.check_output(['pkg-config', '--variable=host_bins', 'Qt5Core'],
                env=environment, text=True).strip())
            library = []
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs',
            'Qt5Quick', 'Qt5WebChannel', 'Qt5Network'], env=environment, text=True))
        jdk = Path(os.environ.get('JAVA_HOME', '/usr/lib/jvm/temurin-21-jdk'))
        with tempfile.TemporaryDirectory(prefix='overte-pico-embedded-web-') as temporary:
            stage = Path(temporary)
            qml = stage / 'qml'
            qml.mkdir()
            production = ROOT / 'interface/resources/qml'
            def copy(relative):
                target = qml / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(production / relative, target)
            for relative in ('Web3DSurface.qml', '+android_interface/Web3DSurface.qml',
                '+android_interface/Web3DSurfaceAndroid.qml', '+android_picoInterface/Web3DSurface.qml',
                '+android_picoInterface/PicoLegacyWebSurface.qml', 'controls/EmbeddedWebBackend.qml',
                'controls/EmbeddedWebView.qml', 'controls/NativeFlickableWebViewCore.qml',
                'controls/FlickableWebViewCore.qml', 'controls/TabletWebScreen.qml',
                'controls/+android/EmbeddedWebBackend.qml',
                'controls/+android_picoInterface/EmbeddedWebBackend.qml',
                'controlsUit/Keyboard.qml', 'controlsUit/Key.qml', 'controlsUit/TouchUiMetrics.qml',
                'controlsUit/TouchUiProfile.qml', 'controlsUit/TouchUiProfileBase.qml'):
                copy(relative)
            self.assertIn('AndroidEmbeddedWebBackend 1.0 +android/EmbeddedWebBackend.qml', (production / 'controls/qmldir').read_text())
            (qml / 'controls/qmldir').write_text('module controls\nEmbeddedWebView 1.0 EmbeddedWebView.qml\nNativeFlickableWebViewCore 1.0 NativeFlickableWebViewCore.qml\nFlickableWebViewCore 1.0 FlickableWebViewCore.qml\nAndroidEmbeddedWebBackend 1.0 +android/EmbeddedWebBackend.qml\n')
            (qml / 'controlsUit/qmldir').write_text('module controlsUit\nKeyboard 1.0 Keyboard.qml\nKey 1.0 Key.qml\nTouchUiMetrics 1.0 TouchUiMetrics.qml\nTouchUiProfileBase 1.0 TouchUiProfileBase.qml\n')
            subprocess.run([str(tools / 'moc'), str(WEB / 'src/NativeWebViewItem.h'), '-o', str(stage / 'native-moc.cpp')], check=True)
            subprocess.run([str(tools / 'moc'), str(TESTS / 'pico-embedded-web-native-test.cpp'),
                '-o', str(stage / 'pico-embedded-web-native-test.moc')], check=True)
            subprocess.run([str(tools / 'rcc'), str(WEB / 'embedded-web.qrc'), '-o', str(stage / 'resources.cpp')], check=True)
            binary = stage / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-UNDEBUG',
                str(WEB / 'src/NativeWebViewItem.cpp'),
                str(ROOT / 'android/vr/pico/apps/picoInterface/src/PicoEmbeddedWeb.cpp'),
                str(TESTS / 'pico-embedded-web-native-test.cpp'),
                str(stage / 'native-moc.cpp'), str(stage / 'resources.cpp'),
                '-I' + str(stage), '-I' + str(WEB / 'src'), '-I' + str(ROOT / 'libraries/shared/src'),
                '-I' + str(jdk / 'include'), '-I' + str(jdk / 'include/linux'),
                *library, '-o', str(binary), *flags], env=environment, check=True, timeout=90)
            subprocess.run([str(binary), str(qml)], env=environment, check=True, timeout=30)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--android-jar', type=Path)
    parser.add_argument('--webkit-jar', type=Path)
    parser.add_argument('--qt-jar', type=Path)
    parser.add_argument('--core-jar', type=Path, help='Actual AndroidX Core 1.1.0 required by Snapshot')
    parser.add_argument('--api-only', action='store_true')
    parser.add_argument('--jni-create', action='store_true', help='Execute production create through a real host JVM; Android scheduling is substituted')
    args, remaining = parser.parse_known_args()
    artifacts = (args.android_jar, args.webkit_jar, args.qt_jar, args.core_jar)
    if (args.api_only or args.jni_create) and not any(artifacts):
        parser.error('--api-only requires the four actual SDK artifacts')
    if any(artifacts):
        if not all(path and path.is_file() for path in artifacts):
            parser.error('Production Java API compilation requires all three actual SDK artifacts')
        # PermissionsActivity needs generated APK R. Every other Pico class,
        # real Qt binding and shared runtime is compiled without substitutions.
        sources = list((ROOT / 'android/vr/pico/apps/picoInterface/src/main/java').rglob('*.java'))
        sources = [path for path in sources if path.name != 'PermissionsActivity.java']
        for relative in ('android/common/libraries/qt/src/main/java', 'android/common/web/java', 'android/common/documents/java', 'android/common/snapshot/java', 'security/redaction/java'):
            sources.extend((ROOT / relative).rglob('*.java'))
        with tempfile.TemporaryDirectory(prefix='overte-pico-web-api-') as output:
            subprocess.run(['javac', '-classpath', os.pathsep.join(map(str, artifacts)), '-d', output,
                            *map(str, sources)], check=True, timeout=60)
            if args.jni_create:
                # Compile production against actual APIs first; only the host JVM
                # substitutes Looper/Handler at the Android scheduling boundary.
                subprocess.run(['javac', '-classpath', output + os.pathsep + str(args.android_jar),
                                '-d', output, *map(str, (TESTS / 'jni-boundary').rglob('*.java'))], check=True, timeout=30)
                qt = Path(os.environ.get('OVERTE_QT5_ROOT', str(Path.home() / '.local/overte-qt5/root')))
                environment = os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software'}
                if (qt / 'usr/lib64/pkgconfig/Qt5WebChannel.pc').is_file():
                    environment.update({'PKG_CONFIG_PATH': str(qt / 'usr/lib64/pkgconfig'),
                        'PKG_CONFIG_SYSROOT_DIR': str(qt), 'LD_LIBRARY_PATH': str(qt / 'usr/lib64'),
                        'QML2_IMPORT_PATH': str(qt / 'usr/lib64/qt5/qml'),
                        'QT_PLUGIN_PATH': str(qt / 'usr/lib64/qt5/plugins')})
                    tools = qt / 'usr/lib64/qt5/bin'
                    libraries = ['-L' + str(qt / 'usr/lib64')]
                else:
                    tools = Path(subprocess.check_output(['pkg-config', '--variable=host_bins', 'Qt5Core'], env=environment, text=True).strip())
                    libraries = []
                stage = Path(output)
                subprocess.run([str(tools / 'moc'), str(WEB / 'src/NativeWebViewItem.h'), '-o', str(stage / 'moc.cpp')], check=True)
                subprocess.run([str(tools / 'rcc'), str(WEB / 'embedded-web.qrc'), '-o', str(stage / 'resources.cpp')], check=True)
                flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt5Quick', 'Qt5WebChannel', 'Qt5Network'], env=environment, text=True))
                jdk = Path(os.environ.get('JAVA_HOME', '/usr/lib/jvm/temurin-21-jdk'))
                subprocess.run(['c++', '-std=c++17', '-fPIC', '-UNDEBUG', str(WEB / 'src/NativeWebViewItem.cpp'),
                    str(ROOT / 'android/vr/pico/apps/picoInterface/src/PicoEmbeddedWeb.cpp'), str(TESTS / 'pico-embedded-web-jni-test.cpp'),
                    str(stage / 'moc.cpp'), str(stage / 'resources.cpp'), '-I' + str(WEB / 'src'), '-I' + str(ROOT / 'libraries/shared/src'),
                    '-I' + str(jdk / 'include'), '-I' + str(jdk / 'include/linux'), '-L' + str(jdk / 'lib/server'),
                    '-Wl,-rpath,' + str(jdk / 'lib/server'), '-ljvm', *libraries, '-o', str(stage / 'jni-test'), *flags], env=environment, check=True, timeout=90)
                subprocess.run([str(stage / 'jni-test'), output + os.pathsep + os.pathsep.join(map(str, artifacts))], env=environment, check=True, timeout=30)
                # A real compiled previous ABI must not silently accept the
                # newly added private editor argument.
                previous = stage / 'previous-abi'
                previous.mkdir()
                java = previous / 'EmbeddedWebView.java'
                original = (WEB / 'java/org/overte/web/EmbeddedWebView.java').read_text()
                old = original.replace('String bootstrap, String editorBootstrap) {\n        MAIN.post(',
                    'String bootstrap) {\n        final String editorBootstrap = "";\n        MAIN.post(', 1)
                if old == original:
                    raise AssertionError('Production create signature was not found for the previous ABI fixture')
                java.write_text(old)
                classpath = output + os.pathsep + os.pathsep.join(map(str, artifacts))
                subprocess.run(['javac', '-classpath', classpath, '-d', str(previous), str(java)], check=True, timeout=30)
                subprocess.run([str(stage / 'jni-test'), str(previous) + os.pathsep + classpath, 'reject-old-abi'],
                    env=environment, check=True, timeout=30)
        print('PASS actual Pico Activity/Hosts + Qt bindings + shared Web/Documents/Snapshot compile; APK resources excluded')
    if not args.api_only:
        unittest.main(argv=[__file__, *remaining])
