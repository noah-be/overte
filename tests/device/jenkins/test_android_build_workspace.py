#!/usr/bin/env python3
"""Device-free regression tests for isolated Android build workspaces."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANAGER = HERE / "android_build_workspace.py"


def run(*command: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command), cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if check and result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result


class AndroidBuildWorkspaceTest(unittest.TestCase):
    def repository(self, parent: Path) -> Path:
        source = parent / "source"
        source.mkdir(mode=0o700)
        run("git", "init", "--quiet", cwd=source)
        run("git", "config", "user.email", "device-tests@overte.org", cwd=source)
        run("git", "config", "user.name", "Overte device tests", cwd=source)
        common_script = r'''#!/usr/bin/env bash
set -euo pipefail
role="$1"
other="$2"
artifact="$3"
mkdir -p android/common/conan/generated "$(dirname -- "$artifact")"
printf '%s\n' "$role" >android/common/conan/generated/owner
printf '%s\n%s\n%s\n%s\n' \
    "$PWD" "$CONAN_HOME" "$GRADLE_USER_HOME" "$OVERTE_ANDROID_BUILD_WORKSPACE" \
    >"$OVERTE_ANDROID_BUILD_WORKSPACE/paths"
printf '%s\n' "$role" >"$artifact"
touch "$SYNC_ROOT/$role"
count=0
while [[ ! -f "$SYNC_ROOT/$other" ]]; do
    count=$((count + 1))
    [[ "$count" -lt 500 ]] || exit 9
    sleep 0.01
done
[[ "$(cat android/common/conan/generated/owner)" == "$role" ]]
'''
        helper = source / "android/common/run-build"
        helper.parent.mkdir(parents=True)
        helper.write_text(common_script, encoding="utf-8")
        helper.chmod(0o700)
        entries = {
            "android/phone/build.sh": (
                "android-phone", "android-pico",
                "android/phone/apps/phoneInterface/build/outputs/apk/debug/"
                "phoneInterface-debug.apk",
            ),
            "android/vr/pico/build.sh": (
                "android-pico", "android-phone",
                "android/vr/pico/apps/picoInterface/build/outputs/apk/debug/"
                "picoInterface-debug.apk",
            ),
        }
        for relative, arguments in entries.items():
            entry = source / relative
            entry.parent.mkdir(parents=True, exist_ok=True)
            entry.write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\n"
                f'exec ./android/common/run-build {arguments[0]} {arguments[1]} '
                f'{arguments[2]}\n',
                encoding="utf-8",
            )
            entry.chmod(0o700)
        (source / "tracked.txt").write_text("original\n", encoding="utf-8")
        run("git", "add", ".", cwd=source)
        run("git", "commit", "--quiet", "-m", "fixture", cwd=source)
        return source

    def command(self, source: Path, build_root: Path, conan_root: Path, role: str,
                artifact: Path) -> list[str]:
        return [
            sys.executable, str(MANAGER),
            "--source", str(source),
            "--build-root", str(build_root),
            "--conan-root", str(conan_root),
            "--role", role,
            "--artifact-dir", str(artifact),
            "--keep-workspace",
        ]

    def test_phone_and_pico_mutate_distinct_real_checkouts_and_export_apks(self):
        with tempfile.TemporaryDirectory(prefix="overte-android-workspace-test-") as name:
            temporary = Path(name)
            source = self.repository(temporary)
            build_root = temporary / "managed-builds"
            conan_root = temporary / "managed-conan"
            sync = temporary / "sync"
            sync.mkdir(mode=0o700)
            phone_artifact = temporary / "phone-artifact"
            pico_artifact = temporary / "pico-artifact"
            environment = {**os.environ, "SYNC_ROOT": str(sync)}
            phone = subprocess.Popen(
                self.command(source, build_root, conan_root, "android-phone", phone_artifact),
                cwd=source, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            pico = subprocess.Popen(
                self.command(source, build_root, conan_root, "android-pico", pico_artifact),
                cwd=source, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            phone_output = "".join(phone.communicate(timeout=30))
            pico_output = "".join(pico.communicate(timeout=30))
            self.assertEqual(0, phone.returncode, phone_output)
            self.assertEqual(0, pico.returncode, pico_output)

            phone_workspaces = list((build_root / "workspaces").glob("android-phone-*"))
            pico_workspaces = list((build_root / "workspaces").glob("android-pico-*"))
            self.assertEqual(1, len(phone_workspaces))
            self.assertEqual(1, len(pico_workspaces))
            self.assertNotEqual(phone_workspaces[0], pico_workspaces[0])
            for workspace, role in (
                    (phone_workspaces[0], "android-phone"),
                    (pico_workspaces[0], "android-pico")):
                checkout = workspace / "source"
                self.assertEqual(
                    role,
                    (checkout / "android/common/conan/generated/owner").read_text().strip(),
                )
                paths = (workspace / "paths").read_text(encoding="utf-8").splitlines()
                self.assertEqual(str(checkout), paths[0])
                self.assertTrue(Path(paths[1]).is_relative_to(conan_root / "homes" / role))
                self.assertTrue(Path(paths[2]).is_relative_to(workspace / "state/gradle"))
                self.assertEqual(str(workspace), paths[3])
                self.assertEqual(0o700, stat.S_IMODE(workspace.stat().st_mode))

            self.assertFalse((source / "android/common/conan/generated").exists())
            self.assertEqual("original\n", (source / "tracked.txt").read_text())
            self.assertEqual(
                "android-phone\n",
                (phone_artifact / "phoneInterface-debug.apk").read_text(),
            )
            self.assertEqual(
                "android-pico\n",
                (pico_artifact / "picoInterface-debug.apk").read_text(),
            )
            phone_manifest = json.loads(
                (phone_artifact / "build-workspace-manifest.json").read_text())
            pico_manifest = json.loads(
                (pico_artifact / "build-workspace-manifest.json").read_text())
            self.assertEqual("android-phone", phone_manifest["role"])
            self.assertEqual("android-pico", pico_manifest["role"])
            self.assertEqual(phone_manifest["sourceRevision"], pico_manifest["sourceRevision"])
            self.assertNotEqual(
                conan_root / "homes/android-phone", conan_root / "homes/android-pico")

    def test_dirty_source_and_ancestor_symlink_fail_before_any_clone(self):
        with tempfile.TemporaryDirectory(prefix="overte-android-workspace-guard-") as name:
            temporary = Path(name)
            source = self.repository(temporary)
            (source / "tracked.txt").write_text("dirty\n", encoding="utf-8")
            result = run(
                sys.executable, str(MANAGER), "--source", str(source),
                "--build-root", str(temporary / "builds"),
                "--conan-root", str(temporary / "conan"),
                "--role", "android-phone", cwd=source, check=False,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("tracked changes", result.stderr)
            self.assertFalse((temporary / "builds").exists())

            run("git", "checkout", "--quiet", "--", "tracked.txt", cwd=source)
            actual = temporary / "actual-build-parent"
            actual.mkdir(mode=0o700)
            linked = temporary / "linked-build-parent"
            linked.symlink_to(actual, target_is_directory=True)
            result = run(
                sys.executable, str(MANAGER), "--source", str(source),
                "--build-root", str(linked / "builds"),
                "--conan-root", str(temporary / "conan"),
                "--role", "android-phone", cwd=source, check=False,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("symbolic-link components", result.stderr)
            self.assertFalse((actual / "builds").exists())

    def test_production_entrypoints_are_covered_by_the_isolated_role_contract(self):
        manager = MANAGER.read_text(encoding="utf-8")
        phone = (ROOT / "android/phone/build.sh").read_text(encoding="utf-8")
        pico_prepare = (ROOT / "android/vr/pico/prepare-deps.sh").read_text(encoding="utf-8")
        pico = (ROOT / "android/vr/pico/build.sh").read_text(encoding="utf-8")
        self.assertIn('"android-phone": "android/phone/build.sh"', manager)
        self.assertIn('"android-pico": "android/vr/pico/build.sh"', manager)
        self.assertIn("apps/phoneInterface/build", phone)
        self.assertIn('runtime_dir="${script_dir}/../../common/runtime-overrides', pico_prepare)
        self.assertIn('host_tools_dir="${script_dir}/pico-host-tools"', pico_prepare)
        self.assertIn('-of "$android_root/common/conan/pico4-debug"', pico)
        self.assertIn('apps/picoInterface/build/outputs/apk/debug', pico)


if __name__ == "__main__":
    unittest.main()
