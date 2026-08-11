#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class V8IOSCheckpointContractTest(unittest.TestCase):
    def test_source_and_tooling_are_pinned(self):
        env = (ROOT / "ios/v8.env").read_text(encoding="utf-8")
        self.assertIn("OVERTE_IOS_V8_VERSION=12.4.254.21", env)
        self.assertRegex(env, r"OVERTE_IOS_V8_REVISION=[0-9a-f]{40}")
        self.assertRegex(env, r"OVERTE_IOS_DEPOT_TOOLS_REVISION=[0-9a-f]{40}")

    def test_build_is_static_device_arm64_and_fail_closed(self):
        script = (ROOT / "ios/tools/build-v8-ios.sh").read_text(encoding="utf-8")
        for contract in (
            'target_os = "ios"',
            'target_cpu = "arm64"',
            'target_environment = "device"',
            "ios_enable_code_signing = false",
            "use_custom_libcxx = false",
            'xcode_clang="$(xcrun --sdk iphoneos --find clang)"',
            'xcode_tool_bin="$(dirname "$xcode_clang")"',
            'bundled_llvm_bin="$source_root/third_party/llvm-build/Release+Asserts/bin"',
            "for compiler in clang clang++",
            "printf '#!/bin/sh\\nexec \"%s\" \"$@\"\\n'",
            'chmod +x "$xcode_toolchain_dir/$compiler"',
            '"llvm-ar:$bundled_llvm_bin/llvm-ar"',
            '"llvm-nm:$(xcrun --find nm)"',
            '"llvm-otool:$(xcrun --find otool)"',
            'clang_base_path = "//buildtools/overte-xcode-toolchain"',
            "clang_use_chrome_plugins = false",
            "use_lld = false",
            "v8_monolithic = true",
            "is_component_build = false",
            "v8_enable_lite_mode = true",
            "v8_jitless = true",
            "v8_enable_webassembly = false",
            "v8_use_external_startup_data = false",
            "libv8_monolith.a",
            "lipo -info",
            "target_os = ['ios']",
        ):
            self.assertIn(contract, script)
        self.assertNotIn("gclient runhooks", script)
        self.assertIn('host_python="$(command -v python3)"', script)
        self.assertIn('"$depot_root/ensure_bootstrap"', script)
        self.assertIn("^Apple clang version ", script)
        for required_build_hook in (
            "build/landmines.py",
            "tools/clang/scripts/update.py",
            "build/util/lastchange.py",
        ):
            self.assertIn(required_build_hook, script)

    def test_integrated_job_restores_validates_and_saves_checkpoint(self):
        workflow = (ROOT / ".github/workflows/ios-integrated.yml").read_text(encoding="utf-8")
        restore = workflow.index("Restore pinned static JITless V8 for iOS")
        validate = workflow.index("Validate pinned static JITless V8 for iOS")
        save = workflow.index("Save validated static JITless V8 for iOS")
        configure = workflow.index("Configure experimental full client graph")
        self.assertLess(restore, validate)
        self.assertLess(validate, save)
        self.assertLess(save, configure)
        self.assertIn("OVERTE_IOS_V8_ROOT:", workflow)


if __name__ == "__main__":
    unittest.main()
