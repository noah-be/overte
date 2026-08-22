#!/usr/bin/env python3
"""Keep Simulator and physical-device MoltenVK binding modes identical."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "interface/src/main.cpp").read_text(encoding="utf-8")
CONTEXT = (ROOT / "libraries/vk/src/vk/Context.cpp").read_text(encoding="utf-8")
SMOKE = (ROOT / "ios/ci/interface-world-simulator-smoke.sh").read_text(encoding="utf-8")
LLDB = (ROOT / "ios/ci/interface-world-simulator-lldb.sh").read_text(encoding="utf-8")

REQUEST = 'qputenv("MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS", "0")'
VERIFY = "verifyIOSMoltenVKConfiguration();"

assert REQUEST in MAIN, "the iOS app must disable Metal argument buffers itself"
assert MAIN.index(REQUEST) < MAIN.index("QtWebView::initialize()"), (
    "MoltenVK configuration must precede framework/application initialization"
)
assert "OVERTE_IOS_MOLTENVK_CONFIG requested metal_argument_buffers=0" in MAIN

for token in (
    "#include <MoltenVK/mvk_private_api.h>",
    "vkGetMoltenVKConfigurationMVK",
    "configuration.useMetalArgumentBuffers != VK_FALSE",
    "OVERTE_IOS_MOLTENVK_CONFIG effective metal_argument_buffers=0 verified=true",
):
    assert token in CONTEXT, f"effective MoltenVK verification is missing {token}"

create_instance = CONTEXT.index("void Context::createInstance()")
verify = CONTEXT.index(VERIFY, create_instance)
first_enumeration = CONTEXT.index("isExtensionPresent", create_instance)
assert verify < first_enumeration, (
    "the effective setting must be verified before the first Vulkan enumeration"
)

for harness in (SMOKE, LLDB):
    assert "SIMCTL_CHILD_MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS=0" in harness, (
        "simulator diagnostics must remain explicit and match the app-internal setting"
    )

print("PASS iOS MoltenVK argument-buffer device/simulator parity contract")
