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
    var flightNormalizationAllowed = true;
    var flightNormalizationActive = false;
    var flightNormalizationStableSamples = 0;
    var flyingEnabledBeforeNormalization = false;
    var assetResource = null;
    var assetResourceUrl = "";
    var controlledAssetEntity = null;
    var controlledKey = null;
    var controlledKeyCommandId = "";
    var controlledInputMappingName = "org.overte.e2e.probe.controlled-input";
    var controlledInputMapping = Controller.newMapping(controlledInputMappingName);
    // Resolve while the script file is the active execution context. Timer
    // callbacks do not retain that source context on every script engine.
    var clientCommandFallbackUrl = String(Script.resolvePath("e2e-client-command.json"));
    var clientCommandRequestPending = false;
    var clientCommandUnavailable = false;
    var lastClientCommandId = "";
    var lastSceneCommandId = "";
    var sampleSequence = 0;
    var orientationHistory = [];
    var verticalObservationPrevious = null;
    var verticalJumpActive = false;
    var verticalEvents = {
        jumpCount: 0,
        jumpCompletedCount: 0,
        lastJumpStartY: null,
        lastJumpPeakY: null,
        lastJumpLandingY: null,
        flightCount: 0,
        lastFlightStartY: null,
        lastFlightPeakY: null
    };
    var soundCommandRequestPending = false;
    // Network-loaded probes retain the fixture-relative fallback. A target
    // adapter's private probe copy can replace it through the narrow command
    // channel only after the fixture has accepted an exact sound command.
    var soundCommandUrl = Script.resolvePath("sound-command.json");
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
    var fixtureMarkers = ["OVERTE_E2E_COLLISION_WALL", "OVERTE_E2E_EAST",
        "OVERTE_E2E_FLOOR", "OVERTE_E2E_NORTH", "OVERTE_E2E_ORIGIN"];
    var domainMarkers = ["OVERTE_E2E_DOMAIN_FLOOR", "OVERTE_E2E_DOMAIN_NORTH",
        "OVERTE_E2E_DOMAIN_EAST", "OVERTE_E2E_DOMAIN_ORIGIN"];
    var expectedSpawn = { x: 0.0, y: 2.0, z: 4.0 };

    function controlledTabletOpen() {
        return Boolean(tablet.tabletShown || HMD.showTablet);
    }

    function addControlledInputRoute(name, action) {
        controlledInputMapping.from(function () {
            // A physical desktop key is consumed by the focused tablet before
            // it can reach world locomotion. Preserve that routing boundary
            // for semantic in-client input while leaving ContextMenu active.
            return controlledKey === name
                && (name === "tablet" || !controlledTabletOpen()) ? 1.0 : 0.0;
        }).to(action);
    }

    addControlledInputRoute("backward", Controller.Actions.Backward);
    addControlledInputRoute("down", Controller.Actions.Down);
    addControlledInputRoute("forward", Controller.Actions.Forward);
    addControlledInputRoute("jump", Controller.Actions.Up);
    addControlledInputRoute("left", Controller.Actions.StrafeLeft);
    addControlledInputRoute("right", Controller.Actions.StrafeRight);
    addControlledInputRoute("tablet", Controller.Actions.ContextMenu);
    Controller.enableMapping(controlledInputMappingName);

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
            dominantHand: right && !left ? "right" : (left && !right ? "left" : "unknown"),
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

    function objectKeysMatch(value, expected) {
        if (!value || typeof value !== "object") {
            return false;
        }
        return Object.keys(value).sort().join("|") === expected.slice().sort().join("|");
    }

    function httpUrl(value) {
        return typeof value === "string"
            && /^https?:\/\/(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(?::[0-9]+)?(?:[/?#]|$)/.test(value);
    }

    function clientCommandEndpoint() {
        if (httpUrl(clientCommandFallbackUrl)) {
            return clientCommandFallbackUrl;
        }
        var currentAddress = String(location.href);
        var origin = /^(https?:\/\/(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(?::[0-9]+)?)(?:[/?#]|$)/
            .exec(currentAddress);
        return origin ? origin[1] + "/e2e-client-command.json" : "";
    }

    function controlledSceneLocation(value) {
        var queryStart = value.indexOf("?");
        if (queryStart === -1) {
            return "";
        }
        var fragmentStart = value.indexOf("#", queryStart);
        var query = value.slice(queryStart + 1,
            fragmentStart === -1 ? value.length : fragmentStart);
        var parts = query.split("&");
        var index;
        for (index = 0; index < parts.length; index += 1) {
            var separator = parts[index].indexOf("=");
            if (separator === -1) {
                continue;
            }
            var name;
            var path;
            try {
                name = decodeURIComponent(parts[index].slice(0, separator).replace(/\+/g, "%20"));
                path = decodeURIComponent(parts[index].slice(separator + 1).replace(/\+/g, "%20"));
            } catch (error) {
                return "";
            }
            if (name !== "location") {
                continue;
            }
            var sections = path.split("/");
            if (sections.length !== 3 || sections[0] !== "") {
                return "";
            }
            var position = sections[1].split(",");
            var orientation = sections[2].split(",");
            if (position.length !== 3 || orientation.length !== 4) {
                return "";
            }
            var components = position.concat(orientation);
            var component;
            for (component = 0; component < components.length; component += 1) {
                if (!/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(components[component])
                        || !isFinite(Number(components[component]))
                        || Math.abs(Number(components[component])) > (component < 3 ? 100000 : 1.01)) {
                    return "";
                }
            }
            return path;
        }
        return "";
    }

    function resetSceneObservation() {
        stableEntitySamples = 0;
        previousEntityCount = -1;
        stableAvatarSamples = 0;
        previousAvatarPosition = null;
        sceneReady = false;
        // Reloading the same serverless URL does not change the domain key,
        // but Window.location can leave the avatar in the temporary flight
        // state used while applying its viewpoint. Re-arm the same bounded
        // normalization used at initial startup before declaring readiness.
        flightNormalizationAllowed = true;
        flightNormalizationStableSamples = 0;
        orientationHistory = [];
    }

    function avatarAtExpectedSpawn() {
        var position = MyAvatar.position;
        var deltaX = Number(position.x) - expectedSpawn.x;
        var deltaZ = Number(position.z) - expectedSpawn.z;
        return deltaX * deltaX + deltaZ * deltaZ <= 1.0;
    }

    function applySceneLocation(commandId, scenePath) {
        if (scenePath !== "" && lastClientCommandId === commandId && !sceneReady
                && !avatarAtExpectedSpawn()) {
            // The serverless scene may reset the avatar after the initial URL
            // lookup. Reapply its bounded viewpoint only if the first load did
            // not actually restore the expected horizontal spawn. Reapplying
            // an already-correct location would repeatedly lift and drop the
            // avatar while the physics state is still settling.
            // Each reapply can transiently enter flight again, so it must also
            // restart the readiness and flight-normalization observation.
            resetSceneObservation();
            Window.location = scenePath;
        }
    }

    function controlledKeySpec(name) {
        var keys = {
            backward: true,
            down: true,
            forward: true,
            jump: true,
            left: true,
            right: true,
            tablet: true
        };
        return Object.prototype.hasOwnProperty.call(keys, name) ? String(name) : null;
    }

    function releaseControlledKey(commandId) {
        if (controlledKey !== null && controlledKeyCommandId === commandId) {
            controlledKey = null;
            controlledKeyCommandId = "";
        }
    }

    function applyControlledKey(command) {
        var key = controlledKeySpec(command.key);
        var durationMs = Number(command.durationMs);
        if (key === null || typeof command.durationMs !== "number"
                || !isFinite(durationMs) || Math.floor(durationMs) !== durationMs
                || durationMs < 50 || durationMs > 10000) {
            return false;
        }
        releaseControlledKey(controlledKeyCommandId);
        controlledKey = key;
        controlledKeyCommandId = String(command.commandId);
        Script.setTimeout(function () {
            releaseControlledKey(String(command.commandId));
        }, durationMs);
        return true;
    }

    function applyClientCommand(command) {
        if (!command || command.schemaVersion !== 1 || !command.commandId
                || command.commandId === lastClientCommandId) {
            return;
        }
        if (command.action === "key-hold"
                && objectKeysMatch(command, ["schemaVersion", "commandId", "action",
                    "key", "durationMs"])
                && applyControlledKey(command)) {
            lastClientCommandId = String(command.commandId);
            return;
        }
        if (command.action === "scene-load"
                && objectKeysMatch(command, ["schemaVersion", "commandId", "action", "url"])
                && httpUrl(command.url)) {
            var sceneCommandId = String(command.commandId);
            var scenePath = controlledSceneLocation(command.url);
            lastClientCommandId = sceneCommandId;
            lastSceneCommandId = sceneCommandId;
            resetSceneObservation();
            Window.location = command.url;
            Script.setTimeout(function () {
                applySceneLocation(sceneCommandId, scenePath);
            }, 1500);
            Script.setTimeout(function () {
                applySceneLocation(sceneCommandId, scenePath);
            }, 3500);
            return;
        }
        if (command.action === "navigate"
                && objectKeysMatch(command, ["schemaVersion", "commandId", "action", "url"])
                && typeof command.url === "string"
                && /^hifi:\/\/(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\]):[0-9]+(?:\/|$)/.test(command.url)) {
            lastClientCommandId = String(command.commandId);
            Window.location = command.url;
            return;
        }
        if (command.action === "asset-load"
                && objectKeysMatch(command, ["schemaVersion", "commandId", "action",
                    "assetId", "url", "entityName"])
                && typeof command.assetId === "string" && command.assetId.length > 0
                && typeof command.entityName === "string"
                && command.entityName.indexOf("OVERTE_E2E_ASSET_LOAD") === 0
                && httpUrl(command.url)) {
            if (controlledAssetEntity !== null) {
                Entities.deleteEntity(controlledAssetEntity);
                controlledAssetEntity = null;
            }
            controlledAssetEntity = Entities.addEntity({
                type: "Image",
                name: command.entityName,
                imageURL: command.url,
                userData: JSON.stringify({ overteE2EAssetId: command.assetId }),
                position: Vec3.sum(MyAvatar.position, Vec3.multiply(
                    2.0, Quat.getForward(Camera.orientation))),
                dimensions: { x: 1.0, y: 1.0, z: 0.01 }
            }, "local");
            lastClientCommandId = String(command.commandId);
            return;
        }
        if (command.action === "sound-channel"
                && objectKeysMatch(command, ["schemaVersion", "commandId", "action", "url"])
                && httpUrl(command.url)) {
            soundCommandUrl = String(command.url);
            lastClientCommandId = String(command.commandId);
        }
    }

    function pollClientCommand() {
        if (clientCommandUnavailable || clientCommandRequestPending) {
            return;
        }
        var commandUrl = clientCommandEndpoint();
        if (commandUrl === "") {
            return;
        }
        clientCommandRequestPending = true;
        var request = new XMLHttpRequest();
        request.onreadystatechange = function () {
            if (request.readyState !== request.DONE) {
                return;
            }
            clientCommandRequestPending = false;
            if ((request.status === 0 || request.status === 200)
                    && request.responseText) {
                try {
                    applyClientCommand(JSON.parse(request.responseText));
                } catch (error) {
                    print("OVERTE_E2E_CLIENT_COMMAND_ERROR " + safeErrorText(error));
                }
            } else if (request.status >= 400
                    || (request.status === 0 && !request.responseText)) {
                // A network-loaded shared probe has no private command file.
                // Stop polling a permanent miss for the rest of the session.
                clientCommandUnavailable = true;
            }
        };
        request.open("GET", commandUrl);
        request.send();
    }

    function pollSoundCommand() {
        if (!soundCommandUrl || soundCommandRequestPending) {
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
        request.open("GET", soundCommandUrl);
        request.send();
    }

    function normalizeInitialFlightState() {
        if (flightNormalizationAllowed && !flightNormalizationActive
                && MyAvatar.isFlying()) {
            flyingEnabledBeforeNormalization = Boolean(MyAvatar.getFlyingEnabled());
            flightNormalizationActive = true;
            flightNormalizationStableSamples = 0;
            MyAvatar.setFlyingEnabled(false);
            print("OVERTE_E2E_FLIGHT_NORMALIZATION stage=started");
        }
        if (!flightNormalizationActive) {
            return;
        }
        if (!MyAvatar.isInAir() && !MyAvatar.isFlying()) {
            flightNormalizationStableSamples += 1;
        } else {
            flightNormalizationStableSamples = 0;
        }
        if (flightNormalizationStableSamples >= 2) {
            MyAvatar.setFlyingEnabled(flyingEnabledBeforeNormalization);
            flightNormalizationActive = false;
            flightNormalizationAllowed = false;
            print("OVERTE_E2E_FLIGHT_NORMALIZATION stage=completed");
        }
    }

    function observeVerticalMotion() {
        var observation = {
            y: Number(MyAvatar.position.y),
            inAir: Boolean(MyAvatar.isInAir()),
            flying: Boolean(MyAvatar.isFlying())
        };
        if (!sceneReady || flightNormalizationAllowed || flightNormalizationActive) {
            verticalObservationPrevious = observation;
            verticalJumpActive = false;
            return;
        }
        if (verticalObservationPrevious === null) {
            verticalObservationPrevious = observation;
            return;
        }

        if (observation.flying && !verticalObservationPrevious.flying) {
            verticalEvents.flightCount += 1;
            verticalEvents.lastFlightStartY = verticalObservationPrevious.y;
            verticalEvents.lastFlightPeakY = Math.max(
                verticalObservationPrevious.y, observation.y);
        } else if (observation.flying && verticalEvents.lastFlightPeakY !== null) {
            verticalEvents.lastFlightPeakY = Math.max(
                verticalEvents.lastFlightPeakY, observation.y);
        }

        if (observation.inAir && !observation.flying
                && (!verticalObservationPrevious.inAir
                    || verticalObservationPrevious.flying)) {
            verticalEvents.jumpCount += 1;
            verticalEvents.lastJumpStartY = verticalObservationPrevious.y;
            verticalEvents.lastJumpPeakY = Math.max(
                verticalObservationPrevious.y, observation.y);
            verticalEvents.lastJumpLandingY = null;
            verticalJumpActive = true;
        }
        if (verticalJumpActive && observation.inAir && !observation.flying) {
            verticalEvents.lastJumpPeakY = Math.max(
                verticalEvents.lastJumpPeakY, observation.y);
        } else if (verticalJumpActive && !observation.inAir) {
            verticalEvents.jumpCompletedCount = verticalEvents.jumpCount;
            verticalEvents.lastJumpLandingY = observation.y;
            verticalJumpActive = false;
        } else if (verticalJumpActive && observation.flying) {
            verticalJumpActive = false;
        }
        verticalObservationPrevious = observation;
    }

    function sample() {
        pollClientCommand();
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
            flightNormalizationAllowed = true;
            flightNormalizationStableSamples = 0;
        }
        previousLocationKey = currentLocationKey;
        normalizeInitialFlightState();
        var ids = Entities.findEntities(MyAvatar.position, 1000.0);
        var foundMarkers = {};
        var foundDomainMarkers = {};
        var floorTopY = null;
        var collisionWall = null;
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
            if (properties.name === "OVERTE_E2E_COLLISION_WALL") {
                collisionWall = {
                    name: String(properties.name),
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
        var markerCount = Object.keys(foundMarkers).length;
        var foundFixtureMarkers = Object.keys(foundMarkers).sort();
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
                && stableAvatarSamples >= 4 && avatarAboveFloor && avatarAtSpawn
                && !flightNormalizationActive && !MyAvatar.isInAir()
                && !MyAvatar.isFlying()) {
            sceneReady = true;
            flightNormalizationAllowed = false;
        }
        var orientation = Quat.safeEulerAngles(Camera.orientation);
        if (soundInjector && !soundState.finished) {
            soundState.playing = Boolean(soundInjector.playing);
            if (soundState.playing) {
                soundState.started = true;
            }
        }
        sampleSequence += 1;
        orientationHistory.push({
            sampleSequence: sampleSequence,
            orientation: vector(orientation)
        });
        if (orientationHistory.length > 48) {
            orientationHistory.shift();
        }
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
            domain: {
                // A file-backed serverless scene can report location.isConnected
                // even though no domain server or domain UUID exists.
                connected: Boolean(location.isConnected)
                    && String(location.protocol) !== "file",
                hostname: String(location.hostname),
                id: String(location.domainID),
                protocol: String(location.protocol),
                serverless: String(location.protocol) === "file"
            },
            input: effectiveInputState(),
            scene: {
                url: currentAddress,
                commandId: lastSceneCommandId,
                ready: sceneReady,
                entityCount: ids.length,
                fixtureMarkerCount: markerCount,
                fixtureMarkers: foundFixtureMarkers,
                domainMarkerCount: domainMarkerCount,
                domainMarkers: Object.keys(foundDomainMarkers).sort(),
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
            verticalEvents: verticalEvents,
            view: {
                orientation: vector(orientation),
                orientationHistory: orientationHistory
            },
            tablet: {
                // tabletShown is explicitly unused in desktop toolbar mode.
                // HMD.showTablet is the application-level ContextMenu state
                // shared by toolbar and world-tablet presentations.
                open: controlledTabletOpen(),
                home: Boolean(tablet.onHomeScreen()),
                toolbarMode: Boolean(tablet.toolbarMode)
            },
            controller: {
                route: {
                    openxrAxes: openXrAxes(),
                    standardLy: Number(Controller.getValue(Controller.Standard.LY)),
                    translateYAction: Number(Controller.getValue(Controller.Actions.TranslateY)),
                    rawTranslateYDriveKey: Number(MyAvatar.getRawDriveKey(DriveKeys.TRANSLATE_Y)),
                    translateYDriveKeyDisabled: Boolean(MyAvatar.isDriveKeyDisabled(DriveKeys.TRANSLATE_Y)),
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

    var verticalTimer = Script.setInterval(observeVerticalMotion, 50);
    var timer = Script.setInterval(sample, 250);
    Script.scriptEnding.connect(function () {
        Script.clearInterval(verticalTimer);
        Script.clearInterval(timer);
        releaseControlledKey(controlledKeyCommandId);
        Controller.disableMapping(controlledInputMappingName);
        if (flightNormalizationActive) {
            MyAvatar.setFlyingEnabled(flyingEnabledBeforeNormalization);
            flightNormalizationActive = false;
        }
        releaseAssetResource();
        if (controlledAssetEntity !== null) {
            Entities.deleteEntity(controlledAssetEntity);
            controlledAssetEntity = null;
        }
    });
    sample();
}());
