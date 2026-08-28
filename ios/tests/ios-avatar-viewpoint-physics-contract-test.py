#!/usr/bin/env python3
"""Keep an iOS navigation viewpoint authoritative until physics can own it."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "interface/src/avatar/MyAvatar.cpp").read_text(encoding="utf-8")
application = (ROOT / "interface/src/Application.cpp").read_text(encoding="utf-8")
controller = (ROOT / "libraries/physics/src/CharacterController.h").read_text(encoding="utf-8")

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

# A serverless scene may enable the PhysicsEngine before the avatar skeleton
# has supplied a collision capsule.  Treating the engine pointer alone as
# "ready" lets harvest read a missing rigid body and reset the viewpoint to
# the origin.  The go-to may be released only after preSimulation has created
# and added the body to Bullet.
ready = "bool isEnabledAndReady() const { return (bool)_physicsEngine && _rigidBody && _inWorld; }"
assert ready in controller

# HTTP serverless navigation resolves its viewpoint before the asynchronous
# entity import commits. Both an explicit location query and the authored root
# must therefore be replayed after import on iOS.
viewpoint_start = application.index("    const auto scheduleServerlessViewpoint")
viewpoint_end = application.index("    };\n#endif", viewpoint_start)
viewpoint = application[viewpoint_start:viewpoint_end]
for token in (
    "const QUrlQuery query(domainURL);",
    'const QString locationKey = QStringLiteral("location");',
    "query.hasQueryItem(locationKey)",
    "query.queryItemValue(locationKey)",
    'namedPaths.find(QStringLiteral("/"))',
    "QTimer::singleShot(0",
    "goToViewpointForPath(",
    "viewpoint, path);",
):
    assert token in viewpoint, f"iOS committed serverless viewpoint missing {token}"
assert application.count("scheduleServerlessViewpoint(namedPaths);") == 2

print("PASS iOS startup viewpoint remains pending until physics handoff")
