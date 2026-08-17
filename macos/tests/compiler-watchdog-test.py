#!/usr/bin/env python3

import importlib.util
import json
import os
from pathlib import Path
import signal
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
WATCHDOG = ROOT / "macos" / "ci" / "compiler-watchdog.py"


def load_watchdog():
    spec = importlib.util.spec_from_file_location("macos_compiler_watchdog", WATCHDOG)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CompilerWatchdogTest(unittest.TestCase):
    def invoke(self, code: str, timeout: float = 2.0,
               extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["OVERTE_COMPILER_WATCHDOG_DISABLE_SCCACHE"] = "1"
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, str(WATCHDOG), "--interval", "0.05",
             "--inactivity-timeout", str(timeout), "--term-grace", "0.1", "--",
             sys.executable, "-c", code, "/secret/work/private-unit.cpp", "-o",
             "/secret/work/private-unit.o"],
            # macOS process sampling can briefly exceed five seconds on a busy
            # hosted runner; this outer harness limit must not race the
            # watchdog's much shorter, explicitly tested timeout.
            text=True, capture_output=True, env=env, timeout=15, check=False,
        )

    def test_preserves_exit_code_and_redacts_arguments_and_environment(self) -> None:
        secret = "highly-sensitive-signing-value"
        result = self.invoke("import sys; sys.exit(23)", extra_env={"SIGNING_TOKEN": secret})
        self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
        self.assertNotIn("/secret/work", result.stdout)
        self.assertNotIn(secret, result.stdout)
        records = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(records[0]["compiler_watchdog"], "start")
        self.assertEqual(records[0]["source"], "private-unit.cpp")
        self.assertEqual(records[-1]["exit_code"], 23)

    def test_forwards_cmake_preprocessor_flags_placed_before_compiler(self) -> None:
        module = load_watchdog()
        args, command = module._parse_cli([
            "--interval", "0.25", "-E", "-isysroot", "/private/macos-sdk",
            "--", "/usr/bin/clang", "-DPNG_PREFIX=1", "source.c",
        ])
        self.assertEqual(args.interval, 0.25)
        self.assertEqual(command, [
            "/usr/bin/clang", "-E", "-isysroot", "/private/macos-sdk",
            "-DPNG_PREFIX=1", "source.c",
        ])

    def test_uses_explicit_compiler_for_cmake_probe_without_separator(self) -> None:
        module = load_watchdog()
        with mock.patch.dict(os.environ, {
            "OVERTE_COMPILER_WATCHDOG_FALLBACK_COMPILER": "/usr/bin/clang"
        }):
            args, command = module._parse_cli([
                "-E", "-isysroot", "/private/macos-sdk", "source.c",
            ])
        self.assertEqual(args.interval, 30.0)
        self.assertEqual(command, [
            "/usr/bin/clang", "-E", "-isysroot", "/private/macos-sdk", "source.c",
        ])

        env = os.environ.copy()
        env.update({
            "OVERTE_COMPILER_WATCHDOG_DISABLE_SCCACHE": "1",
            "OVERTE_COMPILER_WATCHDOG_FALLBACK_COMPILER": sys.executable,
        })
        result = subprocess.run([
            sys.executable, str(WATCHDOG), "--interval", "0.05",
            "--inactivity-timeout", "2", "-c",
            "import sys; assert sys.argv[1:] == ['-E', '-isysroot', '/sdk']",
            "-E", "-isysroot", "/sdk",
        ], text=True, capture_output=True, env=env, timeout=5, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_separatorless_probe_without_explicit_compiler(self) -> None:
        module = load_watchdog()
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            module._parse_cli(["-E", "source.c"])

    def test_normalizes_compiler_signal_exit_status(self) -> None:
        result = self.invoke("import os,signal; os.kill(os.getpid(), signal.SIGTERM)")
        self.assertEqual(result.returncode, 128 + signal.SIGTERM, result.stdout + result.stderr)
        records = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(records[-1]["exit_code"], 128 + signal.SIGTERM)

    def test_signal_helpers_tolerate_finished_or_inaccessible_processes(self) -> None:
        module = load_watchdog()
        with mock.patch.object(module.os, "killpg", side_effect=PermissionError):
            module._signal_group(12345, signal.SIGKILL)
        with mock.patch.object(module.os, "kill", side_effect=PermissionError):
            module._signal_pids({12345}, signal.SIGKILL)

    def test_reports_cpu_active_long_invocation_without_stalling(self) -> None:
        result = self.invoke(
            "import time; end=time.time()+1.5\nwhile time.time()<end: pass",
            timeout=0.4,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        records = [json.loads(line) for line in result.stdout.splitlines()]
        progress = [row for row in records if row["compiler_watchdog"] == "progress"]
        self.assertTrue(progress)
        self.assertTrue(any(row["cpu_s"] > 0 or row["cpu_pct"] > 0 for row in progress))
        self.assertEqual(records[-1]["compiler_watchdog"], "end")

    def test_inactive_invocation_is_terminated_after_sanitized_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            diagnostics = root / "diagnostics"
            fake_bin.mkdir()
            sample = fake_bin / "sample"
            sample.write_text("#!/bin/sh\nprintf 'Path: /secret/work/private-unit.cpp token=leaked-value\\n'\n")
            sample.chmod(0o755)
            result = self.invoke(
                "import time; time.sleep(3)", timeout=0.15,
                extra_env={
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                    "OVERTE_COMPILER_WATCHDOG_DIAGNOSTICS": str(diagnostics),
                    "API_TOKEN": "leaked-value",
                },
            )
            self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
            records = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertTrue(any(row["compiler_watchdog"] == "stalled" for row in records))
            self.assertEqual(records[-1]["compiler_watchdog"], "end")
            self.assertEqual(records[-1]["exit_code"], 124)
            self.assertEqual(records[-1]["reason"], "inactivity")
            reports = list(diagnostics.glob("stall-*.json"))
            self.assertEqual(len(reports), 1)
            report_text = reports[0].read_text()
            self.assertNotIn("command", report_text)
            self.assertNotIn("/secret/", report_text)
            # The fake sample is only invoked when a compiler-named process is available;
            # the sanitizer itself is tested directly below for hermetic portability.

    def test_sanitizes_sample_paths_tokens_and_environment_secrets(self) -> None:
        module = load_watchdog()
        old = os.environ.get("SIGNING_PASSWORD")
        os.environ["SIGNING_PASSWORD"] = "super-private-password"
        try:
            clean = module._sanitize_sample(
                "Path: /Users/runner/work/private.mm token=abc super-private-password\n")
        finally:
            if old is None:
                os.environ.pop("SIGNING_PASSWORD", None)
            else:
                os.environ["SIGNING_PASSWORD"] = old
        self.assertNotIn("/Users/runner", clean)
        self.assertNotIn("token=abc", clean)
        self.assertNotIn("super-private-password", clean)

    def test_collects_sanitized_sample_and_process_snapshot(self) -> None:
        module = load_watchdog()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            diagnostics = root / "diagnostics"
            fake_bin.mkdir()
            sample = fake_bin / "sample"
            sample.write_text("#!/bin/sh\nprintf 'Path: /Users/runner/private.mm token=abc\\n'\n")
            sample.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            old_diagnostics = os.environ.get("OVERTE_COMPILER_WATCHDOG_DIAGNOSTICS")
            os.environ["PATH"] = f"{fake_bin}{os.pathsep}{old_path}"
            os.environ["OVERTE_COMPILER_WATCHDOG_DIAGNOSTICS"] = str(diagnostics)
            row = {"pid": os.getpid(), "ppid": os.getppid(), "cpu": 1.0,
                   "cpu_pct": 2.0, "rss": 100, "comm": "clang++",
                   "command": "clang++ /private/source.mm -o /private/source.o"}
            try:
                module._collect_diagnostics("abcdef", "source.mm", [row], [row])
            finally:
                os.environ["PATH"] = old_path
                if old_diagnostics is None:
                    os.environ.pop("OVERTE_COMPILER_WATCHDOG_DIAGNOSTICS", None)
                else:
                    os.environ["OVERTE_COMPILER_WATCHDOG_DIAGNOSTICS"] = old_diagnostics
            report = (diagnostics / "stall-abcdef.json").read_text()
            sampled = (diagnostics / f"sample-abcdef-{os.getpid()}.txt").read_text()
            self.assertNotIn("command", report)
            self.assertNotIn("/Users/runner", sampled)
            self.assertNotIn("token=abc", sampled)
            self.assertEqual((diagnostics / "stall-abcdef.json").stat().st_mode & 0o777, 0o600)

    def test_correlates_daemon_owned_compiler_by_exact_source_and_output(self) -> None:
        module = load_watchdog()
        rows = [
            {"pid": 77, "ppid": 1, "cpu": 4.0, "rss": 12, "comm": "clang++",
             "command": "clang++ '/secret/unit file.cpp' -o '/secret/unit file.o'"},
            {"pid": 78, "ppid": 1, "cpu": 4.0, "rss": 12, "comm": "clang++",
             "command": "clang++ '/secret/unit file.cpp.other' -o '/secret/unit file.o'"},
        ]
        matches = module._correlated_compilers(
            rows, "/secret/unit file.cpp", "/secret/unit file.o")
        self.assertEqual([row["pid"] for row in matches], [77])

    def test_parses_unlimited_macos_ps_args_and_derives_compiler_name(self) -> None:
        module = load_watchdog()
        rows = module._parse_snapshot(
            " 731 1 00:02.34 409600 98.7 /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang++ -c '/tmp/unit file.mm' -o '/tmp/unit file.o'\n"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["comm"], "clang++")
        self.assertEqual(rows[0]["cpu"], 2.34)
        self.assertEqual(rows[0]["rss"], 409600)
        matches = module._correlated_compilers(
            rows, "/tmp/unit file.mm", "/tmp/unit file.o")
        self.assertEqual([row["pid"] for row in matches], [731])

    def test_correlates_daemon_compiler_with_response_file(self) -> None:
        module = load_watchdog()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "unit file.cpp"
            output = root / "unit file.o"
            response = root / "compile.rsp"
            response.write_text(
                f"-c {shlex.quote(str(source))} -o {shlex.quote(str(output))}\n")
            rows = [{
                "pid": 991, "ppid": 1, "cpu": 7.0, "rss": 500000,
                "cpu_pct": 100.0, "comm": "s",
                "command": f"/usr/bin/clang++ @{shlex.quote(str(response))}",
            }]
            matches = module._correlated_compilers(rows, str(source), str(output))
            self.assertEqual([row["pid"] for row in matches], [991])

    def test_snapshot_uses_unlimited_width_args_without_comm_column(self) -> None:
        module = load_watchdog()
        completed = subprocess.CompletedProcess(
            [], 0, "12 1 00:00.50 2048 90.0 /usr/bin/clang -c unit.c -o unit.o\n", "")
        with mock.patch.object(module.subprocess, "run", return_value=completed) as run:
            rows = module._snapshot()
        self.assertEqual(rows[0]["comm"], "clang")
        self.assertEqual(
            run.call_args.args[0],
            ["ps", "-ww", "-axo", "pid=,ppid=,time=,rss=,%cpu=,args="],
        )

    def test_classifies_all_four_compiler_languages(self) -> None:
        module = load_watchdog()
        self.assertEqual(module._language("clang", ["unit.c"]), "c")
        self.assertEqual(module._language("clang++", ["unit.cpp"]), "cxx")
        self.assertEqual(module._language("clang", ["unit.m"]), "objc")
        self.assertEqual(module._language("clang++", ["unit.mm"]), "objcxx")

    def assert_process_gone(self, pid: int) -> None:
        deadline = time.monotonic() + 2
        alive = True
        while alive and time.monotonic() < deadline:
            try:
                output = subprocess.run(
                    ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True,
                    text=True, check=False).stdout.strip()
                alive = bool(output and not output.startswith("Z"))
            except OSError:
                alive = False
            time.sleep(0.02)
        self.assertFalse(alive, f"process {pid} survived signal escalation")

    def wait_for_pid(self, path: Path, timeout: float = 3.0) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                value = path.read_text().strip()
                if value.isdigit():
                    return int(value)
            except FileNotFoundError:
                pass
            time.sleep(0.02)
        self.fail(f"PID file was not populated in time: {path.name}")

    @unittest.skipUnless(hasattr(os, "killpg"), "requires POSIX process groups")
    def test_term_and_int_escalate_for_ignoring_compiler_process_group(self) -> None:
        for sent_signal in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=sent_signal):
                self._assert_ignoring_group_is_killed(sent_signal)

    def _assert_ignoring_group_is_killed(self, sent_signal: int) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            leader_file = root / "leader.pid"
            child_file = root / "child.pid"
            code = (
                "import os,pathlib,signal,subprocess,sys,time; "
                "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                "signal.signal(signal.SIGINT,signal.SIG_IGN); "
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); "
                "child=subprocess.Popen([sys.executable,'-c',"
                "'import os,pathlib,signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                "signal.signal(signal.SIGINT,signal.SIG_IGN); pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); "
                "time.sleep(30)',sys.argv[2]]); time.sleep(30)"
            )
            env = os.environ.copy()
            env["OVERTE_COMPILER_WATCHDOG_DISABLE_SCCACHE"] = "1"
            process = subprocess.Popen(
                [sys.executable, str(WATCHDOG), "--interval", "0.05", "--term-grace", "0.15", "--",
                 sys.executable, "-c", code, str(leader_file), str(child_file),
                 "unit.cpp", "-o", "unit.o"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
            )
            leader_pid = self.wait_for_pid(leader_file)
            child_pid = self.wait_for_pid(child_file)
            try:
                process.send_signal(sent_signal)
                stdout, stderr = process.communicate(timeout=3)
                self.assertEqual(process.returncode, 128 + sent_signal, stdout + stderr)
                records = [json.loads(line) for line in stdout.splitlines()]
                self.assertEqual(records[-1]["exit_code"], 128 + sent_signal)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=3)
            self.assert_process_gone(leader_pid)
            self.assert_process_gone(child_pid)

    def test_writes_private_append_only_live_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            live_log = Path(directory) / "watchdog.jsonl"
            live_log.write_text("existing\n")
            live_log.chmod(0o666)
            result = self.invoke("pass", extra_env={"OVERTE_COMPILER_WATCHDOG_LOG": str(live_log)})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            lines = live_log.read_text().splitlines()
            self.assertEqual(lines[0], "existing")
            self.assertEqual(json.loads(lines[1])["compiler_watchdog"], "start")
            self.assertEqual(json.loads(lines[-1])["compiler_watchdog"], "end")
            self.assertEqual(live_log.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
