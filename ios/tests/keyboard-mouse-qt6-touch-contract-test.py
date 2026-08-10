#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "libraries/input-plugins/src/input-plugins/KeyboardMouseDevice.cpp").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require("#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)\n#include <QtGui/QEventPoint>" in SOURCE,
        "Qt 6 touch handling must include QEventPoint")
require("using HifiTouchPoint = QEventPoint;" in SOURCE and
        "return event->points();" in SOURCE and
        "return point.position();" in SOURCE,
        "Qt 6 touch handling must use QEventPoint points and positions")
require("event->touchPointStates().testFlag(QEventPoint::State::Pressed)" in SOURCE,
        "Qt 6 touch begin must use QEventPoint state flags")
require("event->pointStates()" not in SOURCE,
        "touch handling must not call a nonexistent QPointerEvent pointStates API")
require("using HifiTouchPoint = QTouchEvent::TouchPoint;" in SOURCE and
        "return event->touchPoints();" in SOURCE and
        "return point.pos();" in SOURCE,
        "Qt 5 touch handling must retain the legacy API branch")
require(SOURCE.count("evalAverageTouchPoints(hifiTouchPoints(event))") == 3,
        "begin, update, and end must share the versioned point adapter")
require("currentPos - _lastTouch" in SOURCE and
        "averagePoint /= (float)(points.count())" in SOURCE,
        "average-position delta semantics must remain intact")

print("KeyboardMouseDevice Qt 6 touch contract valid: QEventPoint with Qt 5 fallback")
