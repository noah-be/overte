"""Observe and signal only the authenticated configured physical iOS client."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import asyncio
import signal


async def observe(rsd, bundle, executable):
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.device_info import DeviceInfo
    async with DvtProvider(rsd) as provider:
        async with DeviceInfo(provider) as info:
            matches = [p for p in await info.proclist()
                       if p.get("bundleIdentifier") == bundle and p.get("isApplication") is True]
            if not matches:
                return None
            if len(matches) != 1:
                raise RuntimeError("configured native process is ambiguous")
            process = matches[0]
            pid = process.get("pid")
            if (type(pid) is not int or pid <= 0
                    or type(process.get("foregroundRunning")) is not bool
                    or await info.execname_for_pid(pid) != executable):
                raise RuntimeError("configured native process identity is invalid")
            return {"bundleId": bundle, "pid": pid,
                    "foreground": process["foregroundRunning"]}


async def abort(rsd, bundle, executable):
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.device_info import DeviceInfo
    from pymobiledevice3.services.dvt.instruments.process_control import ProcessControl
    process = await observe(rsd, bundle, executable)
    if process is None:
        raise RuntimeError("configured process is absent before abort")
    async with DvtProvider(rsd) as provider:
        async with DeviceInfo(provider) as info:
            if await info.execname_for_pid(process["pid"]) != executable:
                raise RuntimeError("configured executable changed before abort")
            async with ProcessControl(provider) as control:
                await control.signal(process["pid"], signal.SIGABRT)
            deadline = asyncio.get_running_loop().time() + 10
            while await info.is_running_pid(process["pid"]):
                if asyncio.get_running_loop().time() >= deadline:
                    raise RuntimeError("configured native abort did not terminate the process")
                await asyncio.sleep(0.1)

