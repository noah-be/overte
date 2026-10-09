"""Authenticate physical HID on the already-owned userspace Wi-Fi tunnel."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import asyncio
from contextlib import asynccontextmanager, suppress
import ipaddress
import uuid


@asynccontextmanager
async def touch_session(rsd, local_address, *, display_factory=None,
                        hid_factory=None, socket_factory=None):
    # An in-process RSD relay has no reachable kernel endpoint. Bind RTP on
    # the exact authenticated tunnel's existing IP stack instead; never open
    # a second tunnel, patch runtime globals or advertise a loopback endpoint.
    address = ipaddress.IPv6Address(local_address)
    if address.is_unspecified or address.is_multicast or address.is_loopback:
        raise ValueError("native HID requires a reachable owned tunnel address")
    if display_factory is None:
        from pymobiledevice3.remote.core_device.display_service import DisplayService
        display_factory = DisplayService
    if hid_factory is None:
        from pymobiledevice3.remote.core_device.hid_service import UniversalHIDServiceService
        hid_factory = UniversalHIDServiceService
    if socket_factory is None:
        from pmd_pytcp.socket import AF_INET6, SOCK_DGRAM, socket
        socket_factory = lambda: socket(AF_INET6, SOCK_DGRAM)
    receiver = socket_factory()
    stream_id = uuid.uuid4()
    drain = None
    try:
        receiver.bind((str(address), 0))
        bound = receiver.getsockname()
        if bound[0] != str(address) or type(bound[1]) is not int or not 0 < bound[1] <= 65535:
            raise RuntimeError("native HID media receiver binding is invalid")
        async def discard_media():
            while True:
                await receiver.recv(65535)
        drain = asyncio.create_task(discard_media())
        async with display_factory(rsd) as display:
            try:
                await asyncio.wait_for(display.start_video_stream(
                    receiver_ip=str(address), receiver_port=bound[1],
                    sender_ip=rsd.service.address[0], display_id=1,
                    client_session_id=stream_id), timeout=10)
                await asyncio.sleep(0.3)
                async with hid_factory(rsd) as hid:
                    yield hid
            finally:
                # Use the UUID chosen before negotiation: even a lost reply
                # cannot leave an unowned stream or stop another session.
                await asyncio.wait_for(display.stop_media_stream(stream_id), timeout=5)
    finally:
        if drain is not None:
            drain.cancel()
            with suppress(asyncio.CancelledError, OSError):
                await drain
        receiver.close()
