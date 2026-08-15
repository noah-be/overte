#!/usr/bin/env python3
"""Hermetic fail-closed tests for incremental macOS DEV bundle deployment."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "macos/tools/deploy-macos-dev-bundle.py"


def write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary_name:
    temporary = Path(temporary_name)
    app = temporary / "Overte.app"
    executable = app / "Contents/MacOS/Overte"
    executable.parent.mkdir(parents=True)
    executable.write_text("freshly linked executable", encoding="utf-8")
    (app / "Contents/Info.plist").write_text("plist", encoding="utf-8")

    internal = temporary / "build/lib/libinternal.dylib"
    internal.parent.mkdir(parents=True)
    internal.write_text("internal-v1", encoding="utf-8")
    conan = temporary / "build/conanlibs/Release"
    conan.mkdir(parents=True)
    conan_package_binary = temporary / "package/libconan.dylib"
    conan_package_binary.parent.mkdir(parents=True)
    conan_package_binary.write_text("conan-v1", encoding="utf-8")
    (conan / "libconan.dylib").symlink_to(conan_package_binary)
    qml = temporary / "source/interface/resources/qml"
    qml.mkdir(parents=True)
    (qml / "Root.qml").write_text("import QtQuick 2.12\n", encoding="utf-8")

    qt_root = temporary / "qt"
    qt_binary = qt_root / "lib/QtCore.framework/Versions/5/QtCore"
    qt_binary.parent.mkdir(parents=True)
    qt_binary.write_text("qt-core-v1", encoding="utf-8")
    log = temporary / "deploy.log"

    macdeployqt = qt_root / "bin/macdeployqt"
    macdeployqt.parent.mkdir(parents=True)
    write_executable(
        macdeployqt,
        """#!/usr/bin/env python3
import os, pathlib, shutil, sys
app = pathlib.Path(sys.argv[1])
frameworks = app / "Contents/Frameworks"
destination = frameworks / "QtCore.framework/Versions/5/QtCore"
with pathlib.Path(os.environ["DEPLOY_LOG"]).open("a", encoding="utf-8") as stream:
    stream.write("macdeployqt existing=" + str(destination.exists()).lower() + "\\n")
if os.environ.get("MACDEPLOYQT_FAIL") == "1":
    raise SystemExit(9)
destination.parent.mkdir(parents=True, exist_ok=True)
if os.environ.get("MACDEPLOYQT_MUTATE_STABLE") == "1":
    destination.write_text("unexpected-macdeployqt-mutation", encoding="utf-8")
else:
    shutil.copy2(os.environ["QT_BINARY"], destination)
internal = pathlib.Path(os.environ["INTERNAL_DYLIB"])
shutil.copy2(internal, frameworks / internal.name)
""",
    )
    deploy_conan = temporary / "deploy-conan.py"
    write_executable(
        deploy_conan,
        """#!/usr/bin/env python3
import pathlib, shutil, sys, os
app = pathlib.Path(sys.argv[sys.argv.index("--app") + 1])
libraries = pathlib.Path(sys.argv[sys.argv.index("--lib-dir") + 1])
frameworks = app / "Contents/Frameworks"
frameworks.mkdir(parents=True, exist_ok=True)
preserve = "--preserve-existing" in sys.argv
for source in libraries.glob("*.dylib*"):
    destination = frameworks / source.name
    if not preserve or not destination.exists():
        shutil.copy2(source, destination)
with pathlib.Path(os.environ["DEPLOY_LOG"]).open("a", encoding="utf-8") as stream:
    stream.write("deploy-conan preserve=" + str(preserve).lower() + "\\n")
""",
    )
    otool = temporary / "otool"
    write_executable(
        otool,
        """#!/usr/bin/env python3
import os, pathlib, sys
if os.environ.get("OTOOL_FAIL") == "1":
    raise SystemExit(1)
