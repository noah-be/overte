"""Entire original domain-auth implementation/header with real Qt and fake transport."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class DomainAuthGeneration(unittest.TestCase):
    def test_original_domain_auth_lifecycle_and_raw_diagnostics(self):
        include_root = pathlib.Path(os.environ.get('OVERTE_DOMAIN_AUTH_BASELINE_ROOT', ROOT))
        baseline_sha = os.environ.get('OVERTE_DOMAIN_AUTH_BASELINE_SHA')
        source = (subprocess.check_output(['git', '-C', str(include_root), 'show',
                  baseline_sha + ':libraries/networking/src/DomainAccountManager.cpp'], text=True)
                  if baseline_sha else (include_root / 'libraries/networking/src/DomainAccountManager.cpp').read_text())
        # Replace dependency includes only; retain ALL original methods verbatim.
        methods = '\n'.join(line for line in source.splitlines() if not line.startswith('#include'))
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Network'], text=True))
        libexec = subprocess.check_output(['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip()
        with tempfile.TemporaryDirectory(prefix='overte-domain-auth-') as temporary:
            directory = pathlib.Path(temporary)
            (directory / 'DependencyManager.h').write_text('''#pragma once
class Dependency { public: virtual ~Dependency() = default; };
struct DependencyManager { template<class T> static T* get() { static T instance; return &instance; } };
''')
            (directory / 'domain-methods.inc').write_text(methods)
            # Actual production header and its Q_OBJECT/signals, not a field rewrite.
            subprocess.run([str(pathlib.Path(libexec) / 'moc'), '-I', str(directory),
                            str(include_root / 'libraries/networking/src/DomainAccountManager.h'),
                            '-o', str(directory / 'moc.cpp')], check=True, timeout=15)
            binary = directory / 'domain-test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(include_root), '-I', str(directory),
                            '-include', 'QtCore/QtCore', str(directory / 'moc.cpp'),
                            str(pathlib.Path(__file__).with_name('domain-auth-generation-test.cpp')),
                            '-o', str(binary), *flags], check=True, timeout=45)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)], check=True, timeout=5)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary), 'timeout'], check=True, timeout=20)


if __name__ == '__main__':
    unittest.main()
