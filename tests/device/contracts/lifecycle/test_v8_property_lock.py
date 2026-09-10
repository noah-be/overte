#!/usr/bin/env python3
"""Original named property function and real Qt lock/V8; host-only test tools."""
import os
import pathlib
import re
import shlex
import subprocess
import tempfile
import unittest
from v8_abort_fixture import write_abort_fixture

ROOT = pathlib.Path(__file__).resolve().parents[4]


class V8PropertyLock(unittest.TestCase):
    def test_actual_named_getter_releases_lock_on_every_outcome(self):
        prefix = pathlib.Path(os.environ["V8_TEST_ROOT"]).resolve(strict=True)
        path = "libraries/script-engine/src/v8/ScriptValueV8Wrapper.cpp"
        # Optional exact baseline is read-only and permits a real RED regression
        # check without changing the working tree or immutable release exports.
        baseline = os.environ.get("OVERTE_ABORT_ADMISSION_BASELINE") or os.environ.get("V8_PROPERTY_LOCK_BASELINE")
        source = (subprocess.check_output(["git", "show", baseline + ":" + path], cwd=ROOT, text=True)
                  if baseline else (ROOT / path).read_text())
        if os.environ.get('OVERTE_ABORT_ADMISSION_MUTATION') == '1':
            # Preserve unrelated fixes; remove only the production admission gates.
            source = '\n'.join(line for line in source.splitlines() if '_engine->isEvaluationAborted()' not in line)
        caller = source[source.index("ScriptValue ScriptValueV8Wrapper::property(const QString&"):
                        source.index("ScriptValue ScriptValueV8Wrapper::property(quint32")]
        data_caller = source[source.index("ScriptValue ScriptValueV8Wrapper::data() const"):
                             source.index("ScriptEnginePointer ScriptValueV8Wrapper::engine() const")]
        for name in ('hasProperty', 'prototype', 'setData', 'setProperty', 'setPrototype'):
            for match in re.finditer(r'(?m)^[^\n]+ ScriptValueV8Wrapper::' + name + r'\(', source):
                caller += source[match.start():].split('\n}', 1)[0] + '\n}\n'
        start = source.index('ScriptValue ScriptValueV8Wrapper::property(quint32')
        caller += source[start:].split('\n}', 1)[0] + '\n}\n'
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        with tempfile.TemporaryDirectory(prefix="sh005-v8-property-lock-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "v8-property-lock.inc").write_text(caller)
            (temporary / "v8-data-getter.inc").write_text(data_caller)
            write_abort_fixture(ROOT, temporary)
            binary = temporary / "test"
            library = prefix / "usr/lib64"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread", "-I", str(temporary),
                            "-isystem", str(prefix / "usr/include/node"),
                            str(pathlib.Path(__file__).with_name("v8-property-lock-test.cpp")),
                            "-L", str(library), "-Wl,-rpath," + str(library), "-lnode",
                            "-o", str(binary), *flags], check=True, timeout=40)
            cases = ("ordinary", "missing", "null", "throw", "terminate",
                         "data-ordinary", "data-missing", "data-null", "data-throw", "data-terminate", "stopped", "data-stopped")
            cases += tuple("boundary-" + operation + "-" + state for operation in
                ("index", "has", "prototype", "setname", "setindex", "setdata", "setproto") for state in ("ordinary", "stopped"))
            for mode in cases:
                with self.subTest(mode=mode):
                    result = subprocess.run(["unshare", "--user", "--map-root-user", "--net", str(binary), mode],
                                            text=True, capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn("secretProperty", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
