#!/usr/bin/env python3
"""Exercise safe app staging; no simulator executable or native build is invoked."""
import plistlib
from pathlib import Path
import stat
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/candidate"))
from run_simulator_candidate import stage_archive

def package(path, extra=None, platform="iPhoneSimulator"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Overte.app/Info.plist", plistlib.dumps(dict(
            CFBundleExecutable="Overte", CFBundlePackageType="APPL",
            CFBundleSupportedPlatforms=[platform], CFBundleIdentifier="org.overte.fixture")))
        executable = zipfile.ZipInfo("Overte.app/Overte")
        executable.external_attr = (stat.S_IFREG | 0o755) << 16
        archive.writestr(executable, b"synthetic-not-a-native-binary")
        if extra:
            archive.writestr(*extra)

with tempfile.TemporaryDirectory(prefix="ios-stage-tests-") as temporary:
    root = Path(temporary)
    archive = root / "candidate.zip"
    destination = root / "positive"
    destination.mkdir()
    package(archive)
    app, bundle = stage_archive(archive, destination)
    assert app.name == "Overte.app" and bundle == "org.overte.fixture"
    assert (app / "Overte").read_bytes() == b"synthetic-not-a-native-binary"
    changed = root / "changed"
    changed.mkdir()
    try:
        stage_archive(archive, changed, "0" * 64)
        raise AssertionError("unbound producer bytes accepted")
    except ValueError as error:
        assert str(error) == "ARCHIVE_BINDING_CHANGED"
    bad_link = zipfile.ZipInfo("Overte.app/link")
    bad_link.external_attr = (stat.S_IFLNK | 0o777) << 16
    for index, extra in enumerate([
        ("../escape", "bad"), ("/absolute", "bad"), ("Other.app/a", "bad"),
        ("Overte.app/overte", "alias"), (bad_link, "../outside"),
        ("Overte.app/dir\\escape", "bad"),
    ]):
        package(archive, extra)
        target = root / str(index)
        target.mkdir()
        try:
            stage_archive(archive, target)
            raise AssertionError("unsafe archive accepted")
        except ValueError:
            pass
    target = root / "device"
    target.mkdir()
    package(archive, platform="iPhoneOS")
    try:
        stage_archive(archive, target)
        raise AssertionError("device app accepted as simulator")
    except ValueError:
        pass
print("PASS exact app staging paths, case aliases, symlinks and platform negatives; no native execution")
