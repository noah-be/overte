#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class IOSAutonomousDeviceTestContract(unittest.TestCase):
    def test_explicit_bounded_launch_channel_is_registered(self) -> None:
        main = (ROOT / "interface/src/main.cpp").read_text(encoding="utf-8")
        setup = (ROOT / "interface/src/Application_Setup.cpp").read_text(encoding="utf-8")
        self.assertIn('"ios-test-plan"', main)
        self.assertIn("MAX_ENCODED_PLAN_BYTES = 32768", setup)
        self.assertIn("MAX_ACTIONS = 128", setup)
        self.assertIn("decodeIOSAutomationPlan", setup)
        self.assertIn("iosAutonomousTestRunner.js", setup)
        self.assertIn("setIOSAutomationPlan(plan)", setup)

    def test_ios_loads_the_test_script_without_desktop_sandbox(self) -> None:
        source = (ROOT / "interface/src/Application_UI.cpp").read_text(encoding="utf-8")
        load_index = source.index("loadScript(testScript")
        ios_branch_index = source.index("#if defined(Q_OS_IOS)", load_index)
        sandbox_skip_index = source.index("handleSandboxStatus(nullptr)", ios_branch_index)
        self.assertLess(load_index, ios_branch_index)
        self.assertLess(ios_branch_index, sandbox_skip_index)

    def test_runner_is_bundled_and_has_no_dynamic_code_loading(self) -> None:
        cmake = (ROOT / "interface/CMakeLists.txt").read_text(encoding="utf-8")
        runner = (ROOT / "scripts/system/iosAutonomousTestRunner.js").read_text(encoding="utf-8")
        self.assertIn('"${CMAKE_SOURCE_DIR}/scripts"', cmake)
        self.assertIn("Test.getIOSAutomationPlan()", runner)
        self.assertIn('event("heartbeat"', runner)
        self.assertIn('event("result"', runner)
        self.assertNotIn("eval(", runner)
        self.assertNotIn("Script.include", runner)
        self.assertNotIn("Script.require", runner)

    def test_test_interface_exposes_structured_state_not_arbitrary_execution(self) -> None:
        header = (ROOT / "interface/src/scripting/TestScriptingInterface.h").read_text(encoding="utf-8")
        implementation = (ROOT / "interface/src/scripting/TestScriptingInterface.cpp").read_text(encoding="utf-8")
        self.assertIn("getIOSAutomationSnapshot", header)
        self.assertIn("logIOSAutomationEvent", header)
        self.assertIn('command == QStringLiteral("jump")', implementation)
        self.assertIn('command == QStringLiteral("tap")', implementation)
        self.assertIn('command == QStringLiteral("type_text")', implementation)
        self.assertIn('command == QStringLiteral("set_render_scale")', implementation)
        self.assertNotIn("QProcess", implementation)


if __name__ == "__main__":
    unittest.main()
