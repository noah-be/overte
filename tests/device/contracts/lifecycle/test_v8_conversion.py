#!/usr/bin/env python3
"""Nine complete production conversion/comparison/name functions, real V8."""
import os
import pathlib
import re
import shlex
import subprocess
import tempfile
import unittest
from v8_abort_fixture import write_abort_fixture

ROOT = pathlib.Path(__file__).resolve().parents[4]


class V8Conversion(unittest.TestCase):
    def test_actual_functions_with_throw_termination_and_coercion(self):
        prefix = pathlib.Path(os.environ["V8_TEST_ROOT"]).resolve(strict=True)
        path = "libraries/script-engine/src/v8/ScriptValueV8Wrapper.cpp"
        baseline = os.environ.get("V8_CONVERSION_BASELINE")
        admission_baseline = os.environ.get("OVERTE_ABORT_ADMISSION_BASELINE")
        selected_baseline = admission_baseline or baseline
        source = (subprocess.check_output(["git", "show", selected_baseline + ":" + path], cwd=ROOT, text=True)
                  if selected_baseline else (ROOT / path).read_text())
        if os.environ.get('OVERTE_ABORT_ADMISSION_MUTATION') == '1':
            # Preserve unrelated fixes; remove only the production admission gates.
            source = '\n'.join(line for line in source.splitlines() if '_engine->isEvaluationAborted()' not in line)
        names = ("strictlyEquals", "getPropertyNames", "toInt32", "toInteger", "toNumber", "toString", "toUInt16", "toUInt32", "equals")
        functions = []
        for name in names:
            start = re.search(r"(?m)^(?:inline )?[^\n]+ ScriptValueV8Wrapper::" + name + r"\(", source).start()
            functions.append(source[start:].split("\n}", 1)[0] + "\n}\n")
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        with tempfile.TemporaryDirectory(prefix="sh005-v8-conversion-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "v8-conversion.inc").write_text("\n".join(functions))
            write_abort_fixture(ROOT, temporary)
            binary = temporary / "test"
            library = prefix / "usr/lib64"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread", "-DQT_NO_DEBUG", "-I", str(temporary),
                            "-isystem", str(prefix / "usr/include/node"),
                            str(pathlib.Path(__file__).with_name("v8-conversion-test.cpp")),
                            "-L", str(library), "-Wl,-rpath," + str(library), "-lnode", "-o", str(binary), *flags],
                           check=True, timeout=40)
            cases = [(kind, mode) for kind in ("int32", "integer", "number", "string", "uint16", "uint32")
                     for mode in ("ordinary", "throw", "terminate", "empty")]
            cases += [("names", mode) for mode in ("ordinary", "throw", "terminate", "empty")]
            cases += [("equals", mode) for mode in ("ordinary", "throw", "terminate", "missing", "cross", "empty")]
            cases += [("strict", mode) for mode in ("ordinary", "missing", "cross", "empty")]
            cases += [(kind, "wrap") for kind in ("int32", "uint16", "uint32")]
            cases += [("string", "nul"), ("number", "nan")]
            cases += [(kind, "stopped") for kind in ("names", "equals", "int32", "integer", "number", "string", "uint16", "uint32")]
            if baseline:
                cases = [("equals", "ordinary")] # Read-only RED: old second coercion throws/FromJust aborts.
            for kind, mode in cases:
                with self.subTest(kind=kind, mode=mode):
                    result = subprocess.run(["unshare", "--user", "--map-root-user", "--net", str(binary), kind, mode],
                                            text=True, capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
