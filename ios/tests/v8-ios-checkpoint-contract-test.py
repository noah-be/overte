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

    def test_build_is_static_arm64_for_device_or_simulator_and_fail_closed(self):
        script = (ROOT / "ios/tools/build-v8-ios.sh").read_text(encoding="utf-8")
        plan = (ROOT / "ios/tools/v8-build-plan.py").read_text(encoding="utf-8")
        for contract in (
            'OVERTE_IOS_V8_PLATFORM:-device',
            'sdk_name="iphoneos"',
            'sdk_name="iphonesimulator"',
            'target_environment="device"',
            'target_environment="simulator"',
            'xcode_clang="$(xcrun --sdk "$sdk_name" --find clang)"',
            'xcode_tool_bin="$(dirname "$xcode_clang")"',
            'bundled_llvm_bin="$source_root/third_party/llvm-build/Release+Asserts/bin"',
            "for compiler in clang clang++",
            "printf '#!/bin/sh\\nexec \"%s\" \"$@\"\\n'",
            'chmod +x "$xcode_toolchain_dir/$compiler"',
            '"llvm-ar:$bundled_llvm_bin/llvm-ar"',
            '"ld64.lld:$bundled_llvm_bin/ld64.lld"',
            '"llvm-nm:$(xcrun --find nm)"',
            '"llvm-otool:$(xcrun --find otool)"',
            'export PATH="$xcode_toolchain_dir:$PATH"',
            "libv8_monolith.a",
            "lipo -info",
            "target_os = ['ios']",
            "OVERTE_IOS_V8_COMPILER_LAUNCHER",
            "OVERTE_IOS_V8_PLATFORM=$platform",
            'git -C "$source_root" apply --check "$simulator_patch"',
            'git -C "$source_root" apply --reverse --check "$simulator_patch"',
            'v8-$target_environment-build-identity.json',
            'build-identity.json',
            'write_current_identity',
            'cmp -s "$expected_identity"',
            'phase_start compile-v8-monolith',
            'phase_start package-output',
            'phase_start validate-output',
        ):
            self.assertIn(contract, script)
        for contract in (
            'target_os = "ios"',
            'target_cpu = "arm64"',
            '"targetEnvironment": "device"',
            'f\'target_environment = "{target["targetEnvironment"]}"\'',
            "ios_enable_code_signing = false",
            "use_custom_libcxx = false",
            'clang_base_path = "//buildtools/overte-xcode-toolchain"',
            "clang_use_chrome_plugins = false",
            "use_lld = false",
            "v8_monolithic = true",
            "is_component_build = false",
            "v8_enable_lite_mode = true",
            "v8_jitless = true",
            "v8_enable_webassembly = false",
            "v8_use_external_startup_data = false",
        ):
            self.assertIn(contract, plan)
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
        v8 = workflow[workflow.index("  v8-checkpoint:"):workflow.index("  integrated-configure:")]
        names = [
            "Restore pinned static JITless V8 for iOS",
            "Probe durable static JITless V8 checkpoint",
            "Restore durable static JITless V8 checkpoint",
            "Restore trusted apple-ios V8 checkpoint for feature branches",
            "Restore reviewed legacy V8 checkpoint for v2 promotion",
            "Restore V8 compiler recovery checkpoint",
            "Report V8 checkpoint decision",
            "Build pinned static JITless V8 for iOS",
            "Validate pinned static JITless V8 for iOS",
            "Create durable static JITless V8 checkpoint",
            "Upload durable static JITless V8 checkpoint",
            "Save validated static JITless V8 for iOS",
        ]
        positions = [v8.index(name) for name in names]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("--kind v8", v8)
        self.assertIn("v8-build-plan.py identity", v8)
        self.assertIn("overte-v8-ios-v2-${identity}", v8)
        self.assertNotIn('recipe_hash="$(shasum -a 256 ios/v8.env ios/tools/build-v8-ios.sh', v8)
        for identity_input in (
            "--xcode-build",
            "--sdk-version",
            "--sdk-build",
            "--compiler-version",
            "--compiler-sha256",
            "--runner-arch",
        ):
            self.assertIn(identity_input, v8)
        self.assertIn("--compiler-live-log", v8)
        self.assertIn("--output-log", v8)
        self.assertIn("OVERTE_IOS_V8_COMPILER_LAUNCHER", v8)
        self.assertIn("Save V8 compiler recovery checkpoint", v8)
        self.assertIn("V8 sccache state before rebuild", v8)
        self.assertIn("V8 sccache state after rebuild", v8)
        self.assertIn("report-sccache-stats.py", v8)
        self.assertIn("--phase after --require-activity", v8)
        self.assertIn("V8 checkpoint source=$source", v8)
        self.assertIn("V8 rebuild reason=$reason", v8)
        self.assertIn("SCCACHE_MULTILEVEL_WRITE_ERROR_POLICY: l0", v8)
        self.assertIn('SCCACHE_IDLE_TIMEOUT: "0"', v8)
        self.assertIn("--max-age-days 75", v8)
        self.assertNotIn("retention-days: 90", v8)
        self.assertIn("retention-days: 30", v8)
        self.assertIn("OVERTE_IOS_V8_ROOT:", workflow)
        self.assertIn("--expected-branch apple-ios", v8)
        self.assertIn("github.ref_name != 'apple-ios'", v8)
        self.assertIn("source=trusted-apple-ios-promotion", v8)

        build_step = v8[
            v8.index("- name: Build pinned static JITless V8 for iOS"):
            v8.index("- name: Report V8 compiler checkpoint statistics")
        ]
        self.assertIn("steps.v8-cache.outputs.cache-hit != 'true'", build_step)
        self.assertIn("steps.v8-artifact.outputs.restored != 'true'", build_step)
        self.assertIn("steps.v8-apple-ios-artifact.outputs.restored != 'true'", build_step)
        self.assertIn("steps.v8-legacy-artifact.outputs.restored != 'true'", build_step)
        self.assertNotIn("github.run_id", build_step)
        self.assertNotIn("github.run_attempt", build_step)

        consumer = workflow[workflow.index("  integrated-configure:"):]
        self.assertIn("id: integrated-v8-cache", consumer)
        self.assertNotIn("fail-on-cache-miss: true", consumer)
        self.assertIn("Restore durable V8 artifact after cache miss", consumer)
        self.assertIn("needs.v8-checkpoint.outputs.artifact-prefix", consumer)
        self.assertIn("OVERTE_CHECKPOINT_BRANCH: ${{ github.ref_name }}", consumer)
        self.assertIn('--expected-branch "$OVERTE_CHECKPOINT_BRANCH"', consumer)
        self.assertIn("Fail closed without validated V8", consumer)

    def test_reviewed_legacy_promotion_is_exact_and_digest_bound(self):
        legacy = (ROOT / "ios/v8-legacy-checkpoints.env").read_text(encoding="utf-8")
        self.assertIn("OVERTE_IOS_V8_LEGACY_DEVICE_XCODE_BUILD=17F113", legacy)
        self.assertIn("OVERTE_IOS_V8_LEGACY_DEVICE_SDK_VERSION=26.5", legacy)
        self.assertRegex(
            legacy,
            r"OVERTE_IOS_V8_LEGACY_DEVICE_LIBRARY_SHA256=[0-9a-f]{64}",
        )
        self.assertIn("31796177166", legacy)

if __name__ == "__main__":
    unittest.main()
