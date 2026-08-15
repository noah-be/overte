#!/usr/bin/env python3
"""Hermetic contract test for deploy-conan-dylibs.py."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "macos/tools/deploy-conan-dylibs.py"
MAGICS = (
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf",
    b"\xbf\xba\xfe\xca",
)
MACHO = MAGICS[3]

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    app = root / "Overte.app"
    executable = app / "Contents/MacOS/Overte"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(MACHO + b"executable")
    for index, magic in enumerate(MAGICS):
        (executable.parent / f"magic-{index}").write_bytes(magic + b"payload")
    non_macho = app / "Contents/Resources/not-a-mach-o.txt"
    non_macho.parent.mkdir(parents=True)
    non_macho.write_text("resource", encoding="utf-8")
    frameworks = app / "Contents/Frameworks"
    helper = frameworks / "QtWebEngineCore.framework/Helpers/QtWebEngineProcess.app/Contents/MacOS/QtWebEngineProcess"
    helper.parent.mkdir(parents=True)
    helper.write_bytes(MACHO + b"helper")
    qt_gui = frameworks / "QtGui.framework/Versions/5/QtGui"
    qt_gui.parent.mkdir(parents=True)
    qt_gui.write_bytes(MACHO + b"qt gui")
    libraries = root / "conanlibs/Release"
    libraries.mkdir(parents=True)
    (libraries / "libaudio.2.1.dylib").write_bytes(MACHO + b"audio")
    (libraries / "libunused.dylib").write_bytes(MACHO + b"unused")
    log = root / "install-name.log"
    otool_log = root / "otool.log"

    otool = root / "otool"
    otool.write_text(
        """#!/usr/bin/env python3
import os, pathlib, sys
p = pathlib.Path(sys.argv[-1])
if os.environ.get("OTOOL_TEST_FAIL") == p.name:
    raise SystemExit(3)
with pathlib.Path(os.environ["OTOOL_TEST_LOG"]).open("a", encoding="utf-8") as stream:
    stream.write(str(p) + "\\n")
if sys.argv[1] == "-l":
    if p.name == "QtWebEngineProcess":
        print("Load command 1")
        print("          cmd LC_RPATH")
        print("      cmdsize 48")
        print("         path @executable_path/../Frameworks (offset 12)")
    raise SystemExit(0)
print(f"{p}:")
if p.name == "Overte":
    print("\t/lib/libaudio.2.1.dylib (compatibility version 2.0.0, current version 2.1.0)")
    print("\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1.0.0)")
elif p.name == "libaudio.2.1.dylib":
    print("\t/lib/libaudio.2.1.dylib (compatibility version 2.0.0, current version 2.1.0)")
elif p.name == "QtWebEngineProcess":
    print("\t@rpath/QtGui.framework/Versions/5/QtGui (compatibility version 5.15.0, current version 5.15.2)")
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
    environment["OTOOL_TEST_LOG"] = str(otool_log)
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

    assert (frameworks / "libaudio.2.1.dylib").read_bytes() == MACHO + b"audio"
    assert (frameworks / "libunused.dylib").read_bytes() == MACHO + b"unused"
    changes = log.read_text(encoding="utf-8")
    assert "-id @rpath/libaudio.2.1.dylib" in changes
    assert "-change /lib/libaudio.2.1.dylib @rpath/libaudio.2.1.dylib" in changes
    assert "/usr/lib/libSystem.B.dylib" not in changes
    assert "-add_rpath @executable_path/../../../../.." in changes
    inspected = otool_log.read_text(encoding="utf-8")
    assert str(non_macho) not in inspected
    for index in range(len(MAGICS)):
        assert str(executable.parent / f"magic-{index}") in inspected

    deployed_audio = frameworks / "libaudio.2.1.dylib"
    deployed_audio.write_bytes(MACHO + b"transformed")
    subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--app", str(app),
            "--lib-dir", str(libraries),
            "--otool", str(otool),
            "--install-name-tool", str(install_name_tool),
            "--preserve-existing",
        ],
        check=True,
        env=environment,
    )
    assert deployed_audio.read_bytes() == MACHO + b"transformed"

    # A standalone call has no outer manifest proof and must restore the source.
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
    assert deployed_audio.read_bytes() == MACHO + b"audio"

    preserved_mtime_ns = 1_700_000_000_123_456_789
    os.utime(deployed_audio, ns=(preserved_mtime_ns, preserved_mtime_ns))
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
    assert deployed_audio.stat().st_mtime_ns == preserved_mtime_ns

    # Content hashing must refresh a same-size source change even when coarse
    # metadata could otherwise look reusable.
    (libraries / "libaudio.2.1.dylib").write_bytes(MACHO + b"Audio")
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
    assert deployed_audio.read_bytes() == MACHO + b"Audio"

    failed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--app", str(app),
            "--lib-dir", str(libraries),
            "--otool", str(otool),
            "--install-name-tool", str(install_name_tool),
        ],
        check=False,
        env={**environment, "OTOOL_TEST_FAIL": "Overte"},
    )
    assert failed.returncode != 0, "Mach-O inspection failures must fail closed"

print("Conan dylib deployment contract valid")
