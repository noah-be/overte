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
    var previousLocationKey = "";
    var assetResource = null;
    var assetResourceUrl = "";
    var sampleSequence = 0;
    var soundCommandRequestPending = false;
    var lastSoundControlCommandId = "";
    var soundResource = null;
    var soundInjector = null;
    var soundStopRequested = false;
    var soundState = {
        commandId: "",
        url: "",
        commandObserved: false,
        resourceReady: false,
        durationSeconds: 0.0,
        format: "unknown",
        injectorCreated: false,
        started: false,
        playing: false,
        finished: false,
        finishReason: "none"
    };
    var fixtureMarkers = ["OVERTE_E2E_FLOOR", "OVERTE_E2E_NORTH", "OVERTE_E2E_EAST", "OVERTE_E2E_ORIGIN"];
    var domainMarkers = ["OVERTE_E2E_DOMAIN_FLOOR", "OVERTE_E2E_DOMAIN_NORTH",
        "OVERTE_E2E_DOMAIN_EAST", "OVERTE_E2E_DOMAIN_ORIGIN"];
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

    function releaseAssetResource() {
        if (assetResource !== null) {
            assetResource.release();
            assetResource = null;
        }
        assetResourceUrl = "";
    }

    function resourceStateName(state) {
        if (state === Resource.State.QUEUED) {
            return "queued";
        }
        if (state === Resource.State.LOADING) {
            return "loading";
        }
        if (state === Resource.State.LOADED) {
            return "loaded";
        }
        if (state === Resource.State.FINISHED) {
            return "finished";
        }
        return "failed";
    }

    function observeAsset(ids) {
        var candidates = [];
        var index;
        for (index = 0; index < ids.length; index += 1) {
            var identity = Entities.getEntityProperties(ids[index], ["name"]);
            if (String(identity.name).indexOf("OVERTE_E2E_ASSET_LOAD") === 0) {
                candidates.push(ids[index]);
            }
        }
        if (candidates.length !== 1) {
            releaseAssetResource();
            return null;
        }
        var id = candidates[0];
        var properties = Entities.getEntityProperties(id, [
            "name", "type", "imageURL", "userData", "naturalDimensions"
        ]);
        var metadata;
        try {
            metadata = JSON.parse(String(properties.userData));
        } catch (error) {
            releaseAssetResource();
            return null;
        }
        var assetId = metadata && metadata.overteE2EAssetId;
        var imageURL = String(properties.imageURL);
        if (typeof assetId !== "string" || assetId.length === 0 || imageURL.length === 0) {
            releaseAssetResource();
            return null;
        }
        if (assetResource === null || assetResourceUrl !== imageURL) {
            releaseAssetResource();
            assetResourceUrl = imageURL;
            assetResource = TextureCache.prefetch(imageURL);
        }
        return {
            assetId: assetId,
            resource: {
                url: String(assetResource.url),
                state: resourceStateName(assetResource.state)
            },
            entity: {
                id: String(id),
                name: String(properties.name),
                type: String(properties.type),
                imageURL: imageURL,
                naturalDimensions: vector(properties.naturalDimensions)
            }
        };
    }

    function soundFormat(url) {
        return String(url).split("?", 1)[0].toLowerCase().slice(-4) === ".wav"
            ? "wav" : "unknown";
    }

    function startSound(command) {
        if (soundInjector && soundInjector.playing) {
            soundInjector.stop();
        }
        soundResource = null;
        soundInjector = null;
        soundStopRequested = false;
        soundState = {
            commandId: String(command.commandId),
            url: String(command.soundUrl),
            commandObserved: true,
            resourceReady: false,
            durationSeconds: 0.0,
            format: soundFormat(command.soundUrl),
            injectorCreated: false,
            started: false,
            playing: false,
            finished: false,
            finishReason: "none"
        };
        soundResource = SoundCache.getSound(soundState.url);

        function playReadySound() {
            if (!soundResource || soundState.commandId !== String(command.commandId)) {
                return;
            }
            soundState.resourceReady = Boolean(soundResource.downloaded);
            soundState.durationSeconds = Number(soundResource.duration);
            if (!soundState.resourceReady || soundState.durationSeconds <= 0.0) {
                return;
            }
            soundInjector = Audio.playSound(soundResource, {
                localOnly: true,
                volume: 0.1
            });
            soundState.injectorCreated = Boolean(soundInjector);
            if (soundInjector) {
                soundInjector.finished.connect(function () {
                    soundState.playing = false;
                    soundState.finished = true;
                    soundState.finishReason = soundStopRequested ? "stopped" : "natural";
                });
            }
        }

        if (soundResource.downloaded) {
            playReadySound();
        } else {
            soundResource.ready.connect(playReadySound);
        }
    }

    function applySoundCommand(command) {
        if (!command || command.schemaVersion !== 1 || !command.commandId
                || command.commandId === lastSoundControlCommandId) {
            return;
        }
        lastSoundControlCommandId = String(command.commandId);
        if (command.action === "play" && command.soundUrl) {
            startSound(command);
        } else if (command.action === "stop" && soundInjector) {
            soundStopRequested = true;
            soundInjector.stop();
        }
    }

    function safeErrorText(error) {
        return String(error && error.message ? error.message : error)
            .replace(/[\r\n]+/g, " ").slice(0, 160);
    }

    function pollSoundCommand() {
        if (soundCommandRequestPending) {
            return;
        }
        soundCommandRequestPending = true;
        var request = new XMLHttpRequest();
        request.onreadystatechange = function () {
            if (request.readyState !== request.DONE) {
                return;
            }
            soundCommandRequestPending = false;
            if (request.status === 200) {
                try {
                    applySoundCommand(JSON.parse(request.responseText));
                } catch (error) {
                    print("OVERTE_E2E_SOUND_COMMAND_ERROR " + safeErrorText(error));
                }
            }
        };
        request.open("GET", Script.resolvePath("sound-command.json"));
        request.send();
    }

    function sample() {
        pollSoundCommand();
        var currentAddress = String(location.href);
        var currentLocationKey = [String(location.protocol), String(location.hostname),
            String(location.domainID)].join("|");
        if (previousLocationKey !== "" && currentLocationKey !== previousLocationKey) {
            stableEntitySamples = 0;
            previousEntityCount = -1;
            stableAvatarSamples = 0;
            previousAvatarPosition = null;
            sceneReady = false;
        }
        previousLocationKey = currentLocationKey;
        var ids = Entities.findEntities(MyAvatar.position, 1000.0);
        var foundMarkers = {};
        var foundDomainMarkers = {};
        var floorTopY = null;
        var index;
        for (index = 0; index < ids.length; index += 1) {
            var properties = Entities.getEntityProperties(ids[index], ["name", "position", "dimensions"]);
            if (fixtureMarkers.indexOf(properties.name) !== -1) {
                foundMarkers[properties.name] = true;
            }
            if (domainMarkers.indexOf(properties.name) !== -1) {
                foundDomainMarkers[properties.name] = true;
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
        var domainMarkerCount = Object.keys(foundDomainMarkers).length;
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
        if (soundInjector && !soundState.finished) {
            soundState.playing = Boolean(soundInjector.playing);
            if (soundState.playing) {
                soundState.started = true;
            }
        }
        sampleSequence += 1;
        Test.saveObject({
            schemaVersion: 1,
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
            domain: {
                connected: Boolean(location.isConnected),
                hostname: String(location.hostname),
                id: String(location.domainID),
                protocol: String(location.protocol),
                serverless: String(location.protocol) === "file"
            },
            input: effectiveInputState(),
            scene: {
                url: currentAddress,
                ready: sceneReady,
                entityCount: ids.length,
                fixtureMarkerCount: markerCount,
                domainMarkerCount: domainMarkerCount,
                domainMarkers: Object.keys(foundDomainMarkers).sort(),
                floorTopY: floorTopY,
                avatarAboveFloor: avatarAboveFloor,
                spawnLocationObserved: avatarAtSpawn,
                spawnValidated: sceneReady
            },
            avatar: {
                position: avatarPosition,
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
            },
            asset: observeAsset(ids),
            sound: {
                commandId: soundState.commandId,
                url: soundState.url,
                commandObserved: soundState.commandObserved,
                resourceReady: soundState.resourceReady,
                durationSeconds: soundState.durationSeconds,
                format: soundState.format,
                injectorCreated: soundState.injectorCreated,
                started: soundState.started,
                playing: soundState.playing,
                finished: soundState.finished,
                finishReason: soundState.finishReason
            }
        }, "overte-probe.json");
    }

    var timer = Script.setInterval(sample, 250);
    Script.scriptEnding.connect(function () {
        Script.clearInterval(timer);
        releaseAssetResource();
    });
    sample();
}());
