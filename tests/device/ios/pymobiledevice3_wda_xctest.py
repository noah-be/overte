#!/usr/bin/env python3
"""Keep the current PyMobileDevice3 XCTest handshake alive for one WDA run."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
from contextlib import suppress
import ctypes
from importlib.metadata import version
import ipaddress
import json
import os
import re
import signal
import sys

from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
from pymobiledevice3.exceptions import ConnectionTerminatedError
from pymobiledevice3.services.dvt.testmanaged.xcuitest import TestConfig, XCUITestService
from pymobiledevice3.services.wda import WdaServiceClient


MAX_REQUEST_BYTES = 16 * 1024
READY_TIMEOUT_SECONDS = 34.0
GRACEFUL_STOP_TIMEOUT_SECONDS = 10.0
BUNDLE_ID = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9-]*(?:[.][A-Za-z0-9][A-Za-z0-9-]*)+"
)
ENVIRONMENT_KEYS = {"USE_PORT", "WDA_PRODUCT_BUNDLE_IDENTIFIER"}
FAILURE_PHASES = {
    "host-platform",
    "parent-death-signal",
    "parent-lost",
    "request",
    "request-endpoint",
    "request-environment",
    "runtime-version",
    "rsd-connect",
    "rsd-identity",
    "xctest-config",
    "xctest-start",
    "wda-ready",
    "wda-ready-runner-disconnected",
    "wda-ready-runner-error",
    "wda-ready-runner-returned",
    "wda-ready-runner-runtime",
    "wda-ready-runner-timeout",
    "wda-ready-timeout",
    "session-lifetime",
    "session-lifetime-runner-disconnected",
    "session-lifetime-runner-error",
    "session-lifetime-runner-returned",
    "session-lifetime-runner-runtime",
    "session-lifetime-runner-timeout",
    "unexpected",
}


class LaunchError(RuntimeError):
    """The private WDA launch contract could not be satisfied."""

    def __init__(self, phase: str) -> None:
        if phase not in FAILURE_PHASES:
            phase = "unexpected"
        self.phase = phase
        super().__init__(phase)


class AppiumKeepAliveEvent(asyncio.Event):
    """Keep WDA's XCTest transport open until Appium ends the session.

    WebDriverAgent's bootstrap test plan may report completion after its HTTP
    server is ready.  A normal PyMobileDevice3 run closes all DTX providers at
    that point, which also tears down the preinstalled runner.  Appium owns the
    longer session lifetime, so only an explicit keeper signal or a real DTX
    disconnect may end this run.
    """

    def set(self) -> None:
        pass

    def stop(self) -> None:
        """Complete the test plan only when Appium releases its ownership.

        XCTest's own completion callback must not end WDA while the Appium
        session is alive.  Conversely, cancelling XCUITestService.run during
        Appium cleanup closes its DTX providers abruptly and can leave
        testmanagerd unable to accept the next runner.  This explicit path
        lets the service unwind all three providers in protocol order.
        """
        super().set()


def completed_runner_phase(runner: asyncio.Task, prefix: str) -> str:
    """Reduce a completed XCTest task to an allowlisted, value-free phase."""
    if runner.cancelled():
        return f"{prefix}-runner-error"
    error = runner.exception()
    if error is None:
        return f"{prefix}-runner-returned"
    if isinstance(error, ConnectionTerminatedError):
        return f"{prefix}-runner-disconnected"
    if isinstance(error, TimeoutError):
        return f"{prefix}-runner-timeout"
    if isinstance(error, RuntimeError):
        return f"{prefix}-runner-runtime"
    return f"{prefix}-runner-error"


def parent_death_signal() -> None:
    """Ensure a crashed Appium parent cannot orphan an XCTest session."""
    if not sys.platform.startswith("linux"):
        raise LaunchError("host-platform")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise LaunchError("parent-death-signal")
    if os.getppid() == 1:
        raise LaunchError("parent-lost")


def read_request() -> dict:
    line = sys.stdin.buffer.readline(MAX_REQUEST_BYTES + 1)
    if (not line.endswith(b"\n") or len(line) > MAX_REQUEST_BYTES
            or b"\r" in line or b"\0" in line):
        raise LaunchError("request")
    try:
        value = json.loads(line)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LaunchError("request") from error
    keys = {"schemaVersion", "udid", "rsdHost", "rsdPort", "wdaBundleId",
            "wdaPort", "environment"}
    if (not isinstance(value, dict) or set(value) != keys
            or value.get("schemaVersion") != 1
            or isinstance(value.get("schemaVersion"), bool)
            or not isinstance(value.get("udid"), str)
            or not 8 <= len(value["udid"]) <= 128
            or any(character in value["udid"] for character in "\0\r\n")
            or not isinstance(value.get("rsdHost"), str)
            or not 2 <= len(value["rsdHost"]) <= 128
            or not isinstance(value.get("rsdPort"), int)
            or isinstance(value.get("rsdPort"), bool)
            or not 1 <= value["rsdPort"] <= 65535
            or not isinstance(value.get("wdaPort"), int)
            or isinstance(value.get("wdaPort"), bool)
            or value["wdaPort"] != 8100
            or not isinstance(value.get("wdaBundleId"), str)
            or len(value["wdaBundleId"]) > 255
            or not BUNDLE_ID.fullmatch(value["wdaBundleId"])):
        raise LaunchError("request")
    try:
        ipaddress.ip_address(value["rsdHost"].split("%", 1)[0])
    except ValueError as error:
        raise LaunchError("request-endpoint") from error
    environment = value.get("environment")
    if (not isinstance(environment, dict) or set(environment) != ENVIRONMENT_KEYS
            or any(not isinstance(item, str) or len(item) > 255
                   or any(character in item for character in "\0\r\n")
                   for item in environment.values())
            or environment.get("USE_PORT") != "8100"
            or environment.get("WDA_PRODUCT_BUNDLE_IDENTIFIER")
            != value["wdaBundleId"]):
        raise LaunchError("request-environment")
    return value


async def run_xctest(request: dict) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signal_number, stop.set)

    phase = "rsd-connect"
    try:
        async with RemoteServiceDiscoveryService(
                (request["rsdHost"], request["rsdPort"])) as service_provider:
            if service_provider.udid != request["udid"]:
                raise LaunchError("rsd-identity")
            phase = "xctest-config"
            configuration = await TestConfig.create_for(
                service_provider, runner_bundle_id=request["wdaBundleId"]
            )
            configuration.runner_app_env = request["environment"]
            keep_alive = AppiumKeepAliveEvent()
            phase = "xctest-start"
            runner = asyncio.create_task(
                XCUITestService(service_provider).run(
                    configuration, test_done_event=keep_alive
                ),
                name="overte-wda-xctest",
            )
            client = WdaServiceClient(
                service_provider=service_provider,
                port=request["wdaPort"],
                timeout=2.0,
            )
            deadline = loop.time() + READY_TIMEOUT_SECONDS
            phase = "wda-ready"
            while True:
                if runner.done():
                    failure_phase = completed_runner_phase(runner, "wda-ready")
                    raise LaunchError(failure_phase)
                if loop.time() >= deadline:
                    raise LaunchError("wda-ready-timeout")
                try:
                    status = await asyncio.wait_for(client.get_status(), timeout=2.5)
                except Exception:
                    await asyncio.sleep(0.1)
                    continue
                if (isinstance(status, dict)
                        and isinstance(status.get("value"), dict)
                        and status["value"].get("ready") is True):
                    break
                await asyncio.sleep(0.1)

            sys.stdout.write("READY\n")
            sys.stdout.flush()
            phase = "session-lifetime"
            stopped = asyncio.create_task(stop.wait(), name="overte-wda-stop")
            done, _pending = await asyncio.wait(
                {runner, stopped}, return_when=asyncio.FIRST_COMPLETED
            )
            if runner in done and not stop.is_set():
                failure_phase = completed_runner_phase(runner, "session-lifetime")
                raise LaunchError(failure_phase)
            if stop.is_set():
                keep_alive.stop()
                try:
                    await asyncio.wait_for(
                        asyncio.shield(runner),
                        timeout=GRACEFUL_STOP_TIMEOUT_SECONDS,
                    )
                except TimeoutError as error:
                    raise LaunchError("session-lifetime-runner-timeout") from error
                failure_phase = completed_runner_phase(runner, "session-lifetime")
                if failure_phase != "session-lifetime-runner-returned":
                    raise LaunchError(failure_phase)
    except LaunchError:
        raise
    except BaseException as error:
        raise LaunchError(phase) from error
    finally:
        if "runner" in locals() and not runner.done():
            runner.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await runner


def main() -> int:
    try:
        parent_death_signal()
        if version("pymobiledevice3") != "11.1.5":
            raise LaunchError("runtime-version")
        asyncio.run(run_xctest(read_request()))
        return 0
    except BaseException as error:
        phase = error.phase if isinstance(error, LaunchError) else "unexpected"
        sys.stderr.write(
            f"error: immutable Fedora XCTest keeper failed phase={phase}\n"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
