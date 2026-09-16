#!/usr/bin/env python3
"""Real V8 bounded property-copy tests; V8_TEST_ROOT is a host-only prefix."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class V8PropertyCopy(unittest.TestCase):
    def test_actual_helper_and_original_global_snapshot(self):
        prefix = pathlib.Path(os.environ["V8_TEST_ROOT"]).resolve(strict=True)
        source = (ROOT / "libraries/script-engine/src/v8/ScriptEngineV8.cpp").read_text()
        caller = source[source.index("bool ScriptEngineV8::storeGlobalObjectContents()"):
                        source.index("ScriptValue ScriptEngineV8::evaluateInClosure(")]
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        with tempfile.TemporaryDirectory(prefix="sh005-v8-property-copy-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "v8-global-snapshot.inc").write_text(caller)
            binary = temporary / "test"
            library = prefix / "usr/lib64"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread", "-I", str(ROOT),
                            "-I", str(temporary), "-isystem", str(prefix / "usr/include/node"),
                            str(pathlib.Path(__file__).with_name("v8-property-copy-test.cpp")),
                            "-L", str(library), "-Wl,-rpath," + str(library), "-lnode",
                            "-o", str(binary), *flags], check=True, timeout=40)
            for mode in ("ordinary", "getter", "keys", "setter", "terminate", "snapshot", "snapshot-error",
                         "require-ordinary", "require-source-script", "require-source-require",
                         "require-destination-script", "require-destination-require", "require-getter",
                         "require-cache-getter", "require-terminate"):
                with self.subTest(mode=mode):
                    subprocess.run(["unshare", "--user", "--map-root-user", "--net", str(binary), mode],
                                   check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
