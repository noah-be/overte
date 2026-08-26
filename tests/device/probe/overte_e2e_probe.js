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
    var previousSceneUrl = "";
    var sampleSequence = 0;
    var fixtureMarkers = [
        "OVERTE_E2E_COLLISION_WALL",
        "OVERTE_E2E_EAST",
        "OVERTE_E2E_FLOOR",
        "OVERTE_E2E_NORTH",
        "OVERTE_E2E_ORIGIN"
    ];
    var expectedSpawn = { x: 0.0, y: 2.0, z: 4.0 };

    function vector(value) {
        return { x: Number(value.x), y: Number(value.y), z: Number(value.z) };
    }

    function effectiveInputState() {
        var application = Controller.Hardware.Application;
        var right = Number(Controller.getValue(application.RightHandDominant)) > 0.5;
        var left = Number(Controller.getValue(application.LeftHandDominant)) > 0.5;
        return {
            dominantHand: right && !left ? "right" : (left && !right ? "left" : "unknown"),
            advancedMovementControls:
                Number(Controller.getValue(application.AdvancedMovement)) > 0.5
        };
    }

    function sample() {
        var sceneUrl = String(AddressManager.href);
        if (sceneUrl !== previousSceneUrl) {
            previousSceneUrl = sceneUrl;
            stableEntitySamples = 0;
            previousEntityCount = -1;
            stableAvatarSamples = 0;
            previousAvatarPosition = null;
            sceneReady = false;
        }
        var ids = Entities.findEntities(MyAvatar.position, 1000.0);
        var foundMarkers = {};
        var floorTopY = null;
        var collisionWall = null;
        var index;
        for (index = 0; index < ids.length; index += 1) {
            var properties = Entities.getEntityProperties(ids[index], ["name", "position", "dimensions"]);
            if (fixtureMarkers.indexOf(properties.name) !== -1) {
                foundMarkers[properties.name] = true;
            }
            if (properties.name === "OVERTE_E2E_FLOOR") {
                floorTopY = Number(properties.position.y) + Number(properties.dimensions.y) / 2.0;
            }
            if (properties.name === "OVERTE_E2E_COLLISION_WALL") {
                collisionWall = {
                    name: properties.name,
                    center: vector(properties.position),
                    dimensions: vector(properties.dimensions)
                };
            }
        }
        if (ids.length === previousEntityCount) {
            stableEntitySamples += 1;
        } else {
            stableEntitySamples = 0;
            previousEntityCount = ids.length;
        }
        var foundMarkerNames = fixtureMarkers.filter(function (name) {
            return foundMarkers[name] === true;
        });
        var markerCount = foundMarkerNames.length;
        var avatarPosition = vector(MyAvatar.position);
        var spawnDeltaX = avatarPosition.x - expectedSpawn.x;
        var spawnDeltaZ = avatarPosition.z - expectedSpawn.z;
        var avatarAtSpawn = spawnDeltaX * spawnDeltaX + spawnDeltaZ * spawnDeltaZ <= 1.0;
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
        if (!sceneReady && markerCount === fixtureMarkers.length && stableEntitySamples >= 3
                && stableAvatarSamples >= 4 && avatarAboveFloor && avatarAtSpawn) {
            sceneReady = true;
        }
        var orientation = Quat.safeEulerAngles(Camera.orientation);
        sampleSequence += 1;
        Test.saveObject({
            schemaVersion: 2,
            sampleEpochMs: Date.now(),
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
                url: sceneUrl,
                ready: sceneReady,
                entityCount: ids.length,
                fixtureMarkerCount: markerCount,
                fixtureMarkers: foundMarkerNames,
                floorTopY: floorTopY,
                avatarAboveFloor: avatarAboveFloor,
                spawnLocationObserved: avatarAtSpawn,
                spawnValidated: sceneReady,
                collisionWall: collisionWall
            },
            avatar: {
                position: avatarPosition,
                velocity: vector(MyAvatar.velocity),
                bodyYawDegrees: Number(MyAvatar.bodyYaw),
                inAir: Boolean(MyAvatar.isInAir()),
                flying: Boolean(MyAvatar.isFlying()),
                flyingEnabled: Boolean(MyAvatar.getFlyingEnabled())
            },
            view: {
                orientation: vector(orientation)
            },
            tablet: {
                open: Boolean(tablet.tabletShown),
                home: Boolean(tablet.onHomeScreen()),
                toolbarMode: Boolean(tablet.toolbarMode)
            }
        }, "overte-probe.json");
    }

    var timer = Script.setInterval(sample, 250);
    Script.scriptEnding.connect(function () {
        Script.clearInterval(timer);
    });
    sample();
}());
