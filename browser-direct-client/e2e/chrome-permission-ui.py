#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Capture/click one owned Chrome window in the private display-104 PID namespace.

This helper never sets browser permissions. Coordinates must be chosen after
inspection of its actual Chrome-window screenshot and remain inside that bound
window. Profile, process start ticks, ancestry and window ownership are rechecked
before every XTest input. No other display or desktop may be selected.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import stat

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "build/browser-direct"
TITLE = "Overte private microphone permission diagnostic"
FORBIDDEN_FLAGS = ("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                   "--auto-accept-camera-and-microphone-capture", "--unsafely-treat-insecure-origin-as-secure")


def normalise_argv(arguments: list[str], executable: Path) -> list[str]:
    # Chromium's Linux SetProcessTitle replaces argv storage with one joined
    # string (base/process/set_process_title_linux.cc). Parsing that representation
    # restores argument boundaries; it never grants ownership or executes text.
    if executable.name == "chrome" and len(arguments) == 1 and " --" in arguments[0]:
        return shlex.split(arguments[0])
    return arguments


def process_record(pid: int) -> dict | None:
    try:
        directory = Path("/proc") / str(pid)
        value = (directory / "stat").read_text()
        fields = value[value.rfind(")") + 2:].split()
        if fields[0] == "Z" or directory.stat().st_uid != os.getuid():
            return None
        executable = (directory / "exe").resolve()
        arguments = [part.decode("utf-8") for part in (directory / "cmdline").read_bytes().split(b"\0") if part]
        return {"pid": pid, "startTicks": fields[19], "parentPID": int(fields[1]), "executable": str(executable),
                "joinedChromeProcessTitle": executable.name == "chrome" and len(arguments) == 1 and " --" in arguments[0],
                "argv": normalise_argv(arguments, executable)}
    except (OSError, ValueError, UnicodeError):
        return None


def is_descendant(pid: int, ancestor: int) -> bool:
    for _ in range(64):
        record = process_record(pid)
        if record is None or pid <= 1:
            return False
        if record["parentPID"] == ancestor:
            return True
        pid = record["parentPID"]
    return False


def validate_process(record: dict | None, profile: Path, ancestor: int, browser_root: Path,
                     expected: dict | None = None) -> dict:
    if record is None or not record.get("argv"):
        raise RuntimeError("The owned Chrome process is no longer live")
    argv = record["argv"]
    executable = Path(record["executable"]).resolve()
    if executable.name != "chrome" or not executable.is_relative_to(browser_root.resolve()) or Path(argv[0]).resolve() != executable:
        raise RuntimeError("The process is not the laboratory's own downloaded Chrome")
    if argv.count(f"--user-data-dir={profile.resolve()}") != 1 or any(value.startswith("--type=") for value in argv):
        raise RuntimeError("The Chrome browser process must bind the exact fresh private profile")
    if any(value == flag or value.startswith(flag + "=") for value in argv for flag in FORBIDDEN_FLAGS):
        raise RuntimeError("A permission/device override is forbidden in this actual-UI diagnostic")
    if not is_descendant(record["pid"], ancestor):
        raise RuntimeError("The Chrome process is not a child of this exact private driver")
    if expected and (record["pid"] != expected.get("pid") or record["startTicks"] != expected.get("startTicks")
                     or ancestor != expected.get("ancestorPID")):
        raise RuntimeError("The Chrome process/start-tick/driver binding changed")
    return {"pid": record["pid"], "startTicks": record["startTicks"], "ancestorPID": ancestor}


def discover_process(profile: Path, ancestor: int) -> dict:
    candidates = []
    rejections = []
    diagnostics = {"ownedExecutableRecords": 0, "ownedExecutableUnreadableRecords": 0,
                   "profileSubstringRecords": 0, "exactProfileArgumentRecords": 0}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        record = process_record(int(entry.name))
        try:
            executable_owned = (entry / "exe").resolve().is_relative_to((STATE / "browsers").resolve())
        except OSError:
            executable_owned = False
        if executable_owned:
            diagnostics["ownedExecutableRecords"] += 1
            if record is None:
                diagnostics["ownedExecutableUnreadableRecords"] += 1
            elif any(f"--user-data-dir={profile.resolve()}" in argument for argument in record["argv"]):
                diagnostics["profileSubstringRecords"] += 1
                diagnostics["exactProfileArgumentRecords"] += int(f"--user-data-dir={profile.resolve()}" in record["argv"])
        if record and f"--user-data-dir={profile.resolve()}" in record["argv"]:
            try:
                candidates.append(validate_process(record, profile, ancestor, STATE / "browsers"))
            except RuntimeError as error:
                rejections.append(str(error))
    if len(candidates) != 1:
        reason = rejections[0] if len(rejections) == 1 else f"qualified={len(candidates)}, refused={len(rejections)}"
        raise RuntimeError(f"Exactly one owned Chrome browser must use this private profile ({reason}; {json.dumps(diagnostics, sort_keys=True)})")
    return candidates[0]


def require_private_environment(profile: Path, display_name: str) -> None:
    if display_name != ":104" or os.environ.get("DISPLAY") != ":104":
        raise RuntimeError("Only the laboratory's private display104 is permitted")
    if not profile.resolve().is_relative_to((STATE / "e2e").resolve()) or not profile.is_dir():
        raise RuntimeError("Only a fresh result-owned browser profile is permitted")
    if os.environ.get("PULSE_SOURCE") != "browser_microphone" or any(Path(value).exists() for value in ("/dev/dri", "/dev/nvidia0", "/dev/snd")):
        raise RuntimeError("Only the private virtual microphone/device-masked namespace is permitted")
    status = Path("/proc/self/status").read_text()
    namespace_ids = next((line.split()[1:] for line in status.splitlines() if line.startswith("NSpid:")), [])
    # software-run.py installs a new PID namespace and its /proc root. Its init
    # is bwrap rather than the host init, and the caller's host PID is invisible.
    init = process_record(1)
    if not namespace_ids or init is None or not any("bwrap" in value for value in init["argv"]):
        raise RuntimeError("The X11 helper must stay inside the existing private browser PID namespace")


def bounded_json(path: Path) -> dict:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16384 or stat.S_IMODE(info.st_mode) != 0o600:
            raise RuntimeError("The window binding must be a private bounded regular file")
        raw = os.read(descriptor, 16385)
        if len(raw) > 16384:
            raise RuntimeError("Oversized window binding")
        return json.loads(raw)
    finally:
        os.close(descriptor)


def bounded_utf8_title(window, name_atom: int, utf8_atom: int) -> str | None:
    # Chromium Ozone/X11 publishes _NET_WM_NAME as UTF8_STRING. Python-Xlib's
    # legacy get_wm_name() requests STRING, so it cannot read that property.
    # One bounded request: 129 32-bit units, at most516 bytes, detects >512 bytes.
    value = window.get_property(name_atom, utf8_atom, 0, 129)
    if value is None or value.property_type != utf8_atom or value.format != 8 or value.bytes_after != 0:
        return None
    try:
        raw = bytes(value.value)
        if len(raw) > 512 or b"\0" in raw:
            return None
        return raw.decode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError):
        return None


