#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify compaction with real Qt lookups, compiled C++ and binary resources."""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('compact', ROOT / 'android/phone/tools/compact_qt_resources.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
parser = argparse.ArgumentParser()
parser.add_argument('--qt-root', type=Path, required=True, help='native Qt 5 SDK with rcc, headers and Core library')
parser.add_argument('--apk', type=Path, help='also validate every lookup in an existing APK resources.rcc')
args, rest = parser.parse_known_args()
QT = args.qt_root.resolve()


class CompactionTest(unittest.TestCase):
    @unittest.skipUnless(args.apk, 'optional full APK resource comparison requires --apk')
    def test_all_existing_apk_resources_with_qt(self):
        with tempfile.TemporaryDirectory() as td, zipfile.ZipFile(args.apk) as archive:
            p = Path(td)
            original = archive.read('assets/resources.rcc')
            compacted = module.binary(original)
            (p/'original.rcc').write_bytes(original)
            (p/'compact.rcc').write_bytes(compacted)
            self.assertLess(len(compacted), len(original))
            (p/'scan.cpp').write_text(r'''#include <QCoreApplication>
#include <QResource>
#include <QFile>
#include <QDirIterator>
#include <QCryptographicHash>
#include <QStringList>
#include <cstdio>
int main(int argc, char **argv) {
 QCoreApplication app(argc, argv);
 if (argc != 2 || !QResource::registerResource(QString::fromUtf8(argv[1]))) return 2;
 QDirIterator it(":/", QDir::Files, QDirIterator::Subdirectories);
 QStringList files;
 while (it.hasNext()) files.append(it.next());
 files.sort();
 for (const auto &name: files) {
  QFile f(name); if (!f.open(QIODevice::ReadOnly)) return 3;
  auto hash = QCryptographicHash::hash(f.readAll(), QCryptographicHash::Sha256).toHex();
  std::printf("%s %s\n", name.toUtf8().constData(), hash.constData());
 }
 return 0;
}
''')
            subprocess.run(['g++', '-fPIC', '-std=c++17', str(p/'scan.cpp'),
                '-I'+str(QT/'include'), '-I'+str(QT/'include/QtCore'),
                '-L'+str(QT/'lib'), '-lQt5Core', '-o', str(p/'scan')], check=True)
            env = dict(os.environ, LD_LIBRARY_PATH=str(QT/'lib')+':'+os.environ.get('LD_LIBRARY_PATH',''))
            before = subprocess.check_output([str(p/'scan'), str(p/'original.rcc')],env=env)
            after = subprocess.check_output([str(p/'scan'), str(p/'compact.rcc')],env=env)
            self.assertEqual(before, after)
            self.assertGreater(len(before.splitlines()), 1000)
            print(f'All {len(before.splitlines())} Qt resource lookups preserved; RCC {len(original)} -> {len(compacted)} bytes')

    def test_phone_cmake_merges_chunks_and_compiles_compact_resource(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            # Execute the actual changed CMake block, with two tiny shader chunks.
            macro = (ROOT/'cmake/macros/AutoScribeShader.cmake').read_text()
            start = macro.rfind('    if (HIFI_ANDROID', 0, macro.index('# One logical resource pool'))
            end = macro.index('    configure_file(\n        ${CMAKE_CURRENT_SOURCE_DIR}/src/shaders/Shaders.cpp.in', start)
            block = macro[start:end]
            (p/'android/phone/tools').mkdir(parents=True)
            (p/'android/phone/tools/compact_qt_resources.py').symlink_to(ROOT/'android/phone/tools/compact_qt_resources.py')
            (p/'shaders.qrc.in').write_bytes((ROOT/'libraries/shaders/shaders.qrc.in').read_bytes())
            (p/'data').write_text('same shader payload\n'*500)
            script = '''cmake_minimum_required(VERSION 3.16)
project(resource_smoke LANGUAGES CXX)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(HIFI_ANDROID TRUE)
set(HIFI_ANDROID_APP phoneInterface)
set(SHADER_QRC_COUNT 2)
set(SHADER_QRC_1 "<file alias=\\"first\\">${CMAKE_CURRENT_SOURCE_DIR}/data</file>")
set(SHADER_QRC_2 "<file alias=\\"second\\">${CMAKE_CURRENT_SOURCE_DIR}/data</file>")
''' + block + '''
add_library(resource_smoke SHARED ${AUTOSCRIBE_SHADER_LIB_SRC})
target_link_libraries(resource_smoke Qt5::Core)
'''
            # Conan exports Qt's CMake package metadata separately from the SDK.
            # Supply the equivalent native Core/tool targets for this fixture.
            config = p/'qt-config'
            config.mkdir()
            (config/'Qt5Config.cmake').write_text(
                'add_library(Qt5::Core SHARED IMPORTED)\n'
                f'set_target_properties(Qt5::Core PROPERTIES IMPORTED_LOCATION "{QT}/lib/libQt5Core.so" INTERFACE_INCLUDE_DIRECTORIES "{QT}/include;{QT}/include/QtCore")\n'
                f'set(Qt5Core_RCC_EXECUTABLE "{QT}/bin/rcc")\n')
            (p/'CMakeLists.txt').write_text(script)
            env = dict(os.environ, LD_LIBRARY_PATH=str(QT/'lib')+':'+os.environ.get('LD_LIBRARY_PATH',''))
            subprocess.run(['cmake', '-S', str(p), '-B', str(p/'build'), '-DQt5_DIR='+str(config)], env=env,check=True,stdout=subprocess.PIPE)
            subprocess.run(['cmake', '--build', str(p/'build'), '-j2'], env=env,check=True,stdout=subprocess.PIPE)
            generated = (p/'build/qrc_phone_shaders.cpp').read_bytes()
            self.assertEqual(module.cpp(generated), generated)
            tree = module.array(generated.decode(), 'qt_resource_struct')[1]
            offsets = [struct.unpack_from('>I',tree,i+10)[0] for i in range(0,len(tree),22)
                       if not struct.unpack_from('>H',tree,i+4)[0]&2]
            self.assertEqual(len(offsets),2)
            self.assertEqual(len(set(offsets)),1)

    def test_rejects_unknown_and_truncated_data(self):
        for data in (b'', b'qres' + b'\0' * 20):
            with self.assertRaises(ValueError):
                module.binary(data)
        tree = struct.pack('>IHHHIQ', 0, 0, 0, 1, 0, 0)
        with self.assertRaises(ValueError):
            module.compact(tree, b'\0\0\0\xffsmall')
        with self.assertRaises(ValueError):
            module.cpp(b'int version = 2;')

    def test_real_qt_binary_and_cpp_lookup_preserves_aliases_and_locales(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            data = b'unchanged shader/resource content\n' * 500
            other = b'unique resource\0\xff' * 40
            (p/'data').write_bytes(data)
            (p/'other').write_bytes(other)
            (p/'empty').write_bytes(b'')
            (p/'fixture.qrc').write_text('''<RCC><qresource prefix="/size-test">
<file alias="first">data</file><file alias="nested/second">data</file>
<file alias="localized">data</file><file alias="empty">empty</file>
<file alias="unique">other</file></qresource>
<qresource prefix="/size-test" lang="fr"><file alias="localized">other</file></qresource></RCC>''')
            probe = r'''#include <QCoreApplication>
#include <QResource>
#include <QFile>
#include <QLocale>
#include <QCryptographicHash>
#include <cstdio>
int main(int argc, char **argv) {
 QCoreApplication app(argc, argv);
 if (argc < 4) return 2;
 QLocale::setDefault(QLocale(argv[2]));
 if (QString(argv[1]) != "-" && !QResource::registerResource(QString(argv[1]))) return 3;
 for (int i=3; i<argc; ++i) {
  QFile file(QString::fromUtf8(argv[i]));
  if (!file.open(QIODevice::ReadOnly)) return 4;
  auto hash = QCryptographicHash::hash(file.readAll(), QCryptographicHash::Sha256).toHex();
  std::puts(hash.constData());
 }
 return 0;
}
'''
            (p/'probe.cpp').write_text(probe)
            env = os.environ.copy()
            env.update(QT_HASH_SEED='0', QT_RCC_SOURCE_DATE_OVERRIDE='1700000000',
                       LD_LIBRARY_PATH=str(QT/'lib') + ':' + env.get('LD_LIBRARY_PATH', ''))
            def run(command):
                return subprocess.check_output(list(map(str, command)), env=env, text=True)
            def compile_probe(output, extra=()):
                run(['g++', '-fPIC', '-std=c++17', p/'probe.cpp', *extra,
                     '-I'+str(QT/'include'), '-I'+str(QT/'include/QtCore'),
                     '-L'+str(QT/'lib'), '-lQt5Core', '-o', output])
            compile_probe(p/'probe')
            paths = [':/size-test/'+x for x in ['first', 'nested/second', 'localized', 'empty', 'unique']]
            for compressed in (False, True):
                flags = [] if compressed else ['-no-compress']
                raw = p/'raw.rcc'; small = p/'small.rcc'
                run([QT/'bin/rcc', '--format-version', '3', '--binary', *flags, p/'fixture.qrc', '-o', raw])
                original = raw.read_bytes(); result = module.binary(original)
                self.assertLess(len(result), len(original))
                self.assertEqual(module.binary(result), result)  # deterministic and idempotent
                small.write_bytes(result)
                run([QT/'bin/rcc', '--format-version', '3', '--name', 'fixture', *flags, p/'fixture.qrc', '-o', p/'raw.cpp'])
                cpp = module.cpp((p/'raw.cpp').read_bytes()); (p/'small.cpp').write_bytes(cpp)
                self.assertEqual(module.cpp(cpp), cpp)
                compile_probe(p/'cpp-probe', [p/'small.cpp'])
                for locale in ['C', 'fr_FR']:
                    values = [data, data, other if locale == 'fr_FR' else data, b'', other]
                    expected = ''.join(hashlib.sha256(value).hexdigest()+'\n' for value in values)
                    for exe, rcc in [(p/'probe', raw), (p/'probe', small), (p/'cpp-probe', '-')]:
                        self.assertEqual(run([exe, rcc, locale, *paths]), expected)


if __name__ == '__main__':
    unittest.main(argv=[__file__, *rest])
