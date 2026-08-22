#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import argparse
import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "ios/tools/v8-build-plan.py"
SPEC = importlib.util.spec_from_file_location("v8_build_plan", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class V8BuildPlanTest(unittest.TestCase):
    def setUp(self):
        self.original_env = MODULE.ENV_PATH
        self.original_patch = MODULE.SIMULATOR_PATCH

    def tearDown(self):
        MODULE.ENV_PATH = self.original_env
        MODULE.SIMULATOR_PATCH = self.original_patch

    @staticmethod
    def arguments(**changes):
        values = {
            "platform": "device",
            "runner_arch": "ARM64",
            "xcode_build": "17F113",
            "sdk_version": "26.5",
            "sdk_build": "23F77",
            "compiler_version": "Apple clang version 17.0.0 (clang-1700.0.13.5)",
            "compiler_sha256": "1" * 64,
        }
        values.update(changes)
        return argparse.Namespace(**values)

    def test_identical_inputs_are_stable_and_arch_spelling_is_canonical(self):
        arm64 = MODULE.build_plan(self.arguments(runner_arch="ARM64"))
        aarch64 = MODULE.build_plan(self.arguments(runner_arch="aarch64"))
        self.assertEqual(MODULE.identity(arm64), MODULE.identity(aarch64))
        self.assertEqual(arm64["target"]["runnerArch"], "arm64")

    def test_device_identity_ignores_simulator_only_patch_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            patch = pathlib.Path(temporary) / "simulator.patch"
            MODULE.SIMULATOR_PATCH = patch
            patch.write_text("first simulator policy\n", encoding="utf-8")
            first_device = MODULE.identity(MODULE.build_plan(self.arguments()))
            first_simulator = MODULE.identity(
                MODULE.build_plan(self.arguments(platform="simulator"))
            )
            patch.write_text("second simulator policy\n", encoding="utf-8")
            second_device = MODULE.identity(MODULE.build_plan(self.arguments()))
            second_simulator = MODULE.identity(
                MODULE.build_plan(self.arguments(platform="simulator"))
            )
        self.assertEqual(first_device, second_device)
        self.assertNotEqual(first_simulator, second_simulator)

    def test_every_output_affecting_toolchain_input_changes_identity(self):
        baseline = MODULE.identity(MODULE.build_plan(self.arguments()))
        variants = (
            {"xcode_build": "17F114"},
            {"sdk_version": "26.6"},
            {"sdk_build": "23F78"},
            {"compiler_version": "Apple clang version 17.0.1"},
            {"compiler_sha256": "2" * 64},
            {"platform": "simulator"},
        )
        for changes in variants:
            with self.subTest(changes=changes):
                changed = MODULE.identity(MODULE.build_plan(self.arguments(**changes)))
                self.assertNotEqual(baseline, changed)

    def test_pinned_source_and_build_flags_are_in_identity(self):
        plan = MODULE.build_plan(self.arguments())
        self.assertEqual(plan["schemaVersion"], 2)
        self.assertEqual(plan["source"]["v8Version"], "12.4.254.21")
        self.assertRegex(plan["source"]["v8Revision"], r"^[0-9a-f]{40}$")
        flags = plan["build"]["gnArgs"]
        for required in (
            "is_component_build = false",
            "v8_monolithic = true",
            "v8_enable_lite_mode = true",
            "v8_jitless = true",
            "v8_enable_webassembly = false",
            'target_environment = "device"',
        ):
            self.assertIn(required, flags)
        self.assertEqual(plan["build"]["patches"], [])

    def test_deployment_policy_change_invalidates_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            env = pathlib.Path(temporary) / "v8.env"
            original = self.original_env.read_text(encoding="utf-8")
            MODULE.ENV_PATH = env
            env.write_text(original, encoding="utf-8")
            first = MODULE.identity(MODULE.build_plan(self.arguments()))
            env.write_text(
                original.replace(
                    "OVERTE_IOS_V8_DEPLOYMENT_TARGET=15.0",
                    "OVERTE_IOS_V8_DEPLOYMENT_TARGET=16.0",
                ),
                encoding="utf-8",
            )
            second = MODULE.identity(MODULE.build_plan(self.arguments()))
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
