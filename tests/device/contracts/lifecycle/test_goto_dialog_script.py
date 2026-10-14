#!/usr/bin/env python3
"""Run actual DialogsManager script QObject and goto.js against a UI boundary."""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
qt = os.environ.get("OVERTE_GOTO_TEST_QT", "Qt6")
if qt not in {"Qt5", "Qt6"}:
    raise SystemExit("OVERTE_GOTO_TEST_QT must be Qt5 or Qt6")
flags = shlex.split(subprocess.check_output(
    ["pkg-config", "--cflags", "--libs", qt + "Core", qt + "Qml"], text=True))
flags = [part for flag in flags for part in
         (["-isystem", flag[2:]] if flag.startswith("-I") else [flag])]
if qt == "Qt5" and os.environ.get("PKG_CONFIG_SYSROOT_DIR"):
    # pkgconf can omit an extracted SDK's library search flag as a system path.
    library = subprocess.check_output(
        ["pkg-config", "--variable=libdir", qt + "Core"], text=True).strip()
    flags = ["-L" + library, *flags]
tool_variable = "libexecdir" if qt == "Qt6" else "host_bins"
moc = Path(subprocess.check_output(
    ["pkg-config", "--variable=" + tool_variable, qt + "Core"], text=True).strip()) / "moc"
if not moc.is_file() and os.environ.get("PKG_CONFIG_SYSROOT_DIR"):
    moc = Path(os.environ["PKG_CONFIG_SYSROOT_DIR"]) / str(moc).lstrip("/")
production = ROOT / "interface/src/scripting"
with tempfile.TemporaryDirectory(prefix="overte-goto-script-") as temporary:
    scratch = Path(temporary)
    fixture = scratch / "goto-dialog-script-test.cpp"
    fixture.write_text((HERE / fixture.name).read_text())
    generated = []
    for header, output in [
        (fixture, scratch / "goto-dialog-script-test.moc"),
        (production / "DialogsManagerScriptingInterface.h", scratch / "moc-production.cpp"),
        (HERE / "dialogs-fixture/ui/DialogsManager.h", scratch / "moc-ui-boundary.cpp"),
    ]:
        subprocess.run([str(moc), str(header), "-o", str(output)], check=True, timeout=30)
        if output.suffix == ".cpp":
            generated.append(str(output))
    binary = scratch / "goto-dialog-script-test"
    subprocess.run([
        "c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC", "-pthread",
        "-I" + str(HERE / "dialogs-fixture"), "-I" + str(production),
        str(fixture), str(production / "DialogsManagerScriptingInterface.cpp"),
        *generated, "-o", str(binary), *flags,
    ], check=True, timeout=90)
    print(qt + " actual production script-object and GOTO lifecycle", flush=True)
    subprocess.run([str(binary), str(ROOT / "scripts/system/goto.js")], check=True, timeout=30)
