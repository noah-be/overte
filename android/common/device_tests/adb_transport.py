#!/usr/bin/env python3
"""Privacy-safe ADB primitives shared by Android target adapters."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import time


class AdbTransport:
    def __init__(self, executable: str | None = None, *,
                 server_port: int | None = None) -> None:
        self.executable = executable or self.find_executable()
        self.command = ([sys.executable, self.executable]
                        if os.name == "nt" and self.executable.lower().endswith(".py")
                        else [self.executable])
        if server_port is not None:
            if (isinstance(server_port, bool) or not isinstance(server_port, int)
                    or not 1 <= server_port <= 65535):
                raise RuntimeError("ADB server port is invalid")
            self.command += ["-P", str(server_port)]

    @staticmethod
    def find_executable() -> str:
        candidates = [
            os.environ.get("OVERTE_ANDROID_ADB", ""),
            str(Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools/adb"),
            str(Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools/adb"),
            str(Path.home() / "Android/Sdk/platform-tools/adb"),
            shutil.which("adb") or "",
        ]
        for candidate in candidates:
            is_python_mock = os.name == "nt" and candidate.lower().endswith(".py")
            if candidate and Path(candidate).is_file() and (is_python_mock or os.access(candidate, os.X_OK)):
                return candidate
        raise RuntimeError("ADB executable was not found")

    def execute(self, arguments: list[str], *, target: str | None = None,
                timeout: int = 20, check: bool = True) -> str:
        command = list(self.command)
        if target:
            command += ["-s", target]
        try:
            result = subprocess.run([*command, *arguments], text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=timeout, check=False)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("ADB operation timed out") from error
        if check and result.returncode != 0:
            raise RuntimeError("ADB operation failed")
        return result.stdout.replace("\r", "")

    def shell(self, target: str, *arguments: str, check: bool = True) -> str:
        return self.execute(["shell", *arguments], target=target, check=check)

    def prop(self, target: str, name: str) -> str:
        return self.shell(target, "getprop", name, check=False).strip()

    def authorized_targets(self) -> list[str]:
        lines = self.execute(["devices", "-l"]).splitlines()
        return [parts[0] for line in lines
                if len(parts := line.split()) >= 2 and parts[1] == "device"]

    def require_connected(self, target: str) -> None:
        if self.execute(["get-state"], target=target, check=False).strip() != "device":
            raise RuntimeError("target is not connected and authorized")

    def read_debug_app_file(self, target: str, package: str, relative_path: str,
                            *, attempts: int = 60, interval_seconds: float = 0.25) -> str:
        """Read one app-private debug artifact without granting broad storage access."""
        path = PurePosixPath(relative_path)
        if (not re.fullmatch(r"[A-Za-z0-9_]+(?:[.][A-Za-z0-9_]+)+", package)
                or not relative_path or "\\" in relative_path or path.is_absolute()
                or any(part in {"", ".", ".."} for part in path.parts)
                or str(path) != relative_path):
            raise RuntimeError("debug app file selector is unsafe")
        if attempts < 1 or interval_seconds < 0:
            raise RuntimeError("debug app file retry policy is invalid")
        for attempt in range(attempts):
            raw = self.shell(target, "run-as", package, "cat", relative_path, check=False)
            if raw:
                return raw
            if attempt + 1 < attempts:
                time.sleep(interval_seconds)
        return ""

    def process_state(self, target: str, package: str) -> dict:
        pid = self.shell(target, "pidof", "-s", package, check=False).strip()
        if not pid.isdigit():
            return {"running": False, "identity": None}
        stat = self.shell(target, "cat", f"/proc/{pid}/stat", check=False).strip().split()
        start_ticks = stat[21] if len(stat) > 21 and stat[21].isdigit() else "unknown"
        return {"running": True, "identity": f"{pid}:{start_ticks}"}

    def foreground_package(self, target: str) -> str | None:
        activities = self.shell(target, "dumpsys", "activity", "activities", check=False)
        pattern = re.compile(
            r"^\s*(?:mResumedActivity|topResumedActivity|ResumedActivity|Resumed):.*?\s([A-Za-z0-9._]+)/(?:[A-Za-z0-9._$]+)")
        for line in activities.splitlines():
            if match := pattern.search(line):
                return match.group(1)
        return None

    @staticmethod
    def integer_match(pattern: str, text: str) -> int | None:
        match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
        return int(match.group(1)) if match else None

    def telemetry_snapshot(self, target: str, package: str) -> dict:
        memory = self.shell(target, "dumpsys", "meminfo", package, check=False)
        total = re.search(r"^\s*TOTAL\s+(\d+)\s+(\d+)", memory, re.MULTILINE)
        battery = self.shell(target, "dumpsys", "battery", check=False)
        thermal = self.shell(target, "dumpsys", "thermalservice", check=False)
        return {
            "batteryLevel": self.integer_match(r"^\s*level:\s*(\d+)", battery),
            "batteryTemperatureDeciC": self.integer_match(
                r"^\s*temperature:\s*(\d+)", battery),
            "memoryPssKb": int(total.group(1)) if total else None,
            "memoryRssKb": int(total.group(2)) if total else None,
            "thermalStatus": self.integer_match(
                r"(?:Thermal Status:|mStatus=)\s*(\d+)", thermal),
        }
