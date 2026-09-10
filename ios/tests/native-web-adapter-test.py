#!/usr/bin/env python3
"""Execute actual iOS adapter and Shared process policy; UIKit boundary is test-only."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Gui"],
                                          text=True, timeout=10))
flags = [part for flag in flags for part in
         (["-isystem", flag[2:]] if flag.startswith("-I") else [flag])]
with tempfile.TemporaryDirectory(prefix="ios-native-web-") as scratch:
    binary = str(Path(scratch) / "test")
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC", "-pthread",
                    str(root / "ios/web/NativeWebAdapter.cpp"),
                    str(root / "interface/src/NativeWebPolicy.cpp"),
                    str(Path(__file__).with_suffix(".cpp")), "-o", binary, *flags],
                   check=True, timeout=60)
    subprocess.run([binary], check=True, timeout=10,
                   env=dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_RUNTIME_DIR=scratch))
print("PASS actual iOS native-web adapter and original Shared process policy; UIKit/WebKit unexecuted")