def validate_screen_bounds(bounds: dict, screen: dict) -> None:
    if not all(type(value) is int for value in (*bounds.values(), *screen.values())):
        raise RuntimeError("Actual window/root dimensions must be integers")
    if not (0 < screen["width"] <= 8192 and 0 < screen["height"] <= 4320
            and 0 <= bounds["x"] and 0 <= bounds["y"]
            and bounds["width"] > 0 and bounds["height"] > 0
            and bounds["x"] + bounds["width"] <= screen["width"]
            and bounds["y"] + bounds["height"] <= screen["height"]):
        raise RuntimeError(f"The owned Chrome window must fit wholly inside its private root ({json.dumps({'window': bounds, 'root': screen}, sort_keys=True)})")


def owned_window(dpy, process: dict, expected: dict | None = None):
    from Xlib import X
    root = dpy.screen().root
    pid_atom = dpy.intern_atom("_NET_WM_PID")
    title_atom = dpy.intern_atom("_NET_WM_NAME")
    utf8_atom = dpy.intern_atom("UTF8_STRING")
    geometry = root.get_geometry()
    screen = {"width": geometry.width, "height": geometry.height}
    counts = {"sameProcessWindows": 0, "validBoundedUTF8Titles": 0, "expectedTitleMatches": 0,
              "viewableExpectedTitleWindows": 0, "rootWidth": screen["width"], "rootHeight": screen["height"]}
    windows = []
    for window in root.query_tree().children:
        try:
            pid = window.get_full_property(pid_atom, X.AnyPropertyType)
            if pid is None or int(pid.value[0]) != process["pid"]:
                continue
            counts["sameProcessWindows"] += 1
            title = bounded_utf8_title(window, title_atom, utf8_atom)
            if title is not None:
                counts["validBoundedUTF8Titles"] += 1
            if title is None or TITLE not in title:
                continue
            counts["expectedTitleMatches"] += 1
            if window.get_attributes().map_state != X.IsViewable:
                continue
            counts["viewableExpectedTitleWindows"] += 1
            geometry = window.get_geometry()
            point = root.translate_coords(window, 0, 0)
            bounds = {"x": point.x, "y": point.y, "width": geometry.width, "height": geometry.height}
            if not (16 <= bounds["width"] <= 4096 and 16 <= bounds["height"] <= 2160):
                raise RuntimeError("Unsupported bounded Chrome window size")
            validate_screen_bounds(bounds, screen)
            windows.append((window, bounds))
        except (ValueError, IndexError):
            continue
    if len(windows) != 1:
        raise RuntimeError(f"Exactly one live owned Chrome diagnostic window is required ({json.dumps(counts, sort_keys=True)})")
    window, bounds = windows[0]
    if expected and (window.id != expected.get("windowID") or bounds != expected.get("bounds")):
        raise RuntimeError("The reviewed Chrome window/geometry binding changed")
    # A root crop includes a browser-owned permission bubble. Refuse any foreign
    # viewable top-level window intersecting that crop before capture or input.
    for other in root.query_tree().children:
        if other.id == window.id:
            continue
        try:
            attributes = other.get_attributes()
            if attributes.map_state != X.IsViewable or attributes.win_class == X.InputOnly:
                continue
            geometry = other.get_geometry(); point = root.translate_coords(other, 0, 0)
            intersects = (point.x < bounds["x"] + bounds["width"] and point.x + geometry.width > bounds["x"]
                          and point.y < bounds["y"] + bounds["height"] and point.y + geometry.height > bounds["y"])
            if not intersects:
                continue
            pid = other.get_full_property(pid_atom, X.AnyPropertyType)
            transient = other.get_wm_transient_for()
            if not ((pid is not None and int(pid.value[0]) == process["pid"])
                    or (transient is not None and transient.id == window.id)):
                raise RuntimeError("A foreign window overlaps the bound Chrome screenshot/input area")
        except (ValueError, IndexError):
            raise RuntimeError("An overlapping window's ownership could not be verified")
    return root, window, bounds, counts


