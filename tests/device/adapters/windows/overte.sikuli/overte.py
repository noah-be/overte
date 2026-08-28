from sikuli import *
import json
import os
import sys


action = sys.argv[1]
arguments = json.loads(sys.argv[2])
title = arguments.get("windowTitle", "")


def release_input():
    # OculiX can be terminated by the adapter timeout while a native hold is
    # active. A separate bounded recovery invocation normalizes every key and
    # button this driver is allowed to press.
    mouseUp(Button.RIGHT)
    for key in ("w", "a", "s", "d", "c", Key.SPACE, Key.TAB):
        keyUp(key)


if action == "release-input":
    release_input()
    raise SystemExit(0)

expected_pid = int(arguments.get("processId", 0))
if expected_pid <= 0:
    raise RuntimeError("visual action requires the launched Overte process ID")
application = None
window = None
for attempt in range(60):
    application = None
    for candidate in App.getApps():
        if candidate.getPID() == expected_pid:
            application = candidate
            break
    if application is None:
        wait(0.5)
        continue
    if action == "close":
        application.close(5)
        raise SystemExit(0)
    application.focus()
    # Window ownership plus the in-client foreground probe are the stable
    # assertions; a transient native focus query is not completion evidence.
    window = application.window()
    if window is not None and window.w >= 100 and window.h >= 100:
        break
    wait(0.5)
if application is None:
    raise RuntimeError("launched Overte process is not visible to OculiX")
if window is None or window.w < 100 or window.h < 100:
    raise RuntimeError("Overte application window could not be focused")
if application.getPID() != expected_pid:
    raise RuntimeError("focused window does not belong to the launched Overte process")

if action == "focus":
    pass
elif action == "look":
    center = window.getCenter()
    horizontal = float(arguments.get("horizontal", 0.25))
    vertical = float(arguments.get("vertical", 0.0))
    destination = Location(center.x - int(window.w * horizontal),
                           center.y - int(window.h * vertical))
    mouseMove(center)
    mouseDown(Button.RIGHT)
    try:
        # OculiX exposes mouseMove(Location), but unlike older SikuliX builds
        # does not expose the Location-plus-duration overload. Emit a smooth
        # drag as deterministic intermediate locations instead.
        for step in range(1, 9):
            mouseMove(Location(
                center.x + int((destination.x - center.x) * step / 8.0),
                center.y + int((destination.y - center.y) * step / 8.0)))
            wait(0.1)
    finally:
        mouseUp(Button.RIGHT)
elif action in ("move", "jump", "fly", "settle"):
    movement_keys = {
        "forward": "w", "backward": "s", "left": "a", "right": "d"
    }
    if action == "move":
        direction = arguments.get("direction", "forward")
        if direction not in movement_keys:
            raise RuntimeError("unsupported movement direction")
        key = movement_keys[direction]
        duration = float(arguments.get("durationSeconds", 1.5))
    elif action == "jump":
        key = Key.SPACE
        duration = 0.1
    elif action == "fly":
        key = Key.SPACE
        duration = float(arguments.get("durationSeconds", 2.0))
    else:
        key = "c"
        duration = 2.5
    keyDown(key)
    try:
        wait(duration)
    finally:
        keyUp(key)
elif action in ("tablet-open", "tablet-close"):
    if arguments.get("normalizeKeyUp") is True:
        keyUp(Key.TAB)
    keyDown(Key.TAB)
    try:
        wait(0.1)
    finally:
        keyUp(Key.TAB)
elif action == "screenshot":
    directory = arguments["artifactDirectory"]
    filename = arguments.get("filename", "screenshot.png")
    if filename != "screenshot.png" or not os.path.isdir(directory):
        raise RuntimeError("screenshot destination is not adapter-owned")
    captured = window.getScreen().capture(window)
    captured.getFile(directory, filename)
else:
    raise RuntimeError("unsupported OculiX action")
