// In-client observation probe for physical-device E2E tests. This script is
// loaded only through Interface's --testScript command-line option and writes
// snapshots into --testResultsLocation through the existing Test API.
(function () {
    "use strict";

    function reloadCommandIdFromAddress(address) {
        var match = String(address).match(
            /[?&]overteE2EReloadCommandId=([^&#]*)/);
        if (!match) {
            return "";
        }
        try {
            return decodeURIComponent(match[1]);
        } catch (error) {
            return "";
        }
    }

    function addressWithoutReloadCommand(address) {
        var withoutFragment = String(address).split("#", 1)[0];
        var queryStart = withoutFragment.indexOf("?");
        if (queryStart === -1) {
            return withoutFragment;
        }
        var path = withoutFragment.slice(0, queryStart);
        var components = withoutFragment.slice(queryStart + 1).split("&");
        var retained = [];
        var index;
        for (index = 0; index < components.length; index += 1) {
            if (components[index]
                    && components[index].indexOf("overteE2EReloadCommandId=") !== 0) {
                retained.push(components[index]);
            }
        }
        return path + (retained.length ? "?" + retained.join("&") : "");
    }

    var tablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
    var stableEntitySamples = 0;
    var previousEntityCount = -1;
    var stableAvatarSamples = 0;
    var previousAvatarPosition = null;
    var sceneReady = false;
    var probeErrorCount = 0;
    var lastProbeError = "";
    var lastSampleEpochMs = 0;
    var lastCompletedSampleEpochMs = 0;
    var lastHeartbeatEpochMs = 0;
    var sampleIntervalMs = 250;
    var heartbeatIntervalMs = 5000;
    var previousLocationKey = "";
    // About.platform names the product. The fixed debug launcher owns this
    // local, versioned marker; resolve paths while the script context is live.
    var androidControlMarkerUrl = String(Script.resolvePath("android-control.json"));
    var androidControlCommandUrl = String(Script.resolvePath("android-control-command.json"));
    var androidFixtureUrl = String(Script.resolvePath("scene.json"))
        + "?location=/0,0,4/0,0,0,1";
    var androidControlEligible = /^file:/.test(androidControlMarkerUrl);
    var androidControlAvailable = false;
    var androidControlProcessId = null;
    var nativeMotionUrl = String(Script.resolvePath("avatar-motion-observation.json"));
    var nativeMotionLastRequestEpochMs = 0;
    var nativeMotionLastSequence = 0;
    var nativeMotionUpdatedEpochMs = 0;
    var nativeMotionAvailable = false;
    var lastAndroidControlCommandId = reloadCommandIdFromAddress(location.href);
    var androidAssetEntityId = null;
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
    var clientCommandRequest = null;
    var clientCommandUnavailable = false;
    var lastClientCommandId = "";
    // Serverless navigation can restart the probe. Recover the identity from
    // the actual loaded address, rather than losing the reload confirmation.
    var lastSceneCommandId = reloadCommandIdFromAddress(location.href);
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
    var soundCommandRequest = null;
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
    var interactionTargetName = "OVERTE_E2E_INTERACTABLE";
    var interactionPressCount = 0;
    var interactionLastEntityName = "";
    var interactionLastPointerId = null;
    // Read-only diagnostics of the real dispatcher rays. These observations
    // never create a pointer, deliver an event, or count as a test assertion.
    var interactionPointers = null;
    var interactionPointerHistory = [];
    var interactionPointerSequence = 0;
    var interactionPointerLastSampleMs = 0;
    var interactionPointerChannel = "Pico4-FarGrab-Depth";
    function observeDispatcherPointers(channel, message, sender, localOnly) {
        if (channel !== interactionPointerChannel || !localOnly) { return; }
        try {
            var config = JSON.parse(message);
            if (config.action === "configurePointers"
                    && typeof config.left === "number" && typeof config.right === "number") {
                interactionPointers = [config.left, config.right];
            }
        } catch (error) { /* Ignore unrelated worker messages. */ }
    }
    Messages.subscribe(interactionPointerChannel);
    Messages.messageReceived.connect(observeDispatcherPointers);
    var interactionPointerDiscovery = Script.setInterval(function () {
        if (interactionPointers === null) {
            Messages.sendLocalMessage(interactionPointerChannel, JSON.stringify({ action: "ready" }));
        }
    }, 1000);
    function observeDispatcherRay(now) {
        if (interactionPointers === null || now - interactionPointerLastSampleMs < 100) { return; }
        var trigger = Controller.getValue(Controller.Standard.RT);
        if (trigger <= 0.01) { return; }
        interactionPointerLastSampleMs = now;
        try {
            interactionPointerSequence += 1;
            var pick = Pointers.getPrevPickResult(interactionPointers[1]);
            interactionPointerHistory.push({
                sampleSequence: interactionPointerSequence, sampleEpochMs: now,
                trigger: trigger, triggerClick: Controller.getValue(Controller.Standard.RTClick),
                pose: controllerPose(Controller.Standard.RightHand),
                pick: pick, avatarPosition: MyAvatar.position,
                sensorToWorld: MyAvatar.getSensorToWorldMatrix(),
                pressCount: interactionPressCount
            });
            if (interactionPointerHistory.length > 64) { interactionPointerHistory.shift(); }
            Test.saveObject({ schemaVersion: 1, source: "actual-dispatcher-ray",
                processId: androidControlProcessId, updatedEpochMs: now,
                samples: interactionPointerHistory }, "interaction-ray-observation.json");
        } catch (error) { /* Diagnostic availability does not change test results. */ }
    }
    var peerTrackingId = "";
    var peerPreviousPosition = null;
    var peerObservationCount = 0;
    var peerMovementDistance = 0.0;
    var renderFrameCount = 0;
    var renderLastFrameEpochMs = 0;
    var renderStats = Render.getConfig("Stats");
    var domainMarkers = ["OVERTE_E2E_DOMAIN_FLOOR", "OVERTE_E2E_DOMAIN_NORTH",
        "OVERTE_E2E_DOMAIN_EAST", "OVERTE_E2E_DOMAIN_ORIGIN"];
    var expectedSpawn = { x: 0.0, y: 0.0, z: 4.0 };

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

    function pendingVector(value) {
        if (!value || !isFinite(Number(value.x)) || !isFinite(Number(value.y))
                || !isFinite(Number(value.z))) {
            return { x: 0.0, y: 0.0, z: 0.0 };
        }
        return vector(value);
    }

    function observeRenderedFrame() {
        renderFrameCount += 1;
        renderLastFrameEpochMs = Date.now();
    }

    if (renderStats && renderStats.newStats) {
        renderStats.newStats.connect(observeRenderedFrame);
    }

    function controlledSharedObservation(properties) {
        if (properties.name !== "OVERTE_E2E_SHARED_COLOR") { return null; }
        var state;
        try { state = JSON.parse(String(properties.userData)); } catch (error) { return null; }
        var author = String(properties.lastEditedBy).replace(/[{}]/g, "").toLowerCase();
        if (!state || state.contract !== "overte-e2e-collaboration-v1"
                || state.actorId !== "OVERTE_E2E_ACTOR_FIXTURE"
                || typeof state.revision !== "number" || !isFinite(state.revision)
                || state.revision < 0 || state.revision > 9007199254740991 || state.revision % 1 !== 0
                || (state.value !== "blue" && state.value !== "orange")
                || !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(author)
                || author === "00000000-0000-0000-0000-000000000000") { return null; }
        var color = state.value === "blue"
            ? { red: 40, green: 120, blue: 255 } : { red: 255, green: 150, blue: 40 };
        if (!properties.color || properties.color.red !== color.red
                || properties.color.green !== color.green || properties.color.blue !== color.blue) { return null; }
        return { schemaVersion: 1, entityName: String(properties.name), actorId: state.actorId,
            revision: state.revision, value: state.value, actorSessionId: author };
    }

    function controlledPeer() {
        var identifiers = AvatarList.getAvatarIdentifiers();
        var candidates = [];
        var index;
        for (index = 0; index < identifiers.length; index += 1) {
            if (String(identifiers[index]) === String(MyAvatar.sessionUUID)) {
                continue;
            }
            var avatar = AvatarList.getAvatar(identifiers[index]);
            if (avatar && String(avatar.displayName) === "OVERTE_E2E_PEER") {
                candidates.push(avatar);
            }
        }
        if (candidates.length !== 1) {
            return {
                present: false, sessionId: "", displayName: "", position: null,
                observationCount: peerObservationCount,
                movementDistanceMeters: peerMovementDistance
            };
        }
        var peer = candidates[0];
        var sessionId = String(peer.sessionUUID);
        var position = vector(peer.position);
        if (peerTrackingId !== sessionId) {
            peerTrackingId = sessionId;
            peerPreviousPosition = null;
            peerObservationCount = 0;
            peerMovementDistance = 0.0;
        }
        if (peerPreviousPosition !== null) {
            var dx = position.x - peerPreviousPosition.x;
            var dy = position.y - peerPreviousPosition.y;
            var dz = position.z - peerPreviousPosition.z;
            peerMovementDistance += Math.sqrt(dx * dx + dy * dy + dz * dz);
        }
        peerPreviousPosition = position;
        peerObservationCount += 1;
        return {
            present: true,
            sessionId: sessionId,
            displayName: "OVERTE_E2E_PEER",
            position: position,
            observationCount: peerObservationCount,
            movementDistanceMeters: peerMovementDistance
        };
    }

    function observePrimaryInteraction(entityID, event) {
        var properties = Entities.getEntityProperties(entityID, ["name"]);
        if (String(properties.name) !== interactionTargetName) {
            return;
        }
        interactionPressCount += 1;
        interactionLastEntityName = interactionTargetName;
        interactionLastPointerId = event && isFinite(Number(event.id))
            ? Math.max(0, Math.floor(Number(event.id))) : null;
    }

    Entities.mousePressOnEntity.connect(observePrimaryInteraction);

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

    function openXrAxes(openXr) {
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

    function appendAssetCandidate(candidates, id) {
        if (id === null || id === undefined) {
            return;
        }
        var index;
        for (index = 0; index < candidates.length; index += 1) {
            if (String(candidates[index]) === String(id)) {
                return;
            }
        }
        var identity = Entities.getEntityProperties(id, ["name"]);
        if (String(identity.name).indexOf("OVERTE_E2E_ASSET_LOAD") === 0) {
            candidates.push(id);
        }
    }

    function observeAsset(ids) {
        var candidates = [];
        appendAssetCandidate(candidates, androidAssetEntityId);
        appendAssetCandidate(candidates, controlledAssetEntity);
        var index;
        for (index = 0; index < ids.length; index += 1) {
            appendAssetCandidate(candidates, ids[index]);
        }
        if (candidates.length !== 1) {
            releaseAssetResource();
            return null;
        }
        var id = candidates[0];
        var properties = Entities.getEntityProperties(id, [
            "name", "type", "imageURL", "userData", "dimensions", "naturalDimensions"
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
        if (!properties.naturalDimensions) {
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
                naturalDimensions: pendingVector(properties.naturalDimensions)
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
                        || Math.abs(Number(components[component]))
                        > (component < 3 ? 100000 : 1.01)) {
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

    function reloadControlledScene(commandId) {
        var baseAddress = addressWithoutReloadCommand(androidControlAvailable
            ? androidFixtureUrl : location.href);
        var separator = baseAddress.indexOf("?") === -1 ? "?" : "&";
        resetSceneObservation();
        lastSceneCommandId = String(commandId);
        Window.location = baseAddress + separator + "overteE2EReloadCommandId="
            + encodeURIComponent(String(commandId));
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

    var voiceOriginal = null;
    var voiceWatchdog = null;
    var voiceLocalEcho = false;
    var voiceServerEcho = false;
    function restoreVoice() {
        if (typeof Test.voiceTest === "function") {
            Test.voiceTest({ schemaVersion: 1, commandId: "voice-watchdog-reset", action: "reset" });
            Test.saveObject({ schemaVersion: 1, commandId: "voice-watchdog-reset", ok: true }, "voice-result.json");
        }
        if (voiceOriginal) {
            Object.keys(voiceOriginal).forEach(function (key) { Audio[key] = voiceOriginal[key]; });
            voiceOriginal = null;
            Audio.setLocalEcho(voiceLocalEcho);
            Audio.setServerEcho(voiceServerEcho);
        }
        if (voiceWatchdog !== null) { Script.clearTimeout(voiceWatchdog); voiceWatchdog = null; }
    }
    function applyVoice(command) {
        if (!command || command.schemaVersion !== 1
                || !objectKeysMatch(command, ["schemaVersion", "commandId", "action", "request"])
                || command.action !== "voice-test" || !command.commandId
                || command.commandId === lastClientCommandId) { return false; }
        lastClientCommandId = String(command.commandId);
        var request = command.request;
        var result = { schemaVersion: 1, commandId: command.commandId, ok: false,
            error: "voice-test-not-enabled" };
        if (typeof Test.voiceTest === "function" && request && request.commandId === command.commandId) {
            if (request.action === "prepare") {
                if (voiceOriginal !== null) {
                    result.error = "voice-session-busy";
                    Test.saveObject(result, "voice-result.json");
                    return true;
                }
                result = Test.voiceTest(request);
                if (result.ok) {
                    voiceOriginal = {};
                    voiceLocalEcho = Boolean(Audio.getLocalEcho());
                    voiceServerEcho = Boolean(Audio.getServerEcho());
                    ["muted", "pushToTalk", "noiseReduction", "acousticEchoCancellation", "avatarGain",
                        "serverInjectorGain", "localInjectorGain", "systemInjectorGain"].forEach(function (key) {
                        voiceOriginal[key] = Audio[key];
                    });
                    Audio.muted = true;
                    Audio.pushToTalk = false;
                    Audio.noiseReduction = false;
                    Audio.acousticEchoCancellation = false;
                    Audio.avatarGain = 0;
                    Audio.serverInjectorGain = -96;
                    Audio.localInjectorGain = -96;
                    Audio.systemInjectorGain = -96;
                    Audio.setLocalEcho(false);
                    Audio.setServerEcho(false);
                    // Keep an already established voice domain intact. Looking
                    // it up again can enter the loading interstitial and pause
                    // the native source after the test clock has been prepared.
                    var domainPattern = new RegExp("^hifi://([^/?#]+)(?:[/?#]|$)", "i");
                    var currentDomain = domainPattern.exec(String(location.href));
                    var requestedDomain = domainPattern.exec(String(request.domainUrl));
                    if (!location.isConnected || !currentDomain || !requestedDomain
                            || currentDomain[1].toLowerCase() !== requestedDomain[1].toLowerCase()) {
                        location.handleLookupString(request.domainUrl);
                    }
                }
            } else if (request.action === "reset") {
                restoreVoice();
                result = Test.voiceTest(request);
            } else if (voiceOriginal !== null) {
                if (request.action === "send") { Audio.muted = request.muted; }
                result = Test.voiceTest(request);
            } else { result.error = "voice-session-unprepared"; }
            if (voiceOriginal !== null) {
                if (voiceWatchdog !== null) { Script.clearTimeout(voiceWatchdog); }
                voiceWatchdog = Script.setTimeout(restoreVoice, 120000);
            }
        }
        result.sampleEpochMs = Date.now();
        result.position = MyAvatar.position;
        result.connected = Boolean(location.isConnected);
        result.domainId = String(location.domainID);
        result.version = String(About.buildVersion);
        result.muted = Boolean(Audio.muted);
        result.localEcho = Boolean(Audio.getLocalEcho());
        result.serverEcho = Boolean(Audio.getServerEcho());
        Test.saveObject(result, "voice-result.json");
        return true;
    }

    function applyClientCommand(command) {
        if (applyVoice(command)) { return; }
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
            // app.launch already loaded this exact controlled serverless
            // scene. Applying the bounded location path keeps the single
            // Interface process and, unlike assigning the full URL again,
            // does not restart this probe before its readiness observation.
            if (scenePath !== "") {
                Window.location = scenePath;
            }
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
        if (clientCommandUnavailable || clientCommandRequest !== null) {
            return;
        }
        var commandUrl = clientCommandEndpoint();
        if (commandUrl === "") {
            return;
        }
        var request = new XMLHttpRequest();
        clientCommandRequest = request;
        request.onreadystatechange = function () {
            if (request.readyState !== request.DONE) {
                return;
            }
            clientCommandRequest = null;
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

    function removeAndroidControlledAssetEntities() {
        var ids = Entities.findEntities(MyAvatar.position, 1000.0);
        var index;
        for (index = 0; index < ids.length; index += 1) {
            var properties = Entities.getEntityProperties(ids[index], ["name"]);
            if (String(properties.name).indexOf("OVERTE_E2E_ASSET_LOAD") === 0) {
                Entities.deleteEntity(ids[index]);
            }
        }
        androidAssetEntityId = null;
        releaseAssetResource();
    }

    function applyAndroidControlCommand(command) {
        if (applyVoice(command)) { return; }
        if (!command || command.schemaVersion !== 1 || !command.commandId
                || command.commandId === lastAndroidControlCommandId) {
            return;
        }
        if (command.action === "reload-scene"
                && objectKeysMatch(command,
                    ["schemaVersion", "commandId", "action"])) {
            lastAndroidControlCommandId = String(command.commandId);
            reloadControlledScene(lastAndroidControlCommandId);
            return;
        }
        if (command.action === "enter-domain"
                && objectKeysMatch(command, ["schemaVersion", "commandId", "action", "url"])
                && typeof command.url === "string"
                && /^hifi:\/\/(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\]):[0-9]+(?:\/|$)/.test(command.url)) {
            lastAndroidControlCommandId = String(command.commandId);
            location.handleLookupString(command.url);
            return;
        }
        if (command.action === "load-asset"
                && objectKeysMatch(command, ["schemaVersion", "commandId", "action",
                    "assetId", "entityName", "url"])
                && typeof command.assetId === "string" && command.assetId.length > 0
                && typeof command.entityName === "string"
                && command.entityName.indexOf("OVERTE_E2E_ASSET_LOAD") === 0
                && httpUrl(command.url)) {
            removeAndroidControlledAssetEntities();
            androidAssetEntityId = Entities.addEntity({
                type: "Image",
                name: command.entityName,
                imageURL: command.url,
                userData: JSON.stringify({ overteE2EAssetId: command.assetId }),
                position: {
                    x: Number(MyAvatar.position.x),
                    y: Number(MyAvatar.position.y),
                    z: Number(MyAvatar.position.z) - 2.0
                },
                dimensions: { x: 1.0, y: 1.0, z: 0.01 },
                lifetime: 300
            }, "local");
            lastAndroidControlCommandId = String(command.commandId);
            return;
        }
        if (command.action === "sound-channel"
                && objectKeysMatch(command, ["schemaVersion", "commandId", "action",
                    "commandUrl"])
                && httpUrl(command.commandUrl)) {
            soundCommandUrl = String(command.commandUrl);
            lastAndroidControlCommandId = String(command.commandId);
            return;
        }
        if (command.action === "audio-mute"
                && objectKeysMatch(command, ["schemaVersion", "commandId", "action", "muted"])
                && typeof command.muted === "boolean") {
            Audio.muted = command.muted;
            lastAndroidControlCommandId = String(command.commandId);
            return;
        }
        if (command.action === "set-safe-setting"
                && objectKeysMatch(command, ["schemaVersion", "commandId", "action",
                    "settingId", "enabled"])
                && command.settingId === "audio.warn-when-muted"
                && typeof command.enabled === "boolean") {
            Audio.warnWhenMuted = command.enabled;
            lastAndroidControlCommandId = String(command.commandId);
        }
    }

    function pollAndroidControlCommand() {
        if (!androidControlAvailable) {
            return;
        }
        try {
            var command = Script.require(androidControlCommandUrl + "?sample="
                + sampleSequence);
            applyAndroidControlCommand(command);
        } catch (error) {
            // The launcher starts without a command and creates it on demand.
        }
    }

    function pollAndroidControlMarker() {
        if (!androidControlEligible) {
            return;
        }
        if (androidControlAvailable) {
            pollAndroidControlCommand();
            return;
        }
        try {
            var marker = Script.require(androidControlMarkerUrl);
            androidControlAvailable = marker.schemaVersion === 1
                && marker.channel === "android-debug-file-v1"
                && marker.probe === "overte_e2e_probe.js";
            if (androidControlAvailable && typeof marker.processId === "number"
                    && marker.processId > 0) {
                androidControlProcessId = marker.processId;
            }
        } catch (error) {
            androidControlAvailable = false;
        }
        pollAndroidControlCommand();
    }

    function pollSoundCommand() {
        if (!soundCommandUrl || soundCommandRequest !== null) {
            return;
        }
        var request = new XMLHttpRequest();
        soundCommandRequest = request;
        request.onreadystatechange = function () {
            if (request.readyState !== request.DONE) {
                return;
            }
            soundCommandRequest = null;
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

    function observeVerticalMotion(observation) {
        observation = observation || {
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

    function consumeNativeMotion(history, now) {
        if (!androidControlProcessId || !history || history.schemaVersion !== 1
                || history.processId !== androidControlProcessId
                || history.source !== "native-avatar-motion"
                || !Array.isArray(history.samples)
                || typeof history.updatedEpochMs !== "number"
                || !isFinite(history.updatedEpochMs)
                || history.updatedEpochMs > now + 1000
                || now - history.updatedEpochMs > 5000) {
            return;
        }
        history.samples.forEach(function (entry) {
            var motion = entry.avatarMotion;
            if (typeof entry.sampleSequence !== "number"
                    || !isFinite(entry.sampleSequence)
                    || entry.sampleSequence <= nativeMotionLastSequence
                    || typeof entry.sampleEpochMs !== "number"
                    || !isFinite(entry.sampleEpochMs)
                    || entry.sampleEpochMs > now + 1000
                    || now - entry.sampleEpochMs > 5000
                    || !motion || !motion.position
                    || typeof motion.position.y !== "number"
                    || !isFinite(motion.position.y)
                    || typeof motion.inAir !== "boolean"
                    || typeof motion.flying !== "boolean") {
                return;
            }
            nativeMotionLastSequence = entry.sampleSequence;
            nativeMotionUpdatedEpochMs = entry.sampleEpochMs;
            nativeMotionAvailable = true;
            observeVerticalMotion({ y: motion.position.y,
                inAir: motion.inAir, flying: motion.flying });
        });
    }

    function pollNativeMotion(now) {
        if (!androidControlProcessId || now - nativeMotionLastRequestEpochMs < 500) {
            return;
        }
        nativeMotionLastRequestEpochMs = now;
        var moduleId = nativeMotionUrl + "?sample=" + now;
        try {
            // The fixed private-file loader is supported by the Android script
            // engine; local XMLHttpRequest does not complete on this runtime.
            consumeNativeMotion(Script.require(moduleId), Date.now());
        } catch (error) {
            // Missing or malformed observations cannot produce events.
        } finally {
            // Each fresh URL is a one-use observation, not a persistent module.
            // Release only our own entry; preserve all other script modules.
            try {
                delete Script.require.cache[Script.require.resolve(moduleId)];
            } catch (error) {
                // An unavailable native source has no resolvable cache entry.
            }
        }
    }

    function sample(now, verticalObservationMs) {
        var phaseEpochMs = Date.now();
        var timing = { schemaVersion: 1, startedEpochMs: phaseEpochMs,
            processId: androidControlProcessId,
            previousSampleIntervalMs: lastCompletedSampleEpochMs
                ? now - lastCompletedSampleEpochMs : null,
            verticalMotionObservationMs: verticalObservationMs, phasesMs: {} };
        function phase(name) {
            var completed = Date.now();
            timing.phasesMs[name] = completed - phaseEpochMs;
            phaseEpochMs = completed;
            timing.completedPhase = name;
            timing.updatedEpochMs = completed;
            if (androidControlAvailable) {
                Test.saveObject(timing, "pico-probe-timing-in-progress.json");
            }
        }
        pollAndroidControlMarker();
        pollClientCommand();
        pollSoundCommand();
        phase("controlPolling");
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
        phase("locationAndFlight");
        var ids = Entities.findEntities(MyAvatar.position, 1000.0);
        phase("entitySearch");
        var foundMarkers = {};
        var foundDomainMarkers = {};
        var sharedEntityCount = 0;
        var sharedObservation = null;
        var interactionTargetAvailable = false;
        var scriptedEntity = {
            targetAvailable: false, loaded: false, scriptUrl: "", activationCount: 0,
            state: "unavailable", color: null
        };
        var floorTopY = null;
        var collisionWall = null;
        var index;
        for (index = 0; index < ids.length; index += 1) {
            var properties = Entities.getEntityProperties(ids[index], [
                "name", "position", "dimensions", "script", "userData", "color", "lastEditedBy"
            ]);
            if (fixtureMarkers.indexOf(properties.name) !== -1) {
                foundMarkers[properties.name] = true;
            }
            if (domainMarkers.indexOf(properties.name) !== -1) {
                foundDomainMarkers[properties.name] = true;
            }
            if (androidControlAvailable && properties.name === "OVERTE_E2E_SHARED_COLOR") {
                sharedEntityCount += 1;
                sharedObservation = controlledSharedObservation(properties);
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
            if (properties.name === interactionTargetName) {
                interactionTargetAvailable = true;
                var metadata = null;
                try {
                    metadata = JSON.parse(String(properties.userData));
                } catch (error) {
                    metadata = null;
                }
                scriptedEntity = {
                    targetAvailable: true,
                    loaded: Boolean(metadata && metadata.contract ===
                        "overte-e2e-scripted-entity-v1" && metadata.loaded === true),
                    scriptUrl: String(properties.script),
                    activationCount: metadata && isFinite(Number(metadata.activationCount))
                        ? Math.max(0, Math.floor(Number(metadata.activationCount))) : 0,
                    state: metadata && (metadata.state === "active" || metadata.state === "idle")
                        ? metadata.state : "idle",
                    color: {
                        red: Math.floor(Number(properties.color.red)),
                        green: Math.floor(Number(properties.color.green)),
                        blue: Math.floor(Number(properties.color.blue))
                    }
                };
            }
        }
        phase("entityProperties");
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
        var avatarFeetPosition = vector(MyAvatar.feetPosition);
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
        var avatarAboveFloor = floorTopY !== null
            && avatarFeetPosition.y >= floorTopY - 0.05;
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
            } else if (soundState.started) {
                soundState.finished = true;
                soundState.finishReason = soundStopRequested ? "stopped" : "natural";
            }
        }
        phase("avatarAndCamera");
        sampleSequence += 1;
        if (androidControlAvailable) {
            // Separate private evidence keeps real native author identity out
            // of the portable, publishable snapshot. No client entity edit is
            // performed here: all values come from received entity properties.
            Test.saveObject({ schemaVersion: 1, sampleEpochMs: now, sampleSequence: sampleSequence,
                entityCount: sharedEntityCount,
                observation: sharedEntityCount === 1 ? sharedObservation : null }, "pico-collaboration-observation.json");
        }
        orientationHistory.push({
            sampleSequence: sampleSequence,
            orientation: vector(orientation)
        });
        if (orientationHistory.length > 48) {
            orientationHistory.shift();
        }
        phase("collaborationSnapshotAndHistory");
        // QVariantMap exposure converts an entire channel directory on every
        // property access. Read each directory once per sample; input values
        // and poses still come from the live Controller API on every query.
        var standardChannels = Controller.Standard;
        var actionChannels = Controller.Actions;
        var hardwareChannels = Controller.Hardware;
        var observedController = {
                route: {
                    openxrAxes: openXrAxes(hardwareChannels.OpenXR),
                    standardLy: Number(Controller.getValue(standardChannels.LY)),
                    translateYAction: Number(Controller.getValue(actionChannels.TranslateY)),
                    rawTranslateYDriveKey: Number(MyAvatar.getRawDriveKey(DriveKeys.TRANSLATE_Y)),
                    translateYDriveKeyDisabled: Boolean(MyAvatar.isDriveKeyDisabled(DriveKeys.TRANSLATE_Y)),
                    translateZAction: Number(Controller.getValue(actionChannels.TranslateZ)),
                    rawTranslateZDriveKey: Number(MyAvatar.getRawDriveKey(DriveKeys.TRANSLATE_Z)),
                    translateZDriveKeyDisabled: Boolean(MyAvatar.isDriveKeyDisabled(DriveKeys.TRANSLATE_Z))
                },
                axes: {
                    lx: Number(Controller.getValue(standardChannels.LX)),
                    ly: Number(Controller.getValue(standardChannels.LY)),
                    rx: Number(Controller.getValue(standardChannels.RX)),
                    ry: Number(Controller.getValue(standardChannels.RY)),
                    leftTrigger: Number(Controller.getValue(standardChannels.LT)),
                    rightTrigger: Number(Controller.getValue(standardChannels.RT)),
                    leftGrip: Number(Controller.getValue(standardChannels.LeftGrip)),
                    rightGrip: Number(Controller.getValue(standardChannels.RightGrip))
                },
                buttons: {
                    menu: Boolean(Controller.getValue(hardwareChannels.OpenXR
                        ? hardwareChannels.OpenXR.Start : standardChannels.Start)),
                    leftPrimary: Boolean(Controller.getValue(standardChannels.LeftPrimaryThumb)),
                    leftSecondary: Boolean(Controller.getValue(standardChannels.LeftSecondaryThumb)),
                    leftThumbstick: Boolean(Controller.getValue(standardChannels.LS)),
                    leftTrigger: Boolean(Controller.getValue(standardChannels.LTClick)),
                    rightPrimary: Boolean(Controller.getValue(standardChannels.RightPrimaryThumb)),
                    rightSecondary: Boolean(Controller.getValue(standardChannels.RightSecondaryThumb)),
                    rightThumbstick: Boolean(Controller.getValue(standardChannels.RS)),
                    rightTrigger: Boolean(Controller.getValue(standardChannels.RTClick))
                },
                poses: {
                    left: controllerPose(standardChannels.LeftHand),
                    right: controllerPose(standardChannels.RightHand)
                }
        };
        phase("controller");
        Test.saveObject({
            schemaVersion: 2,
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
            control: androidControlAvailable ? {
                schemaVersion: 1,
                channel: "android-debug-file-v1",
                probe: "overte_e2e_probe.js",
                lastCommandId: lastAndroidControlCommandId
            } : null,
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
            audio: {
                muted: Boolean(Audio.muted)
            },
            settings: {
                audioWarnWhenMuted: Boolean(Audio.warnWhenMuted)
            },
            render: {
                frameCount: renderFrameCount,
                lastFrameEpochMs: renderLastFrameEpochMs
            },
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
                feetPosition: avatarFeetPosition,
                velocity: vector(MyAvatar.velocity),
                bodyYawDegrees: Number(MyAvatar.bodyYaw),
                inAir: Boolean(MyAvatar.isInAir()),
                flying: Boolean(MyAvatar.isFlying()),
                flyingEnabled: Boolean(MyAvatar.getFlyingEnabled())
            },
            verticalEvents: verticalEvents,
            nativeMotion: { processId: androidControlProcessId,
                sampleSequence: nativeMotionLastSequence,
                sampleEpochMs: nativeMotionUpdatedEpochMs },
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
            interaction: {
                targetAvailable: interactionTargetAvailable,
                pressCount: interactionPressCount,
                lastEntityName: interactionLastEntityName,
                lastPointerId: interactionLastPointerId
            },
            scriptedEntity: scriptedEntity,
            peer: controlledPeer(),
            controller: observedController,
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
        phase("snapshotSerializationAndWrite");
        timing.sampleSequence = sampleSequence;
        timing.completedEpochMs = Date.now();
        lastCompletedSampleEpochMs = now;
        Test.saveObject(timing, "pico-probe-timing.json");
    }

    function updateProbe() {
        var observationStartedMs = Date.now();
        observeDispatcherRay(observationStartedMs);
        // Other Android products also publish the process marker but do not
        // provide the Pico application-thread history. Keep their real direct
        // observations until a valid native source is actually available.
        if (!nativeMotionAvailable) {
            observeVerticalMotion();
        }
        pollNativeMotion(observationStartedMs);
        var now = Date.now();
        if (lastSampleEpochMs !== 0 && now - lastSampleEpochMs < sampleIntervalMs) {
            return;
        }
        lastSampleEpochMs = now;
        try {
            sample(now, now - observationStartedMs);
            lastProbeError = "";
        } catch (error) {
            probeErrorCount += 1;
            var detail = safeErrorText(error);
            Test.saveObject({
                schemaVersion: 1,
                sampleEpochMs: Date.now(),
                sampleSequence: sampleSequence,
                errorCount: probeErrorCount,
                detail: detail
            }, "overte-probe-error.json");
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
        Script.clearInterval(interactionPointerDiscovery);
        Messages.messageReceived.disconnect(observeDispatcherPointers);
        Messages.unsubscribe(interactionPointerChannel);
        restoreVoice();
        releaseControlledKey(controlledKeyCommandId);
        Controller.disableMapping(controlledInputMappingName);
        Entities.mousePressOnEntity.disconnect(observePrimaryInteraction);
        if (renderStats && renderStats.newStats) {
            renderStats.newStats.disconnect(observeRenderedFrame);
        }
        if (flightNormalizationActive) {
            MyAvatar.setFlyingEnabled(flyingEnabledBeforeNormalization);
            flightNormalizationActive = false;
        }
        if (controlledTabletOpen()) {
            HMD.closeTablet();
        }
        releaseAssetResource();
        if (androidAssetEntityId !== null) {
            Entities.deleteEntity(androidAssetEntityId);
            androidAssetEntityId = null;
        }
        if (controlledAssetEntity !== null) {
            Entities.deleteEntity(controlledAssetEntity);
            controlledAssetEntity = null;
        }
    });
    updateProbe();
}());
