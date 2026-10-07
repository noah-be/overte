#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build direct-client server binaries in a pinned, GPU-free Linux environment."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "build/browser-direct"
IMAGE = "ghcr.io/noah-be/overte/native-dependencies@sha256:a692b477cd2efdfc1f3d0f059a8eebba4852d37509a2efa945937ef2fe073373"
DATA_CHANNEL_URL = "https://github.com/paullouisageneau/libdatachannel.git"
DATA_CHANNEL_TAG = "v0.24.6"
DATA_CHANNEL_COMMIT = "6b1e2e620f1e37f0eafeee702eaea0043cb305fd"
CONTAINER_STATE = "/src/build/browser-direct"


def run(arguments: list[str], *, cwd: Path = REPO) -> None:
    subprocess.run(arguments, cwd=cwd, check=True)


def container(arguments: list[str]) -> None:
    run(["podman", "run", "--rm", "--pull=never", "--network", "none",
         "--security-opt", "label=disable", "--name", f"overte-direct-build-{os.getpid()}",
         "-v", f"{REPO}:/src", "-w", "/src",
         "-e", f"CONAN_HOME={CONTAINER_STATE}/conan",
         "-e", f"CCACHE_DIR={CONTAINER_STATE}/ccache",
         "-e", "QT_QPA_PLATFORM=offscreen",
         "-e", "QT_RCC_SOURCE_DATE_OVERRIDE=1", IMAGE, *arguments])


def prepare() -> None:
    source = STATE / "deps/libdatachannel"
    if not source.exists():
        run(["git", "clone", "--branch", DATA_CHANNEL_TAG, "--depth", "1",
             "--recurse-submodules", "--shallow-submodules", DATA_CHANNEL_URL, str(source)])
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if actual != DATA_CHANNEL_COMMIT:
        raise RuntimeError("libdatachannel source does not match the reviewed release commit")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True).strip():
        raise RuntimeError("libdatachannel checkout has unreviewed changes")
    submodules = subprocess.check_output(["git", "submodule", "status", "--recursive"], cwd=source, text=True)
    if any(line[0] != " " for line in submodules.splitlines()):
        raise RuntimeError("libdatachannel submodules do not match the pinned parent commit")
    container(["python3", "tools/native-tests/packages.py", "--source", "."])
    container(["python3", "-c",
               "from pathlib import Path; import shutil; "
               f"target=Path('{CONTAINER_STATE}/conan'); "
               "shutil.copytree('/root/.conan2',target) if not target.exists() else None"])
    container(["conan", "install", ".", "-pr", "tools/conan-profiles/linux",
               "-s", "compiler.cppstd=gnu20", "-s", "build_type=Release",
               "-o", "Overte/*:qt_source=system", "--lockfile=tools/native-tests/conan-linux.lock",
               "--build=never", "--no-remote", "-of", "build/browser-direct/native"])
    container(["cmake", "-S", f"{CONTAINER_STATE}/deps/libdatachannel", "-B",
               f"{CONTAINER_STATE}/deps/libdatachannel-build", "-G", "Ninja",
               "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_INSTALL_PREFIX={CONTAINER_STATE}/deps/prefix",
               "-DNO_MEDIA=ON", "-DNO_WEBSOCKET=ON", "-DNO_TESTS=ON", "-DNO_EXAMPLES=ON",
               "-DBUILD_SHARED_LIBS=ON", "-DBUILD_SHARED_DEPS_LIBS=OFF",
               "-DUSE_NICE=OFF", "-DUSE_GNUTLS=OFF", "-DUSE_MBEDTLS=OFF"])
    container(["cmake", "--build", f"{CONTAINER_STATE}/deps/libdatachannel-build", "--target",
               "install", "--parallel", "4"])
    (STATE / "dependency-source.json").write_text(json.dumps({
        "nativeImage": IMAGE, "libdatachannel": {"url": DATA_CHANNEL_URL,
        "tag": DATA_CHANNEL_TAG, "commit": DATA_CHANNEL_COMMIT,
        "submodules": submodules.splitlines()},
        "nativeBuild": "build/browser-direct/native", "jobs": 4,
        "networkDuringCompilation": False, "gpuDevicesMounted": False,
    }, indent=2) + "\n")


def configure() -> None:
    container(["cmake", "-S", ".", "-B", "build/browser-direct/native", "-G", "Ninja",
               "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_TOOLCHAIN_FILE=generators/conan_toolchain.cmake",
               f"-DCMAKE_PREFIX_PATH={CONTAINER_STATE}/deps/prefix",
               "-DCMAKE_C_COMPILER_LAUNCHER=ccache", "-DCMAKE_CXX_COMPILER_LAUNCHER=ccache",
               "-DOVERTE_BUILD_CLIENT=OFF", "-DOVERTE_BUILD_SERVER=ON",
               "-DOVERTE_BUILD_TOOLS=OFF", "-DOVERTE_BUILD_INSTALLER=OFF",
               "-DOVERTE_BUILD_TESTS=ON", "-DOVERTE_BUILD_MANUAL_TESTS=OFF",
               "-DOVERTE_TEST_GROUPS=networking;browser-direct-transport", "-DOVERTE_BROWSER_TRANSPORT=ON"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "configure", "build", "exec"))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "native-build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.operation == "prepare":
            prepare()
        elif args.operation == "configure":
            configure()
        elif args.operation == "build":
            container(["cmake", "--build", "build/browser-direct/native", "--parallel", "4",
                       "--target", *(args.arguments or ["domain-server", "assignment-client"])])
        else:
            command = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
            if not command:
                parser.error("exec requires a command")
            container(command)


if __name__ == "__main__":
    main()
