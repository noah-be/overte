#!/usr/bin/env python3
"""Privacy-safe ADB primitives shared by Android target adapters."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


class AdbTransport:
    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or self.find_executable()

    @staticmethod
    def find_executable() -> str:
        candidates = [
            os.environ.get("OVERTE_ANDROID_ADB", ""),
            str(Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools/adb"),
            str(Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools/adb"),
            str(Path.home() / "Android/Sdk/platform-tools/adb"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
                return candidate
        raise RuntimeError("ADB executable was not found")

    def execute(self, arguments: list[str], *, target: str | None = None,
                timeout: int = 20, check: bool = True) -> str:
        command = [self.executable]
        if target:
            command += ["-s", target]
        result = subprocess.run([*command, *arguments], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout, check=False)
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