path = pathlib.Path(sys.argv[-1])
internal = pathlib.Path(os.environ["INTERNAL_DYLIB"])
if sys.argv[1] == "-l":
    if path.name in ("Overte", internal.name):
        print("Load command 1")
        print("          cmd LC_RPATH")
        print("      cmdsize 48")
        print("         path @executable_path/../Frameworks (offset 12)")
        print("Load command 2")
        print("          cmd LC_RPATH")
        print("      cmdsize 48")
        print(f"         path {internal.parent} (offset 12)")
    raise SystemExit(0)
print(f"{path}:")
if path.name == "Overte":
    print("\\t@rpath/libinternal.dylib (compatibility version 1.0.0, current version 1.0.0)")
    print("\\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1.0.0)")
elif path == internal:
    print("\\t@rpath/libinternal.dylib (compatibility version 1.0.0, current version 1.0.0)")
    print("\\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1.0.0)")
""",
    )
    install_name_tool = temporary / "install_name_tool"
    write_executable(install_name_tool, "#!/bin/sh\nexit 0\n")
    stamp = temporary / "state/deploy-stamp.json"
    environment = os.environ.copy()
    environment.update({
        "DEPLOY_LOG": str(log),
        "QT_BINARY": str(qt_binary),
        "INTERNAL_DYLIB": str(internal),
    })

    command = [
        sys.executable,
        str(TOOL),
        "--app", str(app),
        "--executable", str(executable),
        "--qml-dir", str(qml),
        "--lib-dir", str(conan),
        "--macdeployqt", str(macdeployqt),
        "--deploy-conan-tool", str(deploy_conan),
        "--stamp", str(stamp),
        "--otool", str(otool),
        "--install-name-tool", str(install_name_tool),
    ]

    def deploy(extra_environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        current_environment = environment.copy()
        current_environment.update(extra_environment or {})
        return subprocess.run(
            command, text=True, capture_output=True, check=False, env=current_environment
        )

    runtime_resources = app / "Contents/Resources"
    runtime_script = runtime_resources / "scripts/system/runtime.js"
    runtime_script.parent.mkdir(parents=True)
    runtime_script.write_text("runtime-v1", encoding="utf-8")
    runtime_qrc = runtime_resources / "resources.rcc"
    runtime_qrc.write_text("rcc-v1", encoding="utf-8")

    stale = app / "Contents/Frameworks/stale.dylib"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")
    (stale.parent / "libinternal.dylib").write_text(
        "stale-bundled-internal", encoding="utf-8"
    )
    first = deploy()
    assert first.returncode == 0, first.stderr + first.stdout
    assert "mode=full reason=missing-or-invalid-stamp" in first.stdout
    assert not stale.exists()
    stamp_text = stamp.read_text(encoding="utf-8")
    manifest = json.loads(stamp_text)
    assert manifest["schema_version"] == 1
    assert len(manifest["input_sha256"]) == 64
    assert str(temporary) not in stamp_text
    assert stamp.stat().st_mode & 0o777 == 0o600

    executable.write_text("new code, identical dependencies", encoding="utf-8")
    second = deploy()
    assert second.returncode == 0, second.stderr + second.stdout
    assert "mode=incremental reason=verified-inputs-and-bundle" in second.stdout
    assert log.read_text(encoding="utf-8").splitlines()[-2:] == [
        "macdeployqt existing=true", "deploy-conan preserve=true",
    ]

    runtime_script.write_text("runtime-v2", encoding="utf-8")
    runtime_qrc.write_text("rcc-v2", encoding="utf-8")
    changed_application_resources = deploy()
    assert changed_application_resources.returncode == 0
    assert (
        "mode=incremental reason=verified-inputs-and-bundle"
        in changed_application_resources.stdout
    )

    internal.write_text("internal-v2", encoding="utf-8")
    changed_internal = deploy()
    assert changed_internal.returncode == 0
    assert "mode=full reason=deployment-input-changed" in changed_internal.stdout
    assert log.read_text(encoding="utf-8").splitlines()[-2] == "macdeployqt existing=false"

    qt_binary.write_text("qt-core-v2", encoding="utf-8")
    changed_qt = deploy()
    assert changed_qt.returncode == 0
    assert "mode=full reason=deployment-input-changed" in changed_qt.stdout

    (conan / "libconan.dylib").write_text("conan-v2", encoding="utf-8")
    changed_conan = deploy()
    assert changed_conan.returncode == 0
    assert "mode=full reason=deployment-input-changed" in changed_conan.stdout

    (qml / "Root.qml").write_text("import QtQuick 2.15\n", encoding="utf-8")
    changed_qml = deploy()
    assert changed_qml.returncode == 0
    assert "mode=full reason=deployment-input-changed" in changed_qml.stdout

    bundled_qt = app / "Contents/Frameworks/QtCore.framework/Versions/5/QtCore"
    bundled_qt.unlink()
    missing_output = deploy()
    assert missing_output.returncode == 0
    assert "mode=full reason=bundle-state-changed" in missing_output.stdout
    assert bundled_qt.read_text(encoding="utf-8") == "qt-core-v2"

    bundled_qt.write_text("tampered", encoding="utf-8")
    stale_output = deploy()
    assert stale_output.returncode == 0
    assert "mode=full reason=bundle-state-changed" in stale_output.stdout
    assert bundled_qt.read_text(encoding="utf-8") == "qt-core-v2"

    external_frameworks = temporary / "external-frameworks"
    external_frameworks.mkdir()
    (external_frameworks / "must-survive").write_text("external", encoding="utf-8")
    shutil.rmtree(app / "Contents/Frameworks")
    (app / "Contents/Frameworks").symlink_to(external_frameworks, target_is_directory=True)
    symlinked_output = deploy()
    assert symlinked_output.returncode == 0
    assert "mode=full reason=bundle-state-changed" in symlinked_output.stdout
    assert not (app / "Contents/Frameworks").is_symlink()
    assert (external_frameworks / "must-survive").read_text(encoding="utf-8") == "external"

    stamp.write_text("not-json", encoding="utf-8")
    invalid_stamp = deploy()
    assert invalid_stamp.returncode == 0
    assert "mode=full reason=missing-or-invalid-stamp" in invalid_stamp.stdout

    inspection_failure = deploy({"OTOOL_FAIL": "1"})
    assert inspection_failure.returncode == 0
    assert "mode=full reason=dependency-inspection-incomplete" in inspection_failure.stdout
    assert not stamp.exists(), "unprovable input state must not create a reusable stamp"

    recovered = deploy()
    assert recovered.returncode == 0
    assert "mode=full reason=missing-or-invalid-stamp" in recovered.stdout
    assert stamp.exists()

    mutated_incremental = deploy({"MACDEPLOYQT_MUTATE_STABLE": "1"})
    assert mutated_incremental.returncode == 0
    assert "fallback=full reason=incremental-mutated-stable-bundle" in mutated_incremental.stdout
    assert "complete mode=full reason=incremental-mutated-stable-bundle" in mutated_incremental.stdout
    assert log.read_text(encoding="utf-8").splitlines()[-3:] == [
        "macdeployqt existing=true",
        "macdeployqt existing=false",
        "deploy-conan preserve=false",
    ]

    failed_tool = deploy({"MACDEPLOYQT_FAIL": "1"})
    assert failed_tool.returncode != 0
    assert not stamp.exists(), "a failed incremental deployment must invalidate the stamp"

    missing_qml = qml.with_name("qml-missing")
    qml.rename(missing_qml)
    invalid_inputs = deploy()
    assert invalid_inputs.returncode != 0
    assert "QML deployment input is missing" in invalid_inputs.stderr
    assert not stamp.exists()

print("macOS incremental DEV bundle deployment contract valid")
