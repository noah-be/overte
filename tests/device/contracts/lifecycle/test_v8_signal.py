#!/usr/bin/env python3
"""Original complete Qt meta-call body, actual moc dispatch and Qt/V8 runtime."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class V8Signal(unittest.TestCase):
    def test_original_signal_dispatch(self):
        prefix = pathlib.Path(os.environ["V8_TEST_ROOT"]).resolve(strict=True)
        source = (ROOT / "libraries/script-engine/src/v8/ScriptObjectV8Proxy.cpp").read_text()
        admission_baseline = os.environ.get('OVERTE_ABORT_ADMISSION_BASELINE')
        if admission_baseline:
            source = subprocess.check_output(['git', '-C', str(ROOT), 'show',
                admission_baseline + ':libraries/script-engine/src/v8/ScriptObjectV8Proxy.cpp'], text=True)
        body = "int ScriptSignalV8Proxy::qt_metacall(" + source.split(
            "int ScriptSignalV8Proxy::qt_metacall(", 1)[1].split(
            "int ScriptSignalV8Proxy::discoverMetaCallIdx()", 1)[0]
        if os.environ.get('OVERTE_SIGNAL_SKIP_CONSENT_ENVIRONMENT'):
            body = body.replace('if (conn.invokeInEnvironment) { conn.invokeInEnvironment(invoke); } else { invoke(); }', 'invoke();')
        header = (ROOT / "libraries/script-engine/src/v8/ScriptObjectV8Proxy.h").read_text()
        base = "class ScriptSignalV8ProxyBase :" + header.split(
            "class ScriptSignalV8ProxyBase :", 1)[1].split("class ScriptSignalV8Proxy final", 1)[0]
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        moc = pathlib.Path(subprocess.check_output(["pkg-config", "--variable=libexecdir", "Qt6Core"], text=True).strip()) / "moc"
        with tempfile.TemporaryDirectory(prefix="sh005-v8-signal-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "signal-body.inc").write_text(body)
            (temporary / "signal-meta.h").write_text(
                "#pragma once\n#include <QObject>\nstruct ScriptValue {};\nstruct Scriptable {};\n" + base +
                "class Emitter : public QObject { Q_OBJECT\n public: signals:\n"
                "void zero(); void ping(int); void ten(int,int,int,int,int,int,int,int,int,int);\n"
                "void huge(int,int,int,int,int,int,int,int,int,int,int);\n};\n")
            subprocess.run([str(moc), str(temporary / "signal-meta.h"), "-o", str(temporary / "signal-moc.inc")], check=True, timeout=10)
            engine_header = (ROOT / 'libraries/script-engine/src/v8/ScriptEngineV8.h').read_text()
            state = next(line for line in engine_header.splitlines() if 'std::atomic<bool> _abortRequested' in line)
            state += '\n' + next(line for line in engine_header.splitlines() if 'bool isEvaluationAborted() const' in line)
            engine_source = (ROOT / 'libraries/script-engine/src/v8/ScriptEngineV8.cpp').read_text()
            abort = 'void ScriptEngineV8::abortEvaluation(' + engine_source.split('void ScriptEngineV8::abortEvaluation(', 1)[1].split('\n}', 1)[0] + '\n}\n'
            (temporary / 'abort-state.inc').write_text(state)
            (temporary / 'abort-method.inc').write_text(abort)
            binary = temporary / "test"
            library = prefix / "usr/lib64"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread", "-DQT_NO_DEBUG", "-I", str(temporary),
                            "-I", str(ROOT / "libraries/shared/src/shared"),
                            "-isystem", str(prefix / "usr/include/node"),
                            str(pathlib.Path(__file__).with_name("v8-signal-test.cpp")),
                            "-L", str(library), "-Wl,-rpath," + str(library), "-lnode", "-o", str(binary), *flags],
                           check=True, timeout=40)
            for mode in ("zero", "one", "ten", "over", "empty-callback", "null-callback", "object-callback",
                         "undefined-callback", "empty-conversion", "null-arguments", "null-argument", "throw", "terminate", "stopped", "conversion-stop", "consent-denied", "consent-allowed"):
                with self.subTest(mode=mode):
                    result = subprocess.run(["unshare", "--user", "--map-root-user", "--net", str(binary), mode],
                                            text=True, capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
