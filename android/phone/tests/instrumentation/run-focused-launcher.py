#!/usr/bin/env python3
"""Offline, bounded launcher tests; reads pinned host dependencies, no Gradle."""
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile


def main():
    repo = Path(__file__).resolve().parents[4]
    phone = repo / "android/phone"
    cache = Path(os.environ.get("PHONE_TEST_MAVEN_CACHE",
                                str(Path.home() / ".gradle/caches/modules-2/files-2.1")))
    maven = Path(os.environ.get("PHONE_TEST_ANDROID_CACHE",
                                str(Path.home() / ".m2/repository/org/robolectric/android-all-instrumented")))
    jdk = Path(os.environ.get("PHONE_TEST_JDK", "/usr/lib/jvm/temurin-21-jdk"))
    lock = repo / "android/common/tests/robolectric/gradle.lockfile"
    with tempfile.TemporaryDirectory(prefix="phone-launcher-host-") as temporary:
        scratch = Path(temporary)
        classes = scratch / "classes"
        classes.mkdir()
        sdk = scratch / "sdk"
        sdk.mkdir()
        jars = []
        for line in lock.read_text().splitlines():
            if line.startswith("#") or ":" not in line:
                continue
            coordinate = line.split("=", 1)[0]
            group, artifact, version = coordinate.split(":")
            location = cache / group / artifact / version
            candidates = sorted(location.glob(f"*/{artifact}-{version}.jar"))
            if candidates:
                if len(candidates) != 1:
                    raise RuntimeError("ambiguous cached test dependency")
                jars.append(candidates[0])
                continue
            archives = sorted(location.glob(f"*/{artifact}-{version}.aar"))
            if len(archives) != 1:
                raise RuntimeError("missing cached test dependency; no network fallback")
            extracted = scratch / f"{group}-{artifact}.jar"
            with zipfile.ZipFile(archives[0]) as archive:
                extracted.write_bytes(archive.read("classes.jar"))
            jars.append(extracted)
        for version in ("8.0.0_r4-robolectric-r1-i7", "15-robolectric-13954326-i7"):
            name = f"android-all-instrumented-{version}.jar"
            source = maven / version / name
            if not source.is_file():
                raise RuntimeError("missing cached Android host runtime")
            (sdk / name).symlink_to(source)
        classpath = os.pathsep.join(str(path) for path in jars)
        sources = sorted((phone / "apps/phoneInterface/src/main/java/org/overte/phone").glob("*.java"))
        sources.append(repo / "security/redaction/java/org/overte/security/SafeDiagnostics.java")
        boundary = repo / "android/common/tests/robolectric/src/main/java"
        sources += [
            boundary / "org/qtproject/qt5/android/bindings/QtActivity.java",
            boundary / "org/overte/phone/R.java",
        ]
        qt = repo / "android/common/libraries/qt/src/main/java/io/highfidelity/utils"
        sources += [qt / name for name in
                    ("HifiUtils.java", "AssetCacheExtractor.java", "SafeAssetPath.java")]
        sources += [
            phone / "apps/phoneInterface/src/test/java/org/overte/phone/PermissionsActivityRobolectricTest.java",
            phone / "apps/phoneInterface/src/test/java/org/overte/phone/PhoneDeepLinkRobolectricTest.java",
            phone / "apps/phoneInterface/src/test/java/org/overte/phone/RedactingDiagnosticsRobolectricTest.java",
        ]
        subprocess.run([str(jdk / "bin/javac"), "--release", "17", "-proc:none",
                        "-cp", classpath, "-d", str(classes), *map(str, sources)],
                       check=True, timeout=60)
        subprocess.run([
            str(jdk / "bin/java"), "-Xmx768m",
            f"-Djava.io.tmpdir={scratch}", f"-Dorg.conscrypt.native.workdir={scratch}",
            "-Drobolectric.offline=true", f"-Drobolectric.dependency.dir={sdk}",
            "-cp", str(classes) + os.pathsep + classpath, "org.junit.runner.JUnitCore",
            "org.overte.phone.PermissionsActivityRobolectricTest",
            "org.overte.phone.PhoneDeepLinkRobolectricTest",
            "org.overte.phone.RedactingDiagnosticsRobolectricTest",
        ], check=True, timeout=110, cwd=scratch)


if __name__ == "__main__":
    main()
