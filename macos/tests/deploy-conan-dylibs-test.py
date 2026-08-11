#!/usr/bin/env python3
"""Hermetic contract test for deploy-conan-dylibs.py."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "macos/tools/deploy-conan-dylibs.py"

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    app = root / "Overte.app"
    executable = app / "Contents/MacOS/Overte"
    executable.parent.mkdir(parents=True)
    executable.write_text("executable", encoding="utf-8")
    libraries = root / "conanlibs/Release"
    libraries.mkdir(parents=True)
    (libraries / "libaudio.2.1.dylib").write_text("audio", encoding="utf-8")
    (libraries / "libunused.dylib").write_text("unused", encoding="utf-8")
    log = root / "install-name.log"

    otool = root / "otool"
    otool.write_text(
        """#!/usr/bin/env python3
import pathlib, sys
p = pathlib.Path(sys.argv[-1])
print(f"{p}:")
if p.name == "Overte":
    print("\t/lib/libaudio.2.1.dylib (compatibility version 2.0.0, current version 2.1.0)")
    print("\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1.0.0)")
elif p.name == "libaudio.2.1.dylib":
    print("\t/lib/libaudio.2.1.dylib (compatibility version 2.0.0, current version 2.1.0)")
""",
        encoding="utf-8",
    )
    install_name_tool = root / "install_name_tool"
    install_name_tool.write_text(
        """#!/usr/bin/env python3
import os, pathlib, sys
with pathlib.Path(os.environ["DEPLOY_TEST_LOG"]).open("a", encoding="utf-8") as stream:
    stream.write(" ".join(sys.argv[1:]) + "\\n")
""",
        encoding="utf-8",
    )
    otool.chmod(0o755)
    install_name_tool.chmod(0o755)
    environment = os.environ.copy()
    environment["DEPLOY_TEST_LOG"] = str(log)
    subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--app", str(app),
            "--lib-dir", str(libraries),
            "--otool", str(otool),
            "--install-name-tool", str(install_name_tool),
        ],
        check=True,
        env=environment,
    )

    frameworks = app / "Contents/Frameworks"
    assert (frameworks / "libaudio.2.1.dylib").read_text() == "audio"
    assert (frameworks / "libunused.dylib").read_text() == "unused"
    changes = log.read_text(encoding="utf-8")
    assert "-id @rpath/libaudio.2.1.dylib" in changes
    assert "-change /lib/libaudio.2.1.dylib @rpath/libaudio.2.1.dylib" in changes
    assert "/usr/lib/libSystem.B.dylib" not in changes

print("Conan dylib deployment contract valid")
