#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

"""Keep --testScript startup shared by iOS and desktop sandbox policies."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "interface/src/Application_UI.cpp").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


startup = SOURCE.split(
    "nodeList->getDomainHandler().resetting();", 1
)[1].split("auto menu = Menu::getInstance();", 1)[0]
ios_guard = "#if defined(Q_OS_IOS)"
require(startup.count(ios_guard) == 1, "startup sandbox policy must have one iOS branch")

shared, platform_policy = startup.split(ios_guard, 1)
ios_policy, desktop_policy = platform_policy.split("#else", 1)
desktop_policy = desktop_policy.rsplit("#endif", 1)[0]

test_property = "QVariant testProperty = property(hifi::properties::TEST);"
test_url = "const auto testScript = testProperty.toUrl();"
load_call = (
    "DependencyManager::get<ScriptEngines>()->loadScript("
    "testScript, false, false, false, false, _quitWhenFinished);"
)

require(test_property in shared, "--testScript lookup is not shared with iOS startup")
require(test_url in shared, "--testScript URL conversion is not shared with iOS startup")
require(load_call in shared, "iOS startup cannot load the requested --testScript")
require(
    shared.index(test_property) < shared.index(test_url) < shared.index(load_call),
    "--testScript startup operations are out of order",
)
require(startup.count(load_call) == 1, "--testScript must be loaded exactly once")

require(
    "QMetaObject::invokeMethod(this, [this] {" in ios_policy
    and "handleSandboxStatus(nullptr);" in ios_policy
    and "Qt::QueuedConnection" in ios_policy,
    "iOS must retain the queued sandbox-absent startup path",
)
require(
    "SandboxUtils::getStatus()" not in ios_policy,
    "iOS must not contact the unavailable desktop Sandbox process",
)

require(
    "if (testProperty.isValid())" in desktop_policy
    and "if (!_urlParam.isEmpty())" in desktop_policy
    and desktop_policy.count("SandboxUtils::getStatus()") == 2
    and desktop_policy.count("handleSandboxStatus(reply)") == 2,
    "desktop Sandbox/test-script startup behavior changed",
)
require(
    load_call not in desktop_policy,
    "desktop startup would load --testScript more than once",
)

print("PASS iOS shared --testScript startup contract")
