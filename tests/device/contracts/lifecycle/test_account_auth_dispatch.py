#!/usr/bin/env python3
"""Execute the actual Application account-auth binding across its target branches."""
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
source = (ROOT / "interface/src/Application_Setup.cpp").read_text()
start = source.index("        auto accountManager = DependencyManager::get<AccountManager>();")
end = source.index("        connect(accountManager.data(), &AccountManager::usernameChanged", start)
binding = source[start:end]
flags = shlex.split(subprocess.check_output(
    ["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
flags = [part for flag in flags for part in
         (["-isystem", flag[2:]] if flag.startswith("-I") else [flag])]
moc = Path(subprocess.check_output(
    ["pkg-config", "--variable=libexecdir", "Qt6Core"], text=True).strip()) / "moc"
profiles = {
    "pico-android": ["Q_OS_ANDROID", "OVERTE_PICO_SETUP"],
    "phone-android": ["Q_OS_ANDROID", "ANDROID_APP_PHONE_INTERFACE"],
    "desktop": [],
    "legacy-android": ["Q_OS_ANDROID", "EXPECT_LEGACY_ACTIVITY"],
}
with tempfile.TemporaryDirectory(prefix="overte-account-auth-") as temporary:
    scratch = Path(temporary)
    fixture = scratch / "account-auth-dispatch-test.cpp"
    fixture.write_text((HERE / fixture.name).read_text())
    subprocess.run([str(moc), str(fixture), "-o", str(fixture.with_suffix(".moc"))],
                   check=True, timeout=30)
    for name, defines in profiles.items():
        # Select only the production binding after the host Qt headers were
        # included. This exercises Android routing without pretending host Qt
        # is an Android SDK or importing its unavailable JNI headers.
        (scratch / "production-auth-dispatch.inc").write_text(
            "".join("#define " + define + "\n" for define in defines if define != "EXPECT_LEGACY_ACTIVITY") +
            binding + "".join("#undef " + define + "\n" for define in defines if define != "EXPECT_LEGACY_ACTIVITY"))
        binary = scratch / name
        subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC", "-pthread",
                        *["-D" + define for define in defines if define == "EXPECT_LEGACY_ACTIVITY"], str(fixture),
                        "-o", str(binary), *flags], check=True, timeout=60)
        print(name, flush=True)
        subprocess.run([str(binary)], check=True, timeout=10)
