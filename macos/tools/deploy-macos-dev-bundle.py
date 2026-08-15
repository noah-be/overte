#!/usr/bin/env python3
"""Fail-closed incremental deployment for a macOS development app bundle.

The fast path is deliberately narrow: the complete Qt deployment prefix,
Conan inventory, QML input, non-system Mach-O dependency closure, deployment
tools, and every deployment-managed bundle file must match the last successful
deployment byte-for-byte.  Application-owned Resources and the freshly linked
main executable are allowed to change independently.  Anything that cannot be
inspected falls back to the original clean Frameworks deployment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time


SCHEMA_VERSION = 1
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CHUNK_SIZE = 1024 * 1024


class DeploymentError(RuntimeError):
    pass


class Fingerprint:
    def __init__(self) -> None:
        self._hash = hashlib.sha256()
        self.files = 0
        self.bytes = 0
        self.cacheable = True

    def token(self, value: str) -> None:
        encoded = value.encode("utf-8", errors="surrogateescape")
        self._hash.update(len(encoded).to_bytes(8, "big"))
        self._hash.update(encoded)

    def missing(self, label: str) -> None:
        self.token(f"missing:{label}")

    def file(self, label: str, path: Path) -> None:
        try:
            metadata = path.lstat()
        except OSError as error:
            raise DeploymentError(f"could not inspect a deployment input: {error}") from error
        self.token(label)
        self.token(oct(stat.S_IMODE(metadata.st_mode)))
        if path.is_symlink():
            self.token("symlink")
            self.token(os.readlink(path))
            return
        if not path.is_file():
            self.token("unsupported")
            self.cacheable = False
            return
        self.token("file")
        self.files += 1
        self.bytes += metadata.st_size
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(CHUNK_SIZE):
                    self._hash.update(chunk)
        except OSError as error:
            raise DeploymentError(f"could not hash a deployment input: {error}") from error

    def tree(
        self,
        label: str,
        root: Path,
        *,
        exclude: Path | None = None,
        exclude_subtrees: tuple[Path, ...] = (),
        _visited_trees: set[Path] | None = None,
    ) -> None:
        if not root.exists():
            self.missing(label)
            return
        if not root.is_dir():
            self.file(label, root)
            return
        self.token(f"tree:{label}")
        root = root.resolve()
        exclude = exclude.resolve() if exclude is not None else None
        excluded_subtrees = tuple(Path(value) for value in exclude_subtrees)
        for excluded_subtree in excluded_subtrees:
            self.token(f"excluded-subtree:{excluded_subtree.as_posix()}")
        visited_trees = _visited_trees if _visited_trees is not None else set()
        if root in visited_trees:
            self.token(f"tree-cycle:{label}")
            return
        visited_trees.add(root)

        def hash_symlink_target(candidate: Path, candidate_label: str) -> None:
            try:
                resolved = candidate.resolve(strict=True)
            except OSError:
                self.cacheable = False
                return
            try:
                resolved.relative_to(root)
            except ValueError:
                if resolved.is_file():
                    self.file(candidate_label + ":external-target", resolved)
                elif resolved.is_dir():
                    self.tree(
                        candidate_label + ":external-target",
                        resolved,
                        _visited_trees=visited_trees,
                    )
                else:
                    self.cacheable = False

        for directory, directory_names, file_names in os.walk(root, followlinks=False):
            directory_names.sort()
            file_names.sort()
            directory_path = Path(directory)
            relative_directory = directory_path.relative_to(root)
            self.token(f"directory:{relative_directory.as_posix()}")
            included_directories: list[str] = []
            for name in directory_names:
                candidate = directory_path / name
                relative_candidate = candidate.relative_to(root)
                if any(
                    relative_candidate == excluded
                    or excluded in relative_candidate.parents
                    for excluded in excluded_subtrees
                ):
                    continue
                included_directories.append(name)
                if candidate.is_symlink():
                    candidate_label = f"{label}:{candidate.relative_to(root).as_posix()}"
                    self.file(candidate_label, candidate)
                    hash_symlink_target(candidate, candidate_label)
            directory_names[:] = included_directories
            for name in file_names:
                candidate = directory_path / name
                relative_candidate = candidate.relative_to(root)
                if any(
                    relative_candidate == excluded
                    or excluded in relative_candidate.parents
                    for excluded in excluded_subtrees
                ):
                    continue
                if exclude is not None and candidate.resolve() == exclude:
                    self.token(f"excluded:{candidate.relative_to(root).as_posix()}")
                    continue
                self.file(
                    f"{label}:{candidate.relative_to(root).as_posix()}", candidate
                )
                if candidate.is_symlink():
                    hash_symlink_target(
                        candidate, f"{label}:{candidate.relative_to(root).as_posix()}"
                    )

    def digest(self) -> str:
        return self._hash.hexdigest()


def command_output(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def dependencies(path: Path, otool: Path) -> list[str] | None:
    output = command_output([str(otool), "-L", str(path)])
    if output is None:
        return None
    return [
        line.strip().split(" (", 1)[0]
        for line in output.splitlines()[1:]
        if line.strip()
    ]


def runtime_paths(path: Path, otool: Path) -> list[str] | None:
    output = command_output([str(otool), "-l", str(path)])
    if output is None:
        return None
    found: list[str] = []
    expect_path = False
    for line in output.splitlines():
        stripped = line.strip()
        if stripped == "cmd LC_RPATH":
            expect_path = True
        elif expect_path and stripped.startswith("path "):
            found.append(stripped[5:].split(" (offset ", 1)[0])
            expect_path = False
    return found


def expand_loader_path(value: str, loader: Path, executable: Path) -> Path | None:
    if value.startswith("@loader_path/"):
        return loader.parent / value.removeprefix("@loader_path/")
    if value.startswith("@executable_path/"):
        return executable.parent / value.removeprefix("@executable_path/")
    if value.startswith("/"):
        return Path(value)
    return None


def resolve_dependency(
    install_name: str,
    loader: Path,
    executable: Path,
    rpaths: list[str],
    search_roots: list[Path],
    excluded_root: Path,
) -> Path | None:
    candidates: list[Path] = []
    direct = expand_loader_path(install_name, loader, executable)
    if direct is not None and direct.is_file():
        candidates.append(direct.resolve())
    if install_name.startswith("@rpath/"):
        suffix = install_name.removeprefix("@rpath/")
        for runtime_path in rpaths:
            expanded = expand_loader_path(runtime_path, loader, executable)
            if expanded is not None and (expanded / suffix).is_file():
                candidates.append((expanded / suffix).resolve())
        for root in search_roots:
            for candidate in (root / suffix, root / Path(suffix).name):
                if candidate.is_file():
                    candidates.append(candidate.resolve())
    # A prior deployment commonly leaves @executable_path/../Frameworks first
    # in LC_RPATH. Prefer a real build/package source even when that stale
    # bundled candidate exists; only-bundle resolution remains non-cacheable.
    excluded_root = excluded_root.resolve()
    for candidate in candidates:
        try:
            candidate.relative_to(excluded_root)
        except ValueError:
            return candidate
    return candidates[0] if candidates else None


def add_dependency_closure(
    fingerprint: Fingerprint,
    executable: Path,
    app: Path,
    otool: Path,
    search_roots: list[Path],
) -> None:
    pending = [executable.resolve()]
    visited: set[Path] = set()
    app_root = app.resolve()
    while pending:
        binary = pending.pop()
        if binary in visited:
            continue
        visited.add(binary)
        found_dependencies = dependencies(binary, otool)
        found_rpaths = runtime_paths(binary, otool)
        if found_dependencies is None or found_rpaths is None:
            fingerprint.cacheable = False
            return
        fingerprint.token("mach-o")
        for value in found_dependencies:
            fingerprint.token(value)
        for value in found_rpaths:
            fingerprint.token(f"rpath:{value}")
        for install_name in found_dependencies:
            if install_name.startswith("/System/") or install_name.startswith("/usr/lib/"):
                continue
            resolved = resolve_dependency(
                install_name, binary, executable, found_rpaths, search_roots, app_root
            )
            if resolved is None:
                fingerprint.cacheable = False
                continue
            try:
                resolved.relative_to(app_root)
            except ValueError:
                pass
            else:
                # A freshly linked executable must resolve against build/package
                # inputs, not against last run's bundle. Redeploy conservatively.
                fingerprint.cacheable = False
                continue
            fingerprint.file(f"dependency:{len(visited)}", resolved)
            pending.append(resolved)


def input_fingerprint(
    app: Path,
    executable: Path,
    qml_dir: Path,
    lib_dir: Path,
    qt_root: Path,
    macdeployqt: Path,
    deploy_conan_tool: Path,
    otool: Path,
    install_name_tool: Path,
) -> Fingerprint:
    value = Fingerprint()
    value.token(f"schema:{SCHEMA_VERSION}")
    value.token(f"python:{sys.version}")
    value.file("python", Path(sys.executable).resolve())
    value.file("bundle-deploy-tool", Path(__file__).resolve())
    value.file("macdeployqt", macdeployqt)
    value.file("deploy-conan-tool", deploy_conan_tool)
    value.file("otool", otool)
    value.file("install-name-tool", install_name_tool)
    value.tree("qt-prefix", qt_root)
    value.tree("conan-libraries", lib_dir)
    value.tree("qml-input", qml_dir)
    add_dependency_closure(
        value,
        executable,
        app,
        otool,
        [lib_dir, qt_root / "lib", qt_root / "plugins", qt_root / "qml"],
    )
    return value


def stable_bundle_fingerprint(app: Path, executable: Path) -> Fingerprint:
    value = Fingerprint()
    # These directories are staged by Interface's own POST_BUILD commands.
    # A script or fixture-only edit must relink/stage the application but must
    # not invalidate an otherwise verified Qt/Conan deployment.  Qt-owned
    # Resources (WebEngine packs, translations, qt.conf, and QML) remain in the
    # fingerprint and are therefore still checked fail-closed.
    application_resources = Path("Contents/Resources")
    value.tree(
        "application-bundle",
        app,
        exclude=executable,
        exclude_subtrees=(
            application_resources / "scripts",
            application_resources / "fonts",
            application_resources / "serverless",
            application_resources / "jsdoc",
            application_resources / "resources.rcc",
        ),
    )
    return value


def load_stamp(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        return None
    for key in ("input_sha256", "stable_bundle_sha256"):
        if not isinstance(value.get(key), str) or not SHA256.fullmatch(str(value[key])):
            return None
    for key in ("input_files", "input_bytes", "bundle_files", "bundle_bytes"):
        if isinstance(value.get(key), bool) or not isinstance(value.get(key), int) or value[key] < 0:
            return None
    return value


def write_stamp(path: Path, inputs: Fingerprint, bundle: Fingerprint) -> None:
    value = {
        "schema_version": SCHEMA_VERSION,
        "input_sha256": inputs.digest(),
        "stable_bundle_sha256": bundle.digest(),
        "input_files": inputs.files,
        "input_bytes": inputs.bytes,
        "bundle_files": bundle.files,
        "bundle_bytes": bundle.bytes,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def validate_paths(
    app: Path,
    executable: Path,
    qml_dir: Path,
    lib_dir: Path,
    qt_root: Path,
    tools: tuple[Path, ...],
) -> None:
    if not (app / "Contents").is_dir():
        raise DeploymentError("application bundle has no Contents directory")
    if not executable.is_file():
        raise DeploymentError("application bundle has no main executable")
    try:
        executable.resolve().relative_to(app.resolve())
    except ValueError as error:
        raise DeploymentError("main executable is outside the application bundle") from error
    if not qt_root.is_dir():
        raise DeploymentError("Qt deployment prefix is missing")
    if not qml_dir.is_dir():
        raise DeploymentError("QML deployment input is missing")
    if not lib_dir.is_dir():
        raise DeploymentError("Conan deployment input is missing")
    if any(not tool.is_file() for tool in tools):
        raise DeploymentError("a required deployment tool is missing")


def remove_frameworks(app: Path) -> None:
    frameworks = app / "Contents/Frameworks"
    if frameworks.is_symlink() or frameworks.is_file():
        frameworks.unlink()
    elif frameworks.exists():
        shutil.rmtree(frameworks)
    if os.path.lexists(frameworks):
        raise DeploymentError("could not remove stale application Frameworks")


def run_deployment(args: argparse.Namespace) -> int:
    started_at = time.monotonic()
    app = args.app.resolve()
    executable = args.executable.resolve()
    qml_dir = args.qml_dir.resolve()
    lib_dir = args.lib_dir.resolve()
    macdeployqt = args.macdeployqt.resolve()
    deploy_conan_tool = args.deploy_conan_tool.resolve()
    otool = args.otool.resolve()
    install_name_tool = args.install_name_tool.resolve()
    stamp = args.stamp.resolve()
    qt_root = macdeployqt.parent.parent.resolve()
    validate_paths(
        app,
        executable,
        qml_dir,
        lib_dir,
        qt_root,
        (macdeployqt, deploy_conan_tool, otool, install_name_tool),
    )

    inputs = input_fingerprint(
        app, executable, qml_dir, lib_dir, qt_root, macdeployqt, deploy_conan_tool,
        otool, install_name_tool,
    )
    previous = load_stamp(stamp)
    current_bundle: Fingerprint | None = None
    incremental = False
    if not inputs.cacheable:
        reason = "dependency-inspection-incomplete"
    elif previous is None:
        reason = "missing-or-invalid-stamp"
    elif previous["input_sha256"] != inputs.digest():
        reason = "deployment-input-changed"
    else:
        # Hashing a large existing bundle is useful only after a valid stamp
        # and identical deployment inputs make the incremental path possible.
        # Full deployments for a missing stamp or changed Qt/Conan/QML inputs
        # clear Frameworks anyway and must not pay this extra full-tree pass.
        current_bundle = stable_bundle_fingerprint(app, executable)
        if previous["stable_bundle_sha256"] != current_bundle.digest():
            reason = "bundle-state-changed"
        else:
            incremental = True
            reason = "verified-inputs-and-bundle"

    # A killed or failed deployment must never leave a reusable success stamp.
    stamp.unlink(missing_ok=True)
    if not incremental:
        remove_frameworks(app)

    mode = "incremental" if incremental else "full"
    print(
        f"OVERTE_MACOS_BUNDLE_DEPLOY mode={mode} reason={reason} "
        f"input_files={inputs.files} input_bytes={inputs.bytes}",
        flush=True,
    )
    macdeployqt_command = [
        str(macdeployqt), str(app), "-verbose=2", f"-qmldir={qml_dir}",
        f"-libpath={lib_dir}",
    ]
    subprocess.run(macdeployqt_command, check=True)
    if incremental:
        if current_bundle is None:
            raise DeploymentError("incremental deployment has no verified bundle state")
        after_macdeployqt = stable_bundle_fingerprint(app, executable)
        if after_macdeployqt.digest() != current_bundle.digest():
            # The proof for preserving transformed Conan binaries no longer
            # holds. Restart through the clean path rather than guessing which
            # stable bundle file macdeployqt changed.
            incremental = False
            mode = "full"
            reason = "incremental-mutated-stable-bundle"
            print(
                "OVERTE_MACOS_BUNDLE_DEPLOY fallback=full "
                "reason=incremental-mutated-stable-bundle",
                flush=True,
            )
            remove_frameworks(app)
            subprocess.run(macdeployqt_command, check=True)
    deploy_conan_command = [
        sys.executable, str(deploy_conan_tool), "--app", str(app),
        "--lib-dir", str(lib_dir), "--otool", str(otool),
        "--install-name-tool", str(install_name_tool),
    ]
    if incremental:
        deploy_conan_command.append("--preserve-existing")
    subprocess.run(deploy_conan_command, check=True)
    frameworks = app / "Contents/Frameworks"
    if not frameworks.is_dir() or not any(frameworks.iterdir()):
        raise DeploymentError("successful deployment produced no Frameworks inventory")
    deployed_bundle = stable_bundle_fingerprint(app, executable)
    if inputs.cacheable:
        write_stamp(stamp, inputs, deployed_bundle)
    print(
        f"OVERTE_MACOS_BUNDLE_DEPLOY complete mode={mode} reason={reason} "
        f"bundle_files={deployed_bundle.files} bundle_bytes={deployed_bundle.bytes} "
        f"elapsed_seconds={time.monotonic() - started_at:.3f}",
        flush=True,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--qml-dir", type=Path, required=True)
    parser.add_argument("--lib-dir", type=Path, required=True)
    parser.add_argument("--macdeployqt", type=Path, required=True)
    parser.add_argument("--deploy-conan-tool", type=Path, required=True)
    parser.add_argument("--stamp", type=Path, required=True)
    parser.add_argument("--otool", type=Path, default=Path("/usr/bin/otool"))
    parser.add_argument("--install-name-tool", type=Path, default=Path("/usr/bin/install_name_tool"))
    args = parser.parse_args()
    try:
        return run_deployment(args)
    except (DeploymentError, OSError, subprocess.CalledProcessError) as error:
        print(f"deploy-macos-dev-bundle: {error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
