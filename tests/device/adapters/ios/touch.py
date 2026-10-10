"""Real CoreDevice HID events from bounded native W3C touch sequences.

The pinned developer runtime authenticates HID through an owned media stream.
It delivers UIKit touch events; it does not set avatar/probe state or invoke
in-client locomotion mappings. Every injected contact is released on exit.
"""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import asyncio
import math


def number(value, minimum, maximum):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("native touch coordinate or duration is out of bounds")
    return float(value)


def validate_actions(payload, width, height):
    width = number(width, 1, 10000)
    height = number(height, 1, 10000)
    if not isinstance(payload, dict) or set(payload) != {"actions"}:
        raise ValueError("native touch requires the exact W3C action envelope")
    sources = payload["actions"]
    if not isinstance(sources, list) or len(sources) != 1:
        raise ValueError("native touch supports one bounded touch pointer")
    source = sources[0]
    if (not isinstance(source, dict) or set(source) != {"type", "id", "parameters", "actions"}
            or source["type"] != "pointer" or source["parameters"] != {"pointerType": "touch"}
            or not isinstance(source["id"], str) or not source["id"]):
        raise ValueError("native touch source is invalid")
    actions = source["actions"]
    if not isinstance(actions, list) or not 3 <= len(actions) <= 64:
        raise ValueError("native touch sequence length is invalid")
    down = False
    point = None
    duration = 0.0
    result = []
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("native touch item must be an object")
        kind = action.get("type")
        if kind == "pointerMove":
            if set(action) != {"type", "duration", "origin", "x", "y"} or action["origin"] != "viewport":
                raise ValueError("native touch requires absolute viewport coordinates")
            x = number(action["x"], 0, width - 1)
            y = number(action["y"], 0, height - 1)
            seconds = number(action["duration"], 0, 10000) / 1000
            point = (round(x * 65535 / width), round(y * 65535 / height))
        elif kind in {"pointerDown", "pointerUp"}:
            if set(action) != {"type", "button"} or type(action["button"]) is not int or action["button"] != 0:
                raise ValueError("native touch supports only the primary contact")
            if point is None or (kind == "pointerDown") == down:
                raise ValueError("native touch contact sequence is invalid")
            down = kind == "pointerDown"
            seconds = 0
        elif kind == "pause":
            if set(action) != {"type", "duration"}:
                raise ValueError("native touch pause fields are invalid")
            seconds = number(action["duration"], 0, 10000) / 1000
        else:
            raise ValueError("native touch item is unsupported")
        duration += seconds
        if duration > 12:
            raise ValueError("native touch sequence exceeds the bounded duration")
        result.append((kind, point, seconds))
    if down or result[-1][0] != "pointerUp":
        raise ValueError("native touch must end with every pointer released")
    return result


async def perform(hid, actions):
    # These report states are pinned by pymobiledevice3's CoreDevice HID codec.
    contact, release = 0xC2, 0x02
    down = False
    position = None
    try:
        for kind, point, seconds in actions:
            if kind == "pointerMove":
                start = position or point
                if down:
                    steps = max(1, math.ceil(seconds * 60))
                    for step in range(1, steps + 1):
                        position = tuple(round(a + (b - a) * step / steps) for a, b in zip(start, point))
                        await hid.send_touchscreen(contact, *position)
                        if seconds:
                            await asyncio.sleep(seconds / steps)
                elif seconds:
                    await asyncio.sleep(seconds)
                position = point
            elif kind == "pointerDown":
                down = True  # Release even if the transport loses the acknowledgement.
                await hid.send_touchscreen(contact, *position)
            elif kind == "pointerUp":
                await hid.send_touchscreen(release, *position)
                down = False
            else:
                await asyncio.sleep(seconds)
    finally:
        if down and position is not None:
            await hid.send_touchscreen(release, *position)

