#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real Qt consumer + publisher round trip, corruption and rollback checks."""
import asyncio
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("development_sync", ROOT / "ios/tools/development-sync.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


async def exercise(work, executable):
    repo, documents = work / "repo", work / "Documents"
    qml = repo / "interface/resources/qml"
    (qml / "+ios").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (qml / "NewModule").mkdir()
    (qml / "NewModule/qmldir").write_text('singleton Extra 1.0 Extra.qml\n')
    (qml / "NewModule/Extra.qml").write_text('pragma Singleton\nimport QtQml\nQtObject { property int value: 7 }\n')
    (qml / "Root.qml").write_text('import QtQml\nimport "NewModule"\nimport "Helper.js" as Helper\nQtObject { property int answer: child.value + Helper.value() + Extra.value; property Child child: Child {} }\n')
    (qml / "Child.qml").write_text('import QtQml\nQtObject { property int value: 1 }\n')
    (qml / "+ios/Child.qml").write_text('import QtQml\nQtObject { property int value: 40 }\n')
    (qml / "Helper.js").write_text('function value() { return 3; }\n')
    (repo / "scripts/defaultScripts.js").write_text('Script.include("child.js");\n')
    (repo / "scripts/child.js").write_text('var child = 7;\n')
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "--allow-empty", "-qm", "test"], check=True)
    result = sync.pack(repo, work / "packs")
    package = work / "packs" / result["revision"]
    transport = sync.LocalDocuments(documents)

    def consume(state):
        subprocess.run([str(executable), str(documents), state], check=True, timeout=15)

    consume("bundled")
    pushed = await sync.push(transport, package)
    assert pushed["uploaded"] == 8 and pushed["state"] == "restart-required"
    pushed = await sync.push(transport, package)
    assert pushed["uploaded"] == 0 and pushed["reused"] == 8
    consume("selected")
    consume("bundled")  # C++ requested disable; active objects stayed pinned.
    await sync.activate(transport, result["revision"])
    consume("selected")  # rollback reuses intact older revision

    await sync.activate(transport, result["revision"])
    active = json.loads(await transport.read(sync.BASE + "/active.json"))
    active["installation"] = "0" * 64
    await sync.atomic_json(transport, sync.BASE + "/active.json", active)
    consume("rejected")  # stale overrides cannot silently survive installation

    await sync.activate(transport, result["revision"])
    member = documents / sync.BASE / "revisions" / result["revision"] / "scripts/child.js"
    member.write_text("corrupt")
    consume("rejected")
    try:
        await sync.push(transport, package)
        raise AssertionError("sealed corrupt revision overwritten")
    except ValueError as error:
        assert "corrupt" in str(error)
    member.unlink()
    member.symlink_to(package / "scripts/child.js")
    consume("rejected")

    # An interrupted transfer never changes the previous activation request.
    class BrokenTransport(sync.LocalDocuments):
        async def write(self, name, data):
            if name.endswith("Helper.js"):
                raise OSError("simulated disconnect")
            await super().write(name, data)
    other = work / "Interrupted"
    broken = BrokenTransport(other)
    cap = await transport.read(sync.BASE + "/capabilities.json")
    await broken.write(sync.BASE + "/capabilities.json", cap)
    try:
        await sync.push(broken, package)
        raise AssertionError("interrupted transfer succeeded")
    except OSError:
        pass
    assert await broken.read(sync.BASE + "/active.json") is None
    assert (await sync.push(sync.LocalDocuments(other), package))["reused"] > 0

    manifest = json.loads((package / "manifest.json").read_bytes())
    manifest["files"]["scripts/../../escape.js"] = "0" * 64
    (package / "manifest.json").write_bytes(sync.encode(manifest))
    try:
        await sync.push(transport, package)
        raise AssertionError("traversal accepted")
    except ValueError:
        pass
    print("PASS: Qt QML/JS/selector execution, script-root snapshot, rollback, install binding, corruption, symlink, disconnect/resume, traversal")


def main():
    if not shutil.which("pkg-config") or subprocess.run(["pkg-config", "--exists", "Qt6Qml"], check=False).returncode:
        raise SystemExit("Qt6Qml development files required for executable reload test")
    with tempfile.TemporaryDirectory(prefix="overte-development-test-") as temporary:
        work = Path(temporary)
        # Baseline qrc files exercise replacements while leaving logical URLs
        # intact. A real qrc, not a URL-validation-only mock.
        (work / "Baseline.qml").write_text('import QtQml\nQtObject { property int value: -1 }\n')
        (work / "baseline.qrc").write_text('<RCC><qresource prefix="/qml"><file alias="Root.qml">Baseline.qml</file><file alias="Child.qml">Baseline.qml</file></qresource></RCC>')
        libexec = subprocess.check_output(["pkg-config", "--variable=libexecdir", "Qt6Core"], text=True).strip()
        rcc = shutil.which("rcc") or str(Path(libexec) / "rcc")
        subprocess.run([rcc, str(work / "baseline.qrc"), "-o", str(work / "qrc.cpp")], check=True)
        flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Qml"], text=True).split()
        executable = work / "test"
        subprocess.run(["c++", "-std=c++17", "-fPIC", str(ROOT / "ios/tests/development-reload-test.cpp"),
                        str(work / "qrc.cpp"), "-o", str(executable), *flags], check=True, timeout=60)
        asyncio.run(exercise(work, executable))


if __name__ == "__main__":
    main()
