#!/usr/bin/env python3
"""Contract preventing macOS command-line probes in iOS PlatformInfo."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "interface/src/scripting/PlatformInfoScriptingInterface.cpp").read_text()
HEADER = (ROOT / "interface/src/scripting/PlatformInfoScriptingInterface.h").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require("#elif defined(Q_OS_MAC) && !defined(Q_OS_IOS)\n#include <sstream>" in SOURCE,
        "macOS reporting support include remains reachable on iOS")
require('#elif defined Q_OS_IOS\n    return "IOS";\n#elif defined Q_OS_MAC\n    return "MACOS";' in SOURCE,
        "iOS operating-system reporting falls through to macOS")
require(SOURCE.count("#elif defined Q_OS_IOS") == 4,
        "expected explicit iOS gates for OS, CPU, memory, and GPU reporting")
require('#elif defined Q_OS_IOS\n    return QString("NOT AVAILABLE");' in SOURCE,
        "iOS CPU reporting may reach the desktop sysctl probe")
require('#elif defined Q_OS_IOS\n    return -1;\n#elif defined Q_OS_MAC' in SOURCE,
        "iOS memory reporting may reach the desktop sysctl probe")
require('#elif defined Q_OS_IOS\n    return QString("UNKNOWN");\n#elif defined Q_OS_MAC' in SOURCE,
        "iOS GPU reporting may reach system_profiler")
require('popen("sysctl -n machdep.cpu.brand_string", "r")' in SOURCE and
        'popen("system_profiler SPDisplaysDataType | grep Chipset", "r")' in SOURCE,
        "desktop macOS reporting implementations changed")
require('<code>"IOS"</code>, or <code>"UNKNOWN"</code>' in HEADER,
        "public script documentation does not describe the iOS identity")

print("iOS PlatformInfo isolation valid: mobile identity explicit; macOS probes preserved and unreachable")
