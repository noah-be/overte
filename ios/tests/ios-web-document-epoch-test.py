#!/usr/bin/env python3
"""Run actual iOS document epoch paired with the owning Shared source policy."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
shared = ROOT / "libraries/shared/src"
if not (shared / "EmbeddedWebPolicy.h").is_file():
    raise SystemExit("Shared EmbeddedWebPolicy.h must propagate from the owning parent before native endpoint integration.")
flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
flags = [part for flag in flags for part in (["-isystem", flag[2:]] if flag.startswith("-I") else [flag])]
with tempfile.TemporaryDirectory(prefix="ios-document-epoch-") as temporary:
    binary = Path(temporary) / "test"
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC",
                    "-I" + str(shared), str(Path(__file__).with_suffix(".cpp")), "-o", str(binary), *flags], check=True, timeout=60)
    subprocess.run([str(binary)], check=True, timeout=10)
print("PASS actual iOS document epoch + Shared policy: reload/redirect old-init race, foreign navigation/Back and lifecycle invalidation")
