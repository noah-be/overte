// In-client observation probe for physical-device E2E tests. This script is
// loaded only through Interface's --testScript command-line option and writes
// snapshots into --testResultsLocation through the existing Test API.
(function () {
    "use strict";

    var tablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
    var stableEntitySamples = 0;
    var previousEntityCount = -1;
    var stableAvatarSamples = 0;
    var previousAvatarPosition = null;
    var sceneReady = false;
    var spawnApplied = false;
    var spawnRequestPending = false;
    var sampleSequence = 0;
    var probeErrorCount = 0;
    var lastProbeError = "";
    var lastSampleEpochMs = 0;
    var lastHeartbeatEpochMs = 0;
    var sampleIntervalMs = 250;
    var heartbeatIntervalMs = 5000;
    var fixtureMarkers = ["OVERTE_E2E_FLOOR", "OVERTE_E2E_NORTH", "OVERTE_E2E_EAST", "OVERTE_E2E_ORIGIN"];
    var expectedSpawn = { x: 0.0, y: 2.0, z: 4.0 };

    function vector(value) {
        return { x: Number(value.x), y: Number(value.y), z: Number(value.z) };
    }

    function controllerPose(channel) {
        var pose = Controller.getPoseValue(channel);
        if (!pose || !pose.valid) {
            return { valid: false, translation: null, rotation: null };
        }
        return {
            valid: true,
            translation: vector(pose.translation),
            rotation: {
                x: Number(pose.rotation.x),
                y: Number(pose.rotation.y),
                z: Number(pose.rotation.z),
                w: Number(pose.rotation.w)
            }
        };
    }

    function openXrAxes() {
        var openXr = Controller.Hardware.OpenXR;
        if (openXr === undefined) {
            return null;
        }
        return {
            lx: Number(Controller.getValue(openXr.LX)),
            ly: Number(Controller.getValue(openXr.LY)),
            rx: Number(Controller.getValue(openXr.RX)),
            ry: Number(Controller.getValue(openXr.RY))
        };
    }

    function effectiveInputState() {
        var application = Controller.Hardware.Application;
        var right = Number(Controller.getValue(application.RightHandDominant)) > 0.5;
        var left = Number(Controller.getValue(application.LeftHandDominant)) > 0.5;
        return {
            dominantHand: right && !left ? "right" : (left && !right ? "left" : "invalid"),
            advancedMovementControls:
                Number(Controller.getValue(application.AdvancedMovement)) > 0.5
        };
    }

    function sample(now) {
        var ids = Entities.findEntities(MyAvatar.position, 1000.0);
        var foundMarkers = {};
        var floorTopY = null;
        var index;
        for (index = 0; index < ids.length; index += 1) {
            var properties = Entities.getEntityProperties(ids[index], ["name", "position", "dimensions"]);
            if (fixtureMarkers.indexOf(properties.name) !== -1) {
                foundMarkers[properties.name] = true;
            }
            if (properties.name === "OVERTE_E2E_FLOOR") {
                floorTopY = Number(properties.position.y) + Number(properties.dimensions.y) / 2.0;
            }
        }
        if (ids.length === previousEntityCount) {
            stableEntitySamples += 1;
        } else {
            stableEntitySamples = 0;
            previousEntityCount = ids.length;
        }
        var markerCount = Object.keys(foundMarkers).length;
        var avatarPosition = vector(MyAvatar.position);
        var spawnDeltaX = avatarPosition.x - expectedSpawn.x;
        var spawnDeltaZ = avatarPosition.z - expectedSpawn.z;
        var avatarAtSpawn = spawnDeltaX * spawnDeltaX + spawnDeltaZ * spawnDeltaZ <= 1.0;
        if (!spawnApplied && markerCount === fixtureMarkers.length && floorTopY !== null) {
            if (spawnRequestPending && avatarAtSpawn) {
                spawnApplied = true;
            } else {
                MyAvatar.velocity = { x: 0.0, y: 0.0, z: 0.0 };
                MyAvatar.goToLocation(expectedSpawn, false);
                previousAvatarPosition = null;
                stableAvatarSamples = 0;
                spawnRequestPending = true;
            }
        }
        if (previousAvatarPosition !== null) {
            var deltaX = avatarPosition.x - previousAvatarPosition.x;
            var deltaY = avatarPosition.y - previousAvatarPosition.y;
            var deltaZ = avatarPosition.z - previousAvatarPosition.z;
            stableAvatarSamples = (deltaX * deltaX + deltaY * deltaY + deltaZ * deltaZ <= 0.0004)
                ? stableAvatarSamples + 1 : 0;
        }
        previousAvatarPosition = avatarPosition;
        spawnDeltaX = avatarPosition.x - expectedSpawn.x;
        spawnDeltaZ = avatarPosition.z - expectedSpawn.z;
        var avatarAboveFloor = floorTopY !== null && avatarPosition.y >= floorTopY - 0.05;
        avatarAtSpawn = spawnDeltaX * spawnDeltaX + spawnDeltaZ * spawnDeltaZ <= 1.0;
        if (!sceneReady && spawnApplied && markerCount === fixtureMarkers.length && stableEntitySamples >= 3
                && stableAvatarSamples >= 4 && avatarAboveFloor && avatarAtSpawn) {
            sceneReady = true;
        }
        var orientation = Quat.safeEulerAngles(Camera.orientation);
        sampleSequence += 1;
        Test.saveObject({
            schemaVersion: 1,
            sampleEpochMs: now,
            sampleSequence: sampleSequence,
            build: {
                platform: String(About.platform),
                version: String(About.buildVersion),
                date: String(About.buildDate)
            },
            application: {
                running: true,
                foreground: Boolean(Window.hasFocus())
            },
            input: effectiveInputState(),
            scene: {
                url: String(AddressManager.href),
                ready: sceneReady,
                entityCount: ids.length,
                fixtureMarkerCount: markerCount,
                floorTopY: floorTopY,
                avatarAboveFloor: avatarAboveFloor,
                spawnApplied: spawnApplied,
                spawnValidated: sceneReady
            },
            avatar: {
                position: avatarPosition,
                bodyYawDegrees: Number(MyAvatar.bodyYaw)
            },
            view: {
                orientation: vector(orientation)
            },
            tablet: {
                open: Boolean(tablet.tabletShown),
                home: Boolean(tablet.onHomeScreen()),
                toolbarMode: Boolean(tablet.toolbarMode)
            },
            controller: {
                route: {
                    openxrAxes: openXrAxes(),
                    standardLy: Number(Controller.getValue(Controller.Standard.LY)),
                    translateZAction: Number(Controller.getValue(Controller.Actions.TranslateZ)),
                    rawTranslateZDriveKey: Number(MyAvatar.getRawDriveKey(DriveKeys.TRANSLATE_Z)),
                    translateZDriveKeyDisabled: Boolean(MyAvatar.isDriveKeyDisabled(DriveKeys.TRANSLATE_Z))
                },
                axes: {
                    lx: Number(Controller.getValue(Controller.Standard.LX)),
                    ly: Number(Controller.getValue(Controller.Standard.LY)),
                    rx: Number(Controller.getValue(Controller.Standard.RX)),
                    ry: Number(Controller.getValue(Controller.Standard.RY)),
                    leftTrigger: Number(Controller.getValue(Controller.Standard.LT)),
                    rightTrigger: Number(Controller.getValue(Controller.Standard.RT)),
                    leftGrip: Number(Controller.getValue(Controller.Standard.LeftGrip)),
                    rightGrip: Number(Controller.getValue(Controller.Standard.RightGrip))
                },
                buttons: {
                    menu: Boolean(Controller.getValue(Controller.Standard.Start)),
                    leftPrimary: Boolean(Controller.getValue(Controller.Standard.LeftPrimaryThumb)),
                    leftSecondary: Boolean(Controller.getValue(Controller.Standard.LeftSecondaryThumb)),
                    leftThumbstick: Boolean(Controller.getValue(Controller.Standard.LS)),
                    leftTrigger: Boolean(Controller.getValue(Controller.Standard.LTClick)),
                    rightPrimary: Boolean(Controller.getValue(Controller.Standard.RightPrimaryThumb)),
                    rightSecondary: Boolean(Controller.getValue(Controller.Standard.RightSecondaryThumb)),
                    rightThumbstick: Boolean(Controller.getValue(Controller.Standard.RS)),
                    rightTrigger: Boolean(Controller.getValue(Controller.Standard.RTClick))
                },
                poses: {
                    left: controllerPose(Controller.Standard.LeftHand),
                    right: controllerPose(Controller.Standard.RightHand)
                }
            }
        }, "overte-probe.json");
    }

    function safeErrorText(error) {
        return String(error && error.message ? error.message : error)
            .replace(/[\r\n]+/g, " ").slice(0, 160);
    }

    function updateProbe() {
        var now = Date.now();
        if (lastSampleEpochMs !== 0 && now - lastSampleEpochMs < sampleIntervalMs) {
            return;
        }
        lastSampleEpochMs = now;
        try {
            sample(now);
            lastProbeError = "";
        } catch (error) {
            probeErrorCount += 1;
            var detail = safeErrorText(error);
            if (detail !== lastProbeError) {
                print("OVERTE_E2E_PROBE_ERROR " + detail);
                lastProbeError = detail;
            }
        }
        if (lastHeartbeatEpochMs === 0
                || now - lastHeartbeatEpochMs >= heartbeatIntervalMs) {
            print("OVERTE_E2E_PROBE_HEARTBEAT sequence=" + sampleSequence
                + " errors=" + probeErrorCount);
            lastHeartbeatEpochMs = now;
        }
    }

    Script.update.connect(updateProbe);
    Script.scriptEnding.connect(function () {
        Script.update.disconnect(updateProbe);
    });
    updateProbe();
}());
