#!/usr/bin/env python3
"""Phone Appium caller of the same verified installed-APK binding."""
# SPDX-License-Identifier: Apache-2.0
import ipaddress
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapter import PhoneAdapter, main, require
from adapters.appium.adapter import AppiumAdapter


class PhoneAppiumAdapter(AppiumAdapter):
    def __init__(self, candidate=None):
        super().__init__("android")
        self.candidate = candidate

    def selected_target(self, requested, action):
        require(type(requested) is str and bool(requested), "PHONE_APPIUM_TARGET_REQUIRED")
        self.target(requested)
        return requested

    def cleanup_target(self, requested):
        return self.selected_target(requested, "cleanup")

    def installed_identity(self, selector):
        target = self.target(selector)
        capabilities = target["capabilities"]
        device = capabilities.get("appium:udid")
        require(target.get("appId") == "org.overte.phone" and type(target.get("physical")) is bool,
                "PHONE_APPIUM_PACKAGE_AND_DEVICE_CLASS_REQUIRED")
        require(capabilities.get("appium:appPackage") == "org.overte.phone",
                "PHONE_APPIUM_PACKAGE_MAPPING_REQUIRED")
        require(type(device) is str and bool(device) and device.lower() != "auto"
                and "appium:avd" not in capabilities
                and target.get("process", {}).get("kind") == "adb"
                and target["process"].get("selector") in (None, device),
                "PHONE_APPIUM_ADB_BINDING_REQUIRED")
        # Local ADB cannot prove which application a remote grid selected.
        # Keep bound mode local; the original adapter retains remote diagnostics.
        host = urlsplit(target["serverUrl"]).hostname
        local = host == "localhost"
        if not local:
            try:
                local = ipaddress.ip_address(host).is_loopback
            except ValueError:
                pass
        require(local, "PHONE_APPIUM_LOCAL_SERVER_REQUIRED")
        if "appium:app" in capabilities:
            # A capability-driven installation is still a candidate installation,
            # never an unrestricted URL/filename trusted on configuration alone.
            PhoneAdapter.require_bound_operation(self, "app.install", {"path": capabilities["appium:app"]})
        binding = PhoneAdapter(self.candidate)
        if target["physical"]:
            self.attest_android_phone_profile(target)
        else:
            # PH-003 is specifically x86_64 virtual smoke, never an ARM64 claim.
            # Read the selected target; its private configuration is expectation,
            # not evidence that a physical phone is an emulator (or vice versa).
            binding.adb.require_connected(device)
            sdk = binding.adb.prop(device, "ro.build.version.sdk")
            gles = binding.adb.prop(device, "ro.opengles.version")
            require(binding.adb.prop(device, "ro.kernel.qemu") == "1"
                    and binding.adb.prop(device, "ro.product.cpu.abi") == "x86_64"
                    and sdk.isdigit() and int(sdk) >= 26
                    and gles.isdigit() and int(gles) >= 196610,
                    "PHONE_APPIUM_X86_64_EMULATOR_REQUIRED")
        return binding.installed_identity(device)

    def describe(self, selector):
        result = super().describe(selector)
        if self.candidate is not None:
            result["executionIdentity"] = self.installed_identity(selector)
            if self.target(selector)["physical"] is False:
                result["role"] = "phone-emulator-e2e"
        return result

    def ensure_session(self, selector):
        if self.candidate is not None:
            self.installed_identity(selector)
        result = super().ensure_session(selector)
        if self.candidate is not None:
            # Appium session creation can itself install an app from capabilities.
            # Recheck before any requested operation executes, not just at the
            # enclosing runner's initial/final describe boundaries.
            self.installed_identity(selector)
        return result

    def invoke(self, selector, operation, values):
        PhoneAdapter.require_bound_operation(self, operation, values)
        result = super().invoke(selector, operation, values)
        if self.candidate is not None and operation == "app.install":
            self.installed_identity(selector)
        return result


if __name__ == "__main__":
    raise SystemExit(main(adapter_class=PhoneAppiumAdapter))
