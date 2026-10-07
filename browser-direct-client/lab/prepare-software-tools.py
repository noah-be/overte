#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Copy verified immutable release/tool artifacts into this lab's private runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "build/browser-direct/lab"
CLIENT = "Overte-2026.04.1-x86_64.AppImage"
CLIENT_SHA256 = "dc39f5b4694a1c48cfb1454a8922f6a25fa4db5820bf937113ebf4086aa99145"
CLIENT_URL = f"https://public.overte.org/build/overte/release/2026.04.1/{CLIENT}"
PACKAGES = {
    "pulseaudio-17.0-9.fc44.x86_64.rpm": "556318f10157bd652a8bbc8d1dac647692c265fc5d8d62c565cb22aac90f4c37",
    "pulseaudio-libs-17.0-9.fc44.x86_64.rpm": "a0cb8816a5694ee5e50e23c8f1233fc9c3a683b137d6c2f0fdb37309392524b4",
    "xorg-x11-server-Xvfb-21.1.24-1.fc44.x86_64.rpm": "32ec1cc4d345055fe7aed63e3404cfef26bc219f89006a39acf24225b7c1f998",
    "speexdsp-1.2.1-10.fc44.x86_64.rpm": "e6dc391d83edf0f0e0665432c9d7237b8a882a261d501ab689af098f02693167",
}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-cache", type=Path, required=True,
                        help="Read-only verified artifact directory, containing downloads/ and rpms/.")
    args = parser.parse_args()
    for name in ("downloads", "logs", "runtime"):
        (ROOT / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    downloads = ROOT / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    identities = []
    for name, expected in {CLIENT: CLIENT_SHA256, **PACKAGES}.items():
        target = downloads / name
        cached = args.artifact_cache / ("downloads" if name == CLIENT else "rpms") / name
        if cached.is_file():
            if digest(cached) != expected:
                raise RuntimeError(f"Cached immutable artifact checksum differs: {name}")
            if not target.exists():
                shutil.copyfile(cached, target)
            provenance = "Verified immutable artifact copy; source cache remains read-only."
        elif name == CLIENT:
            if not target.exists():
                urllib.request.urlretrieve(CLIENT_URL, target)
            provenance = CLIENT_URL
        else:
            raise RuntimeError(f"Prepared pinned Fedora package is unavailable: {name}")
        if digest(target) != expected:
            raise RuntimeError(f"Own artifact checksum differs: {name}")
        identities.append({"filename": name, "sha256": expected, "source": provenance})
    appimage = downloads / CLIENT
    appimage.chmod(0o755)
    app_root = ROOT / "native-release"
    app_root.mkdir(exist_ok=True)
    if not (app_root / "squashfs-root/AppRun").is_file():
        with (ROOT / "logs/native-release-extract.log").open("w") as log:
            subprocess.run([str(appimage), "--appimage-extract"], cwd=app_root, stdout=log,
                           stderr=subprocess.STDOUT, check=True)
    tools = ROOT / "host-tools"
    tools.mkdir(exist_ok=True)
    for name in PACKAGES:
        source = subprocess.Popen(["rpm2cpio", str(downloads / name)], stdout=subprocess.PIPE)
        try:
            result = subprocess.run(["cpio", "-id", "--quiet", "-D", str(tools)],
                                    stdin=source.stdout, capture_output=True, text=True)
        finally:
            source.stdout.close()
        if source.wait() or result.returncode:
            raise RuntimeError(f"Pinned package extraction failed: {name}")
    (ROOT / "runtime/software-tool-artifacts.json").write_text(json.dumps(identities, indent=2) + "\n")
    print(json.dumps({"prepared": True, "nativeRelease": "2026.04.1", "artifactCount": len(identities),
                      "sourceCacheModified": False, "gpuProcessesStarted": False}))


if __name__ == "__main__":
    main()
