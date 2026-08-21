#!/usr/bin/env python3
"""Keep an iOS navigation viewpoint authoritative until physics can own it."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "interface/src/avatar/MyAvatar.cpp").read_text(encoding="utf-8")

start = source.index("    if (_goToPending) {")
end = source.index("    if (_goToFeetAjustment", start)
pending = source[start:end]

for token in (
    "setWorldPosition(_goToPosition);",
    "setWorldOrientation(_goToOrientation);",
    "updateSensorToWorldMatrix();",
    "#if defined(Q_OS_IOS)",
    "qApp->isPhysicsEnabled()",
    "_characterController.isEnabledAndReady()",
    "if (canFinalizeGoTo)",
    "_goToPending = false;",
):
    assert token in pending, f"iOS pending viewpoint handoff missing {token}"

assert pending.index("updateSensorToWorldMatrix();") < pending.index("if (canFinalizeGoTo)")
assert pending.index("if (canFinalizeGoTo)") < pending.index("_goToPending = false;")

harvest_start = source.index("void MyAvatar::harvestResultsFromPhysicsSimulation")
harvest_end = source.index("QString MyAvatar::getScriptedMotorFrame", harvest_start)
harvest = source[harvest_start:harvest_end]
assert "_characterController.needsSafeLandingSupport() || _goToPending" in harvest

print("PASS iOS startup viewpoint remains pending until physics handoff")
