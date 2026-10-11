"""Observe effective Android audio permission and independently presented frames."""
from __future__ import annotations

import base64
from io import BytesIO
import re
import shlex

from adb_transport import AdbTransport


def permission_modes(adb: AdbTransport, device: str, package: str) -> dict:
    output = adb.shell(device, "cmd", "appops", "get", package, "RECORD_AUDIO")
    pattern = r"(allow|ignore|deny|default|foreground)\b"
    uid = set(re.findall(r"^\s*Uid mode: RECORD_AUDIO: " + pattern, output, re.MULTILINE))
    modes = set(re.findall(r"^\s*RECORD_AUDIO: " + pattern, output, re.MULTILINE))
    if len(uid) <= 1 and len(modes) <= 1 and (uid or modes):
        return {"uid": next(iter(uid), "default"),
                "package": next(iter(modes), "default")}
    if "No operations." in output:
        return {"uid": "default", "package": "default"}
    raise RuntimeError("Android microphone AppOps mode is unavailable or ambiguous")


def permission_mode(adb: AdbTransport, device: str, package: str) -> str:
    modes = permission_modes(adb, device, package)
    # Android applies a non-default UID mode before the package mode.
    return modes["uid"] if modes["uid"] != "default" else modes["package"]


def permission_snapshot(adb: AdbTransport, device: str, package: str) -> dict:
    output = adb.shell(device, "dumpsys", "package", package)
    granted = re.findall(r"android.permission.RECORD_AUDIO: granted=(true|false)", output)
    if len(set(granted)) != 1:
        raise RuntimeError("Android microphone runtime grant is unavailable or ambiguous")
    mode = permission_mode(adb, device, package)
    # AppOps is the native OS enforcement path that can deny capture in place.
    # Runtime revocation through PackageManager kills the UID by OS design.
    allowed = granted[0] == "true" and mode in {"allow", "default", "foreground"}
    return {"schemaVersion": 1, "permissionId": "microphone",
            "state": "granted" if allowed else "denied"}


def classify_frame(content: bytes) -> bool:
    from PIL import Image
    with Image.open(BytesIO(content)) as source:
        source.load()
        if source.format != "PNG" or source.width < 32 or source.height < 32:
            raise RuntimeError("native presentation capture is not a usable PNG")
        # Exclude status/navigation bars; the owned world fills this interior.
        crop = source.crop((source.width // 5, source.height // 5,
                            source.width * 4 // 5, source.height * 4 // 5))
        grey = crop.convert("L").resize((64, 64))
        bright = sum(count for level, count in enumerate(grey.histogram()) if level > 12)
        return bright / (64 * 64) < 0.01


def presented_frames(adb: AdbTransport, device: str, package: str) -> int:
    layers = adb.shell(device, "dumpsys", "SurfaceFlinger", "--list")
    timestamps = []
    for line in layers.splitlines():
        if f"SurfaceView[{package}/" not in line or "(BLAST)" not in line:
            continue
        name = line.removeprefix("RequestedLayerState{").split(" parentId=", 1)[0].rstrip("}")
        # A layer name contains spaces and brackets. Quote as one remote argument.
        output = adb.execute(["shell", shlex.join(["dumpsys", "SurfaceFlinger", "--latency", name])],
                             target=device)
        for row in output.splitlines()[1:]:
            values = row.split()
            if len(values) == 3 and all(item.isdigit() for item in values):
                presented = int(values[1])
                if 0 < presented < (1 << 63) - 1:
                    timestamps.append(presented)
    if not timestamps:
        raise RuntimeError("owned Android render surface has no presented-frame evidence")
    return max(timestamps)


def render_snapshot(adb: AdbTransport, device: str, package: str,
                    screenshot: str, foreground: bool) -> dict:
    gfx = adb.shell(device, "dumpsys", "gfxinfo", package)
    backends = set(re.findall(r"^Pipeline=(Skia \(Vulkan\)|Skia \(OpenGL\))$", gfx, re.MULTILINE))
    if len(backends) != 1:
        raise RuntimeError("owned Android window has no unambiguous GPU pipeline")
    try:
        content = base64.b64decode(screenshot, validate=True)
    except (ValueError, TypeError):
        raise RuntimeError("native presentation capture is invalid") from None
    return {"schemaVersion": 1, "backend": "Android " + backends.pop(),
            "hardwareAccelerated": True, "surfaceVisible": foreground,
            "blackFrame": classify_frame(content),
            "frameSequence": presented_frames(adb, device, package)}
