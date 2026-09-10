#!/usr/bin/env python3
import pathlib
import os
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class VisibilityInputs(unittest.TestCase):
    def test_original_qt_publication_and_both_observer_orders(self):
        baseline = os.environ.get('OVERTE_VISIBILITY_PUBLICATION_BASELINE')
        source = (subprocess.check_output(['git', '-C', str(ROOT), 'show',
                  baseline + ':interface/src/Application_Events.cpp'], text=True)
                  if baseline else (ROOT / "interface/src/Application_Events.cpp").read_text())
        setup = (ROOT / "interface/src/Application_Setup.cpp").read_text()
        self.assertLess(setup.index('DependencyManager::set<DomainAccountManager>();'),
                        setup.index('overte::lifecycle::observeQtVisibility('))
        publication = "namespace {\nvoid publishClientVisibility(" + source.split(
            "namespace {\nvoid publishClientVisibility(", 1)[1].split(
            "\nvoid Application::activeChanged(", 1)[0]
        flags = shlex.split(subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "Qt6Core", "Qt6Network"], text=True))
        with tempfile.TemporaryDirectory(prefix="sh005-visibility-inputs-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "visibility-publication.inc").write_text(publication)
            driver = pathlib.Path(__file__).with_name("visibility-inputs-test.cpp")
            binary = temporary / "test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread", "-I", str(ROOT),
                            "-I", str(temporary), str(driver), "-o", str(binary), *flags], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=5)

    def test_qt_authority_without_native_adapter(self):
        with tempfile.TemporaryDirectory(prefix="sh005-visibility-pure-") as temporary:
            binary = pathlib.Path(temporary) / "test"
            source = '''#include "interface/src/ApplicationLifecycle.h"
#include <cassert>
int main() {
    overte::lifecycle::VisibilityInputs inputs;
    assert(!inputs.effective());
    assert(inputs.observeQt(true));
    assert(!inputs.observeQt(false));
    assert(!inputs.observeNative(true));
    assert(inputs.observeQt(true));
    assert(!inputs.observeNative(false));
    assert(!inputs.observeQt(true));
}
'''
            subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                            "-x", "c++", "-", "-o", str(binary)], input=source, text=True, check=True, timeout=20)
            subprocess.run([str(binary)], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
