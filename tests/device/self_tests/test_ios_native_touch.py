#!/usr/bin/env python3
"""Native touch bounds and physical contact cleanup without a device."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.ios.touch import perform, validate_actions


def sequence():
    return {"actions": [{"type": "pointer", "id": "test-touch",
        "parameters": {"pointerType": "touch"}, "actions": [
            {"type": "pointerMove", "duration": 0, "origin": "viewport", "x": 50, "y": 25},
            {"type": "pointerDown", "button": 0},
            {"type": "pointerMove", "duration": 0, "origin": "viewport", "x": 60, "y": 25},
            {"type": "pointerUp", "button": 0}]}]}


class NativeTouch(unittest.IsolatedAsyncioTestCase):
    def test_outside_coordinate_and_foreign_origin_are_rejected(self):
        for key, value in (("x", 101), ("x", True), ("x", float("nan")), ("origin", "pointer")):
            payload = sequence()
            payload["actions"][0]["actions"][0][key] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_actions(payload, 100, 50)

    def test_incomplete_contact_is_rejected_before_events(self):
        payload = sequence()
        payload["actions"][0]["actions"].pop()
        with self.assertRaises(ValueError):
            validate_actions(payload, 100, 50)

    async def test_real_report_sequence_contains_contact_and_release(self):
        hid = AsyncMock()
        await perform(hid, validate_actions(sequence(), 100, 50))
        states = [call.args[0] for call in hid.send_touchscreen.await_args_list]
        self.assertEqual(states, [0xC2, 0xC2, 0x02])

    async def test_transport_failure_still_releases_contact(self):
        hid = AsyncMock()
        hid.send_touchscreen.side_effect = [RuntimeError("transport failure"), None]
        with self.assertRaises(RuntimeError):
            await perform(hid, validate_actions(sequence(), 100, 50))
        self.assertEqual(hid.send_touchscreen.await_args_list[-1].args[0], 0x02)

    async def test_cancellation_still_releases_contact(self):
        hid = AsyncMock()
        hid.send_touchscreen.side_effect = [asyncio.CancelledError(), None]
        with self.assertRaises(asyncio.CancelledError):
            await perform(hid, validate_actions(sequence(), 100, 50))
        self.assertEqual(hid.send_touchscreen.await_args_list[-1].args[0], 0x02)


if __name__ == "__main__":
    unittest.main()
