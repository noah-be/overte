"""Keep native crash signaling scoped and compatible with integer DTX arguments."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import asyncio
from pathlib import Path
import signal
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.ios import native_process


class NativeProcess(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.info = SimpleNamespace(proclist=AsyncMock(return_value=[{
            "bundleIdentifier": "org.example.owned", "isApplication": True,
            "pid": 42, "foregroundRunning": True}]),
            execname_for_pid=AsyncMock(return_value="/verified/owned"),
            is_running_pid=AsyncMock(side_effect=[True, False]))
        self.signal_args = []
        async def signal_wire(pid, sig):
            if type(pid) is not int or type(sig) is not int:
                raise TypeError("DTX arguments require plain integers")
            self.signal_args.append((pid, sig))
        self.control = SimpleNamespace(signal=AsyncMock(side_effect=signal_wire))
        def context(value):
            result=AsyncMock(); result.__aenter__.return_value=value; return result
        self.modules = {
            "pymobiledevice3.services.dvt.instruments.dvt_provider": SimpleNamespace(DvtProvider=lambda _: context(object())),
            "pymobiledevice3.services.dvt.instruments.device_info": SimpleNamespace(DeviceInfo=lambda _: context(self.info)),
            "pymobiledevice3.services.dvt.instruments.process_control": SimpleNamespace(ProcessControl=lambda _: context(self.control))}

    async def test_abort_delivers_real_sigabrt_integer_and_verifies_original_pid_exit(self):
        with patch.dict(sys.modules, self.modules), patch.object(native_process.asyncio, "sleep", new=AsyncMock()):
            await native_process.abort(object(), "org.example.owned", "/verified/owned")
        self.assertEqual([(42, int(signal.SIGABRT))], self.signal_args)
        self.assertEqual([42, 42], [call.args[0] for call in self.info.is_running_pid.await_args_list])

    async def test_changed_executable_or_absent_client_never_receives_a_signal(self):
        self.info.execname_for_pid.side_effect=["/verified/owned", "/foreign"]
        with patch.dict(sys.modules, self.modules), self.assertRaisesRegex(RuntimeError, "executable changed"):
            await native_process.abort(object(), "org.example.owned", "/verified/owned")
        self.control.signal.assert_not_awaited()
        self.info.proclist.return_value=[]
        with patch.dict(sys.modules, self.modules), self.assertRaisesRegex(RuntimeError, "absent"):
            await native_process.abort(object(), "org.example.owned", "/verified/owned")
        self.control.signal.assert_not_awaited()

    async def test_signal_acknowledgement_does_not_replace_actual_process_exit(self):
        self.info.is_running_pid=AsyncMock(return_value=True)
        clock=Mock(side_effect=[0,11])
        with patch.dict(sys.modules, self.modules), patch.object(native_process.asyncio, "get_running_loop", return_value=SimpleNamespace(time=clock)):
            with self.assertRaisesRegex(RuntimeError, "did not terminate"):
                await native_process.abort(object(), "org.example.owned", "/verified/owned")
        self.assertEqual([(42, int(signal.SIGABRT))], self.signal_args)


if __name__ == "__main__": unittest.main()
