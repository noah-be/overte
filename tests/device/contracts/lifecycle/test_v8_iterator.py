#!/usr/bin/env python3
"""Complete original V8 iterator class/methods; host-only V8_TEST_ROOT tooling."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest
from v8_abort_fixture import write_abort_fixture
ROOT = pathlib.Path(__file__).resolve().parents[4]


class V8Iterator(unittest.TestCase):
    def test_original_iterator_failure_and_termination_paths(self):
        prefix = pathlib.Path(os.environ["V8_TEST_ROOT"]).resolve(strict=True)
        header = (ROOT / "libraries/script-engine/src/v8/ScriptValueIteratorV8Wrapper.h").read_text()
        source = (ROOT / "libraries/script-engine/src/v8/ScriptValueIteratorV8Wrapper.cpp").read_text()
        admission_baseline = os.environ.get("OVERTE_ABORT_ADMISSION_BASELINE")
        if admission_baseline:
            source = subprocess.check_output(['git', '-C', str(ROOT), 'show',
                admission_baseline + ':libraries/script-engine/src/v8/ScriptValueIteratorV8Wrapper.cpp'], text=True)
        if os.environ.get('OVERTE_ABORT_ADMISSION_MUTATION') == '1':
            # Preserve unrelated fixes; remove only the production admission gates.
            source = '\n'.join(line for line in source.splitlines() if '_engine->isEvaluationAborted()' not in line)
        declaration = header[header.index("class V8ScriptValueIterator {"):
                             header.index("/// [V8] Implements ScriptValueIterator")]
        methods = source[source.index("V8ScriptValueIterator::V8ScriptValueIterator("):
                         source.index("ScriptValue::PropertyFlags ScriptValueIteratorV8Wrapper::flags()")]
        flags = shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","Qt6Core"],text=True))
        with tempfile.TemporaryDirectory(prefix="sh005-v8-iterator-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "v8-iterator-class.inc").write_text(declaration)
            (temporary / "v8-iterator-methods.inc").write_text(methods)
            write_abort_fixture(ROOT, temporary)
            binary = temporary / "test"
            library = prefix / "usr/lib64"
            subprocess.run(["c++","-std=c++17","-fPIC","-pthread","-I",str(temporary),
                            "-isystem",str(prefix / "usr/include/node"),
                            str(pathlib.Path(__file__).with_name("v8-iterator-test.cpp")),
                            "-L",str(library),"-Wl,-rpath," + str(library),"-lnode","-o",str(binary),*flags],
                           check=True,timeout=40)
            for mode in ("ordinary","empty","null","keys-throw","keys-terminate","getter-throw","getter-terminate","stopped","stopped-existing"):
                with self.subTest(mode=mode):
                    subprocess.run(["unshare","--user","--map-root-user","--net",str(binary),mode],
                                   check=True,timeout=5)


if __name__ == "__main__":
    unittest.main()