def validate_coordinates(x: int, y: int, bounds: dict) -> None:
    if type(x) is not int or type(y) is not int or not (0 <= x < bounds["width"] and 0 <= y < bounds["height"]):
        raise RuntimeError("The trusted click must remain inside the reviewed owned Chrome window")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", choices=("capture", "click"), required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--x", type=int)
    parser.add_argument("--y", type=int)
    args = parser.parse_args()
    require_private_environment(args.profile, ":104")
    ancestor = os.getppid()
    previous = bounded_json(args.binding) if args.operation == "click" else None
    if previous and (previous.get("profile") != str(args.profile.resolve()) or previous.get("display") != 104
                     or previous.get("permissionOverrides") is not False):
        raise RuntimeError("The reviewed window must bind this exact profile and private display without overrides")
    process = discover_process(args.profile, ancestor)
    validate_process(process_record(process["pid"]), args.profile, ancestor, STATE / "browsers", previous)
    from Xlib import X, display
    dpy = display.Display(":104")
    try:
        if not dpy.has_extension("XTEST"):
            raise RuntimeError("Actual trusted XTest input is unsupported on this private display")
        root, window, bounds, counts = owned_window(dpy, process, previous)
        if args.operation == "capture":
            if args.screenshot is None or not args.screenshot.resolve().is_relative_to(args.profile.parent.resolve()):
                raise RuntimeError("The screenshot must stay in this case's private result directory")
            image = root.get_image(bounds["x"], bounds["y"], bounds["width"], bounds["height"], X.ZPixmap, 0xffffffff)
            if image is None or len(image.data) != bounds["width"] * bounds["height"] * 4 or dpy.display.info.image_byte_order != X.LSBFirst:
                raise RuntimeError("Unsupported bounded Chrome screenshot pixel layout")
            from PIL import Image
            Image.frombytes("RGB", (bounds["width"], bounds["height"]), image.data, "raw", "BGRX").save(args.screenshot)
            args.screenshot.chmod(0o600)
            proof = {**process, "windowID": window.id, "bounds": bounds, "display": 104,
                     "profile": str(args.profile.resolve()), "permissionOverrides": False}
            args.binding.write_text(json.dumps(proof) + "\n"); args.binding.chmod(0o600)
            print(json.dumps({"capturedOwnedChromeWindow": True, "bounds": bounds, "display": 104,
                              "boundedWindowPropertyCounts": counts}))
        else:
            validate_coordinates(args.x, args.y, bounds)
            from Xlib.ext import xtest
            # Real X server events; no DOM synthetic click or permission API.
            xtest.fake_input(dpy, X.MotionNotify, root=root.id, x=bounds["x"] + args.x, y=bounds["y"] + args.y)
            xtest.fake_input(dpy, X.ButtonPress, detail=1)
            xtest.fake_input(dpy, X.ButtonRelease, detail=1)
            dpy.sync()
            print(json.dumps({"actualXTestButton": True, "display": 104, "reviewedWindowBound": True}))
    finally:
        dpy.close()


if __name__ == "__main__":
    main()
