#!/usr/bin/env python3
"""Execute the proposed tool's real guards against temporary host fixtures.

No Podman, compiler, device or real Conan operation is permitted by this test.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

TOOL = Path(__file__).resolve().parents[1] / 'prepare-phone-qtcore-o2.py'
SOURCE = TOOL.read_text()
IMAGE_A = 'sha256:' + 'a' * 64
IMAGE_B = 'sha256:' + 'b' * 64
ELF_TEXT = '''ELF Header:
  Class: ELF64
  Machine: AArch64
  0x000000000000000e (SONAME) Library soname: [libQt5Core_arm64-v8a.so]
  0x0000000000000001 (NEEDED) Shared library: [libc.so]
  1: 0000000000100000 55 FUNC GLOBAL DEFAULT 12 exported_function
  2: 0000000000101000 8 OBJECT GLOBAL DEFAULT 13 exported_data
  3: 0000000000000000 0 FUNC GLOBAL DEFAULT UND malloc
'''


class Guards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / 'conan/p/b/qtfixture'
        self.build = self.package / 'b/build_folder'
        self.core = self.build / 'qtbase/src/corelib'
        for relative in ['.obj', '.moc', '.pch/Qt5Core_arm64-v8a.pch']:
            (self.core / relative).mkdir(parents=True, exist_ok=True)
        self.write(self.core / 'Makefile',
                   'QMAKE = /fixture/conan/p/b/qtfixture/b/build_folder/qtbase/bin/qmake\n'
                   'CXX = /opt/android-sdk/ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin/clang++\n'
                   'DEFINES = -DQT_BUILD_CORE_LIB\nCFLAGS = -g\nCXXFLAGS = -g\n')
        self.write(self.core / '.obj/core.o', 'old object')
        self.write(self.core / '.pch/Qt5Core_arm64-v8a.pch/c.pch', 'old C pch')
        self.write(self.core / '.pch/Qt5Core_arm64-v8a.pch/c++.pch', 'old C++ pch')
        self.write(self.build / 'qtbase/lib/libQt5Core_arm64-v8a.so', 'old library')
        self.write(self.package / 'p/conaninfo.txt',
                   'arch=armv8\nbuild_type=Debug\nos=Android\nmulticonfiguration=False\n')
        self.write(self.package / 'p/config.summary', 'debug; optimized tools\n')
        self.write(self.package / 'p/mkspecs/qconfig.pri', 'CONFIG += debug\n')
        self.write(self.package / 'b/qt5/qtbase/src/corelib/core.cpp', 'same patched source\n')
        self.sdk = self.root / 'sdk'
        self.write(self.sdk / 'ndk/27.3.13750724/source.properties', 'Pkg.Revision=27.3.13750724')
        self.write(self.sdk / 'ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin/clang', 'compiler fixture')
        self.apk = self.root / 'baseline.apk'
        with zipfile.ZipFile(self.apk, 'w') as archive:
            archive.writestr('lib/arm64-v8a/libQt5Core_arm64-v8a.so', b'installed QtCore')
        self.tool = self.root / 'tool.py'
        self.tool.write_text(SOURCE)
        self.m = types.ModuleType('qtcore_proposal')
        self.m.__file__ = str(self.tool)
        exec(compile(SOURCE, str(self.tool), 'exec'), self.m.__dict__)
        self.args = argparse.Namespace(package_root=self.package, sdk=self.sdk,
                                       work_dir=self.root / 'work', base_apk=self.apk,
                                       image='fixture-image', jobs=2)
        self.image = IMAGE_A
        self.inspect = patch.object(self.m.subprocess, 'check_output', side_effect=self.fake_inspect).start()
        self.addCleanup(patch.stopall)
        self.run = patch.object(self.m.subprocess, 'run', side_effect=self.fake_run).start()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def fake_inspect(self, argv, **kwargs):
        if argv[:3] == ['podman', 'image', 'inspect']:
            return self.image + '\n'
        self.assertEqual(Path(argv[0]).name, 'llvm-readelf')
        self.assertEqual(argv[1:-1], ['-h', '-d', '--dyn-syms', '--wide'])
        self.assertTrue(Path(argv[-1]).is_file())
        return ELF_TEXT

    def fake_run(self, argv, **kwargs):
        # Emulate only the explicitly required independent copy in a temp fixture.
        # Any attempted Podman/build invocation fails the test immediately.
        self.assertEqual(argv[:3], ['cp', '-a', '--reflink=auto'])
        self.assertEqual(Path(argv[3]), self.build)
        self.assertTrue(Path(argv[4]).is_relative_to(self.root))
        shutil.copytree(argv[3], argv[4], symlinks=True)
        return types.SimpleNamespace(returncode=0)

    def prepare(self):
        self.m.configure(self.args)
        self.m.guard()
        self.m.prepare()
        self.m.save(self.m.WORK / 'dry-run.json', {'returncode': 0})

    def build_guard(self, message):
        argv = ['tool.py', 'build', '--package-root', str(self.args.package_root),
                '--sdk', str(self.args.sdk), '--work-dir', str(self.args.work_dir),
                '--base-apk', str(self.args.base_apk), '--image', self.args.image,
                '--jobs', str(self.args.jobs)]
        with patch.object(sys, 'argv', argv):
            with self.assertRaisesRegex(RuntimeError, message):
                self.m.main()

    def test_normal_preparation_and_pch_stamp(self):
        original = (self.core / '.obj/core.o').read_bytes()
        self.prepare()
        flags = (self.m.CONTROL / 'optimization.mk').read_text()
        self.assertIn('CFLAGS += -O2\nCXXFLAGS += -O2', flags)
        self.assertIn('c.pch', flags)
        self.assertIn('c++.pch', flags)
        self.assertNotIn('NDEBUG', flags)
        self.assertNotIn('QT_NO_DEBUG', flags)
        stamp_time = (self.m.CONTROL / 'optimization.stamp').stat().st_mtime
        self.assertGreater(stamp_time, (self.m.CORE / '.pch/Qt5Core_arm64-v8a.pch/c++.pch').stat().st_mtime)
        (self.m.CORE / '.obj/core.o').write_text('modified independent copy')
        self.assertEqual((self.core / '.obj/core.o').read_bytes(), original)
        self.assertNotEqual((self.core / '.obj/core.o').stat().st_ino,
                            (self.m.CORE / '.obj/core.o').stat().st_ino)
        command = self.m.command(False)
        self.assertIn(IMAGE_A, command)
        self.assertIn(str(self.m.CONAN) + ':/fixture/conan:ro', command)
        self.assertIn(str(self.sdk) + ':/opt/android-sdk:ro', command)
        self.assertIn('--read-only', command)
        self.assertEqual(command[-1], '../../lib/libQt5Core_arm64-v8a.so')
        self.assertIn('-o', command)
        self.assertNotIn('-B', command)
        self.assertNotIn('install', command)
        self.assertEqual(json.loads((self.m.WORK / 'prepared.json').read_text())['baseline'], self.m.identity())

    def test_work_disjoint_from_conan_and_sdk(self):
        for bad in [self.root / 'conan/work', self.sdk / 'work', self.root]:
            with self.subTest(bad=bad):
                self.args.work_dir = bad
                with self.assertRaisesRegex(RuntimeError, 'disjoint'):
                    self.m.configure(self.args)

    def test_work_symlink_rejected(self):
        destination = self.root / 'external'
        destination.mkdir()
        self.args.work_dir.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'symlink'):
            self.m.configure(self.args)

    def test_pch_directory_escape_rejected(self):
        shutil.rmtree(self.core / '.pch')
        outside = self.root / 'outside'
        outside.mkdir()
        (self.core / '.pch').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'escapes isolated copy'):
            self.prepare()

    def test_pch_nested_output_escape_rejected(self):
        file = self.core / '.pch/Qt5Core_arm64-v8a.pch/c++.pch'
        file.unlink()
        outside = self.root / 'outside-pch'
        outside.write_text('protected')
        file.symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, 'Generated output path escapes'):
            self.prepare()
        self.assertEqual(outside.read_text(), 'protected')

    def test_original_source_mutation_rejected(self):
        self.prepare()
        (self.package / 'b/qt5/qtbase/src/corelib/core.cpp').write_text('different source')
        self.build_guard('Original Qt inputs changed')

    def test_original_makefile_mutation_rejected(self):
        self.prepare()
        with (self.core / 'Makefile').open('a') as stream:
            stream.write('# changed\n')
        self.build_guard('Original Qt inputs changed')

    def test_image_change_rejected(self):
        self.prepare()
        self.image = IMAGE_B
        self.build_guard('Container image changed')

    def test_jobs_change_rejected(self):
        self.prepare()
        self.args.jobs = 3
        self.build_guard('Original Qt inputs changed')

    def test_baseline_apk_change_rejected(self):
        self.prepare()
        with zipfile.ZipFile(self.apk, 'a') as archive:
            archive.writestr('extra', b'changed baseline')
        self.build_guard('Original Qt inputs changed')

    def test_compiler_change_rejected(self):
        self.prepare()
        (self.sdk / 'ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin/clang').write_text('new compiler')
        self.build_guard('Original Qt inputs changed')

    def test_assertions_disabled_rejected(self):
        self.m.configure(self.args)
        original = (self.core / 'Makefile').read_text()
        for variable in ['DEFINES', 'CFLAGS', 'CXXFLAGS']:
            for flag in ['-DQT_NO_DEBUG', '-DNDEBUG', '-D QT_NO_DEBUG=1']:
                with self.subTest(variable=variable, flag=flag):
                    text = original.replace(variable + ' = ', variable + ' = ' + flag + ' ')
                    (self.core / 'Makefile').write_text(text)
                    with self.assertRaisesRegex(RuntimeError, 'disables assertions'):
                        self.m.guard()

    def test_already_optimized_baseline_rejected(self):
        self.m.configure(self.args)
        text = (self.core / 'Makefile').read_text().replace('CFLAGS = -g', 'CFLAGS = -O2 -g')
        (self.core / 'Makefile').write_text(text)
        with self.assertRaisesRegex(RuntimeError, 'already specifies optimization'):
            self.m.guard()

    def test_missing_dry_run_rejected(self):
        self.m.configure(self.args)
        self.build_guard('Successful dry-run is required')

    def test_post_prepare_pch_escape_rejected(self):
        self.prepare()
        target = self.m.CORE / '.pch/Qt5Core_arm64-v8a.pch/c++.pch'
        target.unlink()
        external = self.root / 'external-pch'
        external.write_text('preserved')
        target.symlink_to(external)
        self.build_guard('Generated output path escapes')
        self.assertEqual(external.read_text(), 'preserved')

    def test_elf_api_ignores_function_addresses_sizes_and_undefined_symbols(self):
        self.m.configure(self.args)
        original = self.m.elf_identity(self.apk)
        modified = ELF_TEXT.replace('0000000000100000 55 FUNC', '0000000000990000 12 FUNC').replace('UND malloc', 'UND free')
        with patch.object(self.m.subprocess, 'check_output', return_value=modified):
            self.m.require_same_abi(original, self.m.elf_identity(self.apk))
        self.assertEqual(len(original['exports']), 2)

    def test_elf_incompatible_changes_rejected(self):
        self.m.configure(self.args)
        original = self.m.elf_identity(self.apk)
        for old, new in [('AArch64', 'X86-64'), ('ELF64', 'ELF32'),
                         ('libQt5Core_arm64-v8a.so', 'wrong.so'),
                         ('exported_function', 'missing_function'), ('8 OBJECT', '16 OBJECT'),
                         ('libc.so', 'libdifferent.so')]:
            with self.subTest(change=new):
                with patch.object(self.m.subprocess, 'check_output', return_value=ELF_TEXT.replace(old, new)):
                    with self.assertRaisesRegex(RuntimeError, 'ABI mismatch'):
                        self.m.require_same_abi(original, self.m.elf_identity(self.apk))

    def test_only_known_unreferenced_internal_weak_export_may_disappear(self):
        self.m.configure(self.args)
        base = self.m.elf_identity(self.apk)
        before = dict(base, exports=base['exports'] + [[self.m.OPTIONAL_INTERNAL_EXPORT, 'OBJECT', 'WEAK', 'DEFAULT', 64]])
        delta = self.m.require_same_abi(before, base)
        self.assertEqual(delta['removed_exports'], [self.m.OPTIONAL_INTERNAL_EXPORT])
        self.m.verify_optional_export_consumers(delta)
        strong = dict(base, exports=base['exports'] + [[self.m.OPTIONAL_INTERNAL_EXPORT, 'OBJECT', 'GLOBAL', 'DEFAULT', 64]])
        with self.assertRaisesRegex(RuntimeError, 'unexpectedly strong'):
            self.m.require_same_abi(strong, base)
        unknown = dict(base, exports=base['exports'] + [['some_other_weak_export', 'FUNC', 'WEAK', 'DEFAULT', None]])
        with self.assertRaisesRegex(RuntimeError, 'ABI mismatch: exports'):
            self.m.require_same_abi(unknown, base)

    def test_internal_export_exception_rejects_apk_consumer(self):
        self.m.configure(self.args)
        with zipfile.ZipFile(self.apk, 'a') as archive:
            archive.writestr('lib/arm64-v8a/consumer.so', self.m.OPTIONAL_INTERNAL_EXPORT.encode())
        imported = ELF_TEXT.replace('UND malloc', 'UND ' + self.m.OPTIONAL_INTERNAL_EXPORT)
        with patch.object(self.m.subprocess, 'check_output', return_value=imported):
            with self.assertRaisesRegex(RuntimeError, 'imports omitted QtCore internal export'):
                self.m.verify_optional_export_consumers({'removed_exports': [self.m.OPTIONAL_INTERNAL_EXPORT], 'added_exports': []})

    def compiler_log(self):
        compiler = '/opt/android-sdk/ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin/clang'
        return (compiler + ' -target aarch64-linux-android26 -O2 -x c-header -c input.h -o c.pch\n'
                + compiler + '++ -target aarch64-linux-android26 -O2 -x c++-header -c input.h -o cxx.pch\n'
                + compiler + '++ -target aarch64-linux-android26 -O2 -c file.cpp -o file.o\n')

    def test_actual_compiler_log_provenance(self):
        log = self.root / 'compiler.log'
        log.write_text(self.compiler_log())
        identity = self.m.compiler_provenance(log)
        self.assertEqual(identity['compile_commands'], 3)
        self.assertEqual(identity['pch_languages'], ['c++-header', 'c-header'])
        # Parallel build ordering has no effect on the command identity.
        log.write_text('\n'.join(reversed(self.compiler_log().splitlines())) + '\n')
        self.assertEqual(self.m.compiler_provenance(log)['commands_sha256'], identity['commands_sha256'])

    def test_compiler_log_rejects_assertion_optimization_target_and_missing_pch(self):
        for text, reason in [
            (self.compiler_log().replace('-O2', '-O2 -DNDEBUG'), 'disables assertions'),
            (self.compiler_log().replace('-O2', '-O2 -D QT_NO_DEBUG=1'), 'disables assertions'),
            (self.compiler_log().replace('-O2', '-O2 -O0'), 'does not end with -O2'),
            (self.compiler_log().replace('android26', 'android25'), 'changes target ABI'),
            ('\n'.join(self.compiler_log().splitlines()[1:]), r'both C and C\+\+ PCH'),
        ]:
            with self.subTest(reason=reason):
                log = self.root / 'compiler.log'
                log.write_text(text)
                with self.assertRaisesRegex(RuntimeError, reason):
                    self.m.compiler_provenance(log)

    def test_unrecognized_existing_work_preserved(self):
        self.args.work_dir.mkdir()
        (self.args.work_dir / 'valuable.txt').write_text('preserve')
        self.m.configure(self.args)
        with self.assertRaisesRegex(RuntimeError, 'Unrecognized/unfinished'):
            self.m.prepare()
        self.assertEqual((self.args.work_dir / 'valuable.txt').read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main(verbosity=2)
