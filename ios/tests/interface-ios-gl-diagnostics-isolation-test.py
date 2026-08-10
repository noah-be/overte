#!/usr/bin/env python3
"""Contract for iOS exclusion of platform probes and legacy GL statistics."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
main = (ROOT / "interface/src/main.cpp").read_text(encoding="utf-8")
stats = (ROOT / "interface/src/ui/Stats.cpp").read_text(encoding="utf-8")

include = "#include <gl/GLHelpers.h>"
position = main.index(include)
guard = main.rfind("#if (defined(Q_OS_MAC) && !defined(Q_OS_IOS)) || defined(Q_OS_WIN)", 0, position)
close = main.find("#endif", position)
if guard < 0 or close < 0 or main.find("#endif", guard, position) >= 0:
    raise SystemExit("main GLHelpers include is not restricted to macOS/Windows")

context_include = "#include <gl/Context.h>"
position = stats.index(context_include)
guard = stats.rfind("#if !defined(Q_OS_IOS)", 0, position)
close = stats.find("#endif", position)
if guard < 0 or close < 0:
    raise SystemExit("Stats gl::Context include is not excluded on iOS")

ios_branch = stats[stats.index("#if defined(Q_OS_IOS)", position):]
if "STAT_UPDATE(glContextSwapchainMemory, 0)" not in ios_branch:
    raise SystemExit("iOS Stats does not report the unavailable legacy GL metric as zero")
if "gl::Context::getSwapchainMemoryUsage()" not in ios_branch:
    raise SystemExit("non-iOS legacy GL statistic was not preserved")

print("iOS Interface GL diagnostics valid: startup probe excluded; legacy swapchain stat is zero")
