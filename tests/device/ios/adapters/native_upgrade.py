"""Bind native update operations to two explicitly prepared signed artifacts.

The local signer verifies signatures before preparing this private contract;
the device installation service independently accepts or rejects each package.
The portable module verifies the actual running versions and retained setting.
"""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import hashlib
from io import BytesIO
import os
from pathlib import Path
import plistlib
import re
import stat
import zipfile


def configuration(target):
    value = target.get("nativeUpgrade")
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != {"kind", "bundleId", "teamId", "source", "candidate"}
            or value["kind"] != "native-signed-ipa-upgrade" or value["bundleId"] != target.get("appId")
            or not isinstance(value["teamId"], str) or not re.fullmatch(r"[A-Z0-9]{10}", value["teamId"])):
        raise ValueError("native upgrade must identify the configured app and signing team")
    for key in ("source", "candidate"):
        artifact = value[key]
        if (not isinstance(artifact, dict) or set(artifact) != {"path", "sha256", "sourceRevision", "version"}
                or not all(isinstance(v, str) and v for v in artifact.values())
                or not Path(artifact["path"]).is_absolute() or "\x00" in artifact["path"]
                or not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"])
                or not re.fullmatch(r"[0-9a-f]{40}", artifact["sourceRevision"])
                or len(artifact["version"]) > 64 or any(c.isspace() for c in artifact["version"])):
            raise ValueError("native upgrade artifact is not explicitly source and digest bound")
    if any(value["source"][k] == value["candidate"][k] for k in ("path", "sha256", "sourceRevision", "version")):
        raise ValueError("native upgrade requires distinct source and candidate artifacts")
    return value


def package(config, role):
    if role not in {"source", "candidate"}:
        raise ValueError("unknown native upgrade artifact role")
    artifact = config[role]
    path = Path(artifact["path"])
    if path.resolve() != path or path.parent.is_symlink():
        raise ValueError("native upgrade artifact cannot traverse a symlink")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= 2 * 1024**3):
            raise ValueError("native upgrade artifact must be a bounded private owned file")
        data = stream.read(info.st_size + 1)
    if len(data) != info.st_size or hashlib.sha256(data).hexdigest() != artifact["sha256"]:
        raise ValueError("native upgrade artifact digest changed")
    with zipfile.ZipFile(BytesIO(data)) as archive:
        names = archive.namelist()
        plists = [n for n in names if re.fullmatch(r"Payload/[^/]+[.]app/Info[.]plist", n)]
        if len(plists) != 1 or archive.getinfo(plists[0]).file_size > 1024**2:
            raise ValueError("native upgrade requires one bounded outer app identity")
        root = plists[0][:-len("Info.plist")]
        info = plistlib.loads(archive.read(plists[0]))
        if (info.get("CFBundleIdentifier") != config["bundleId"]
                or info.get("OverteE2ETestBuildContractVersion") != 1
                or info.get("CFBundleSupportedPlatforms") != ["iPhoneOS"]
                or root + "embedded.mobileprovision" not in names
                or root + "_CodeSignature/CodeResources" not in names):
            raise ValueError("native upgrade package is not the configured signed device test app")
    return data
