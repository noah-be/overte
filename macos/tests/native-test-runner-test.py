#!/usr/bin/env python3
"""Hermetic contracts for the cross-platform native CTest runner."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/project-native-test.sh"


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary_name:
    temporary = Path(temporary_name)
    build = temporary / "build"
    tools = temporary / "tools"
    build.mkdir()
    tools.mkdir()
    (build / "CMakeCache.txt").write_text("configured\n", encoding="utf-8")
    command_log = temporary / "commands.log"

    (tools / "nproc").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (tools / "sysctl").write_text(
        "#!/bin/sh\n[ \"$1 $2\" = '-n hw.logicalcpu' ] && printf '7\\n'\n",
        encoding="utf-8",
    )
    (tools / "cmake").write_text(
        "#!/bin/sh\nprintf 'cmake' >>\"$COMMAND_LOG\"\n"
        "for arg in \"$@\"; do printf ' <%s>' \"$arg\" >>\"$COMMAND_LOG\"; done\n"
        "printf '\\n' >>\"$COMMAND_LOG\"\n",
        encoding="utf-8",
    )
    (tools / "ctest").write_text(
        "#!/bin/sh\nprintf 'ctest' >>\"$COMMAND_LOG\"\n"
        "junit=''\n"
        "while [ $# -gt 0 ]; do\n"
        "  printf ' <%s>' \"$1\" >>\"$COMMAND_LOG\"\n"
        "  if [ \"$1\" = --output-junit ]; then shift; junit=\"$1\"; printf ' <%s>' \"$1\" >>\"$COMMAND_LOG\"; fi\n"
        "  shift\n"
        "done\n"
        "printf '\\n' >>\"$COMMAND_LOG\"\n"
        "[ -z \"$junit\" ] || printf '<testsuite tests=\"1\"/>\\n' >\"$junit\"\n",
        encoding="utf-8",
    )
    for executable in tools.iterdir():
        executable.chmod(0o755)

    junit = temporary / "reports" / "TEST-native.xml"
    environment = {
        **os.environ,
        "PATH": f"{tools}:{os.environ.get('PATH', '')}",
        "COMMAND_LOG": str(command_log),
        "OVERTE_TEST_BUILD_CONFIG": "RelWithDebInfo",
        "OVERTE_TEST_JUNIT": str(junit),
    }
    completed = subprocess.run(
        [str(RUNNER), str(build)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "cmake <--build>" in commands
    assert "<--target> <all-tests>" in commands
    assert "<--parallel> <7>" in commands
    assert "ctest <--test-dir>" in commands
    assert "<-C> <RelWithDebInfo>" in commands
    assert f"<--output-junit> <{junit}>" in commands
    assert junit.read_text(encoding="utf-8") == '<testsuite tests="1"/>\n'

    invalid = subprocess.run(
        [str(RUNNER), str(build)],
        cwd=ROOT,
        env={**environment, "OVERTE_TEST_JOBS": "many"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert invalid.returncode == 2
    assert "OVERTE_TEST_JOBS must be positive" in invalid.stderr

    symlink = temporary / "linked.xml"
    symlink.symlink_to(temporary / "target.xml")
    linked = subprocess.run(
        [str(RUNNER), str(build)],
        cwd=ROOT,
        env={**environment, "OVERTE_TEST_JOBS": "2", "OVERTE_TEST_JUNIT": str(symlink)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert linked.returncode == 2
    assert "refusing a symlinked JUnit report" in linked.stderr

print("macOS native test runner contract valid")
