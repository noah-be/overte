#!/usr/bin/env python3
"""Focused real-V8 diagnostics, not full engine or consent/revoke acceptance.

V8_TEST_ROOT explicitly names a host-only Node development prefix. Its binaries
must never be fed to a qualified candidate/Cold Build.
"""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class V8ExceptionDiagnostics(unittest.TestCase):
    def test_actual_v8_metadata_and_original_diagnostic_callers(self):
        prefix = pathlib.Path(os.environ["V8_TEST_ROOT"]).resolve(strict=True)
        source = (ROOT / "libraries/script-engine/src/v8/ScriptEngineV8.cpp").read_text()
        first = source[source.index("QString getFileNameFromTryCatch("):
                       source.index("\nScriptValue ScriptEngineV8::makeError(")]
        second = source[source.index("QString ScriptEngineV8::formatErrorMessageFromTryCatch("):
                        source.index("\nv8::Local<v8::ObjectTemplate> ScriptEngineV8::getObjectProxyTemplate(")]
        flags = shlex.split(subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        with tempfile.TemporaryDirectory(prefix="sh005-v8-diagnostics-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "v8-diagnostic-callers.inc").write_text(first + second)
            wrapper_header = (ROOT / "libraries/script-engine/src/v8/ScriptProgramV8Wrapper.h").read_text()
            syntax_class = wrapper_header[wrapper_header.index("class ScriptSyntaxCheckResultV8Wrapper final"):
                                          wrapper_header.index("/// [V8] Implements ScriptProgram")]
            wrapper_source = (ROOT / "libraries/script-engine/src/v8/ScriptProgramV8Wrapper.cpp").read_text()
            compile_body = wrapper_source[wrapper_source.index("bool ScriptProgramV8Wrapper::compile()") :]
            (temporary / "v8-syntax-result.inc").write_text(syntax_class)
            (temporary / "v8-program-compile.inc").write_text(compile_body)
            binary = temporary / "test"
            library = prefix / "usr/lib64"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread", "-I", str(ROOT),
                            "-I", str(temporary), "-isystem", str(prefix / "usr/include/node"),
                            str(pathlib.Path(__file__).with_name("v8-exception-diagnostics-test.cpp")),
                            "-L", str(library), "-Wl,-rpath," + str(library), "-lnode",
                            "-o", str(binary), *flags], check=True, timeout=40)
            for mode in ("ordinary", "empty", "none", "getter", "prepare", "terminate"):
                with self.subTest(mode=mode):
                    subprocess.run(["unshare", "--user", "--map-root-user", "--net",
                                    str(binary), mode], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
