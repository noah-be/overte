#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Mirror the already verified native mannequin without altering any asset bytes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from manage import REPO, ROOT

EXPECTED = {
    "defaultAvatar_full.fst": "0519e02f2f3d6afe19f680dd824a29f14a3baa65acb06b87ace33b1836717c50",
    "mannequin/mannequin.fbx": "e247f3342ff109e17f7ae90916f81935d17ff4f51f60c60908094bb4f38db7da",
    "mannequin/lambert1_Base_Color.png": "70b544b69ea325ee03f726694d9392ea8a12ddc66d47559382d142da12b9bdc6",
    "mannequin/lambert1_Normal_OpenGL.png": "ead05dbdca83bc70c7546a3bd88ab2d58ccea85fed8f9f19b845cbfcd7b1fc05",
    "mannequin/lambert1_Roughness.png": "2f3c696977e1a8bf888b107f4935c0b3e0dca1bee2540cec8f780228468771a8",
    "mannequin/Eyes.png": "e8be0da314bfa0e3ad7e0f9d2315dddc38f39510dd421c9edbafc5406086700d",
}


def prepare() -> dict:
    source = REPO / "browser-direct-client/public/default-avatar"
    destination = ROOT / "https-assets/default-avatar"
    validated = []
    for name, expected in EXPECTED.items():
        data = (source / name).read_bytes()
        original = REPO / "interface/resources/meshes" / name
        if hashlib.sha256(data).hexdigest() != expected or data != original.read_bytes():
            raise RuntimeError("The recorded native mannequin source changed")
        validated.append((name, data))
    for name, data in validated:
        target = destination / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.write_bytes(data)
    for name in ("manifest.json", "LICENSE.txt"):
        shutil.copyfile(source / name, destination / name)
    manifest = {
        "label": "Actual native Overte mannequin copied unchanged for explicit participant test setup",
        "source": "interface/resources/meshes; browser fixed manifest verified against native 2026.04.1",
        "skeletonModelURL": "https://127.0.0.1:46119/default-avatar/defaultAvatar_full.fst",
        "files": [{"path": name, "bytes": len(data), "sourceSHA256": EXPECTED[name],
                   "servedSHA256": hashlib.sha256((destination / name).read_bytes()).hexdigest()}
                  for name, data in validated],
        "licenseSource": "browser-direct-client/public/default-avatar/LICENSE.txt",
        "licenseSHA256": hashlib.sha256((destination / "LICENSE.txt").read_bytes()).hexdigest(),
        "generatedModel": False, "assetQualityChanged": False,
    }
    path = ROOT / "runtime/native-avatar-provenance.json"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
