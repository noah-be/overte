#!/usr/bin/env python3
"""Complete original list call/construct bodies with real V8 and Qt locks."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class V8Invocation(unittest.TestCase):
    def test_original_call_and_construct_bounds_and_failures(self):
        prefix = pathlib.Path(os.environ["V8_TEST_ROOT"]).resolve(strict=True)
        source = (ROOT / "libraries/script-engine/src/v8/ScriptValueV8Wrapper.cpp").read_text()
        admission_baseline = os.environ.get('OVERTE_ABORT_ADMISSION_BASELINE')
        if admission_baseline:
            source = subprocess.check_output(['git', '-C', str(ROOT), 'show',
                admission_baseline + ':libraries/script-engine/src/v8/ScriptValueV8Wrapper.cpp'], text=True)
        call = "ScriptValue ScriptValueV8Wrapper::call(" + source.split(
            "ScriptValue ScriptValueV8Wrapper::call(", 1)[1].split(
            "ScriptValue ScriptValueV8Wrapper::call(const ScriptValue& thisObject, const ScriptValue& arguments)", 1)[0]
        construct = "ScriptValue ScriptValueV8Wrapper::construct(const ScriptValueList& args)" + source.split(
            "ScriptValue ScriptValueV8Wrapper::construct(const ScriptValueList& args)", 1)[1].split(
            "ScriptValue ScriptValueV8Wrapper::construct(const ScriptValue& arguments)", 1)[0]
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        with tempfile.TemporaryDirectory(prefix="sh005-v8-invocation-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "v8-invocation.inc").write_text(call + construct)
            engine_header = (ROOT / 'libraries/script-engine/src/v8/ScriptEngineV8.h').read_text()
            state = next(line for line in engine_header.splitlines() if 'std::atomic<bool> _abortRequested' in line)
            state += '\n' + next(line for line in engine_header.splitlines() if 'bool isEvaluationAborted() const' in line)
            engine_source = (ROOT / 'libraries/script-engine/src/v8/ScriptEngineV8.cpp').read_text()
            entry_source = (subprocess.check_output(['git', '-C', str(ROOT), 'show',
                admission_baseline + ':libraries/script-engine/src/v8/ScriptEngineV8.cpp'], text=True)
                if admission_baseline else engine_source)
            evaluate = 'ScriptValue ScriptEngineV8::evaluate(const QString&' + entry_source.split(
                'ScriptValue ScriptEngineV8::evaluate(const QString&', 1)[1].split('\n}', 1)[0] + '\n}\n'
            (temporary / 'v8-evaluate.inc').write_text(evaluate)
            abort = 'void ScriptEngineV8::abortEvaluation(' + engine_source.split('void ScriptEngineV8::abortEvaluation(', 1)[1].split('\n}', 1)[0] + '\n}\n'
            (temporary / 'abort-state.inc').write_text(state)
            (temporary / 'abort-method.inc').write_text(abort)
            binary = temporary / "test"
            library = prefix / "usr/lib64"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread", "-DQT_NO_DEBUG", "-I", str(temporary),
                            "-isystem", str(prefix / "usr/include/node"),
                            str(pathlib.Path(__file__).with_name("v8-invocation-test.cpp")),
                            "-L", str(library), "-Wl,-rpath," + str(library), "-lnode", "-o", str(binary), *flags],
                           check=True, timeout=40)
            for kind in ("call", "construct"):
                for mode in ("zero", "limit", "over", "nonfunction", "throw", "terminate", "stopped", "empty-argument", "arrow"):
                    with self.subTest(kind=kind, mode=mode):
                        result = subprocess.run(["unshare", "--user", "--map-root-user", "--net", str(binary), kind, mode],
                                                text=True, capture_output=True, timeout=5)
                        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
