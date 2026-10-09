"""Bound media callbacks to the owned stack and clean up exact sessions."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.ios.hid_session import touch_session


class HidSession(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rsd = SimpleNamespace(service=SimpleNamespace(address=("fd00::2", 1234)))
        self.receiver = MagicMock()
        self.receiver.getsockname.return_value = ("fd00::1", 54321)
        async def wait_for_datagram(_):
            await asyncio.sleep(60)
        self.receiver.recv = AsyncMock(side_effect=wait_for_datagram)
        self.display = AsyncMock()
        self.display.__aenter__.return_value = self.display
        self.hid = AsyncMock()
        self.hid.__aenter__.return_value = self.hid
        self.options = dict(display_factory=lambda _: self.display,
                            hid_factory=lambda _: self.hid,
                            socket_factory=lambda: self.receiver)

    async def test_authentication_uses_bound_stack_and_stops_only_owned_uuid(self):
        async with touch_session(self.rsd, "fd00::1", **self.options) as hid:
            self.assertIs(hid, self.hid)
            self.receiver.bind.assert_called_once_with(("fd00::1", 0))
            request = self.display.start_video_stream.call_args.kwargs
            self.assertEqual((request["receiver_ip"], request["receiver_port"]), ("fd00::1", 54321))
        self.display.stop_media_stream.assert_awaited_once_with(request["client_session_id"])
        self.receiver.close.assert_called_once()

    async def test_failed_negotiation_never_injects_and_still_stops_exact_stream(self):
        self.display.start_video_stream.side_effect = RuntimeError("lost negotiation reply")
        with self.assertRaises(RuntimeError):
            async with touch_session(self.rsd, "fd00::1", **self.options):
                self.fail("failed authentication must never yield HID")
        self.hid.__aenter__.assert_not_called()
        request = self.display.start_video_stream.call_args.kwargs
        self.display.stop_media_stream.assert_awaited_once_with(request["client_session_id"])
        self.receiver.close.assert_called_once()

    async def test_loopback_never_creates_media_socket(self):
        with self.assertRaises(ValueError):
            async with touch_session(self.rsd, "::1", **self.options):
                self.fail("loopback is unreachable from the device")
        self.receiver.bind.assert_not_called()


if __name__ == "__main__":
    unittest.main()
