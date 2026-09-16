#!/usr/bin/env python3
"""Focused native/JVM integration; no Gradle, Android runtime or native app build."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
PHONE = ROOT / "android/phone"
JDK = Path(os.environ.get("PHONE_TEST_JDK", "/usr/lib/jvm/temurin-21-jdk"))
SDK = Path(os.environ.get("ANDROID_SDK_ROOT", "/home/user/Android/Sdk"))
API = Path(os.environ.get("PHONE_ANDROID_API_JAR", str(SDK / "platforms/android-26/android.jar")))

def run(*args):
    subprocess.run([str(arg) for arg in args], check=True, timeout=90)

with tempfile.TemporaryDirectory(prefix="phone-storage-jni-") as temporary:
    scratch = Path(temporary)
    classes = scratch / "classes"
    classes.mkdir()
    data = scratch / "data"
    data.mkdir()
    source = PHONE / "apps/phoneInterface/src"
    tests = PHONE / "tests/security"
    run(JDK / "bin/javac", "-proc:none", "-cp", API, "-d", classes,
        source / "main/java/org/overte/phone/SecureAccountStore.java",
        source / "main/java/org/overte/phone/RedactingDiagnostics.java",
        ROOT / "security/redaction/java/org/overte/security/SafeDiagnostics.java",
        tests / "SecureAccountStoreJniFixture.java")
    library = scratch / "libphone-storage-test.so"
    run("c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-pthread", "-shared", "-fPIC",
        "-I" + str(JDK / "include"), "-I" + str(JDK / "include/linux"),
        "-I" + str(tests / "stubs"), source / "PhoneProtectedAccountStore.cpp",
        source / "PhoneProtectedStoreRegistration.cpp", tests / "PhoneProtectedAccountStoreJniTest.cpp",
        "-o", library)
    run(JDK / "bin/java", "-Xcheck:jni", "-cp", str(classes) + os.pathsep + str(API),
        "org.overte.phone.SecureAccountStoreJniFixture", data, library)
    conformance = scratch / "coordinator-test"
    run("c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-pthread",
        ROOT / "tests/device/contracts/secure-storage/coordinator-test.cpp", "-o", conformance)
    run(conformance)
