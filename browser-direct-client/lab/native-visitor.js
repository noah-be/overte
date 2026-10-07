// SPDX-License-Identifier: Apache-2.0
// Observe the real packaged native client; the domain path chooses its spawn.
(function () {
    "use strict";
    MyAvatar.displayName = "direct-lab-native";
    var nativeSkeletonModelURL = "https://127.0.0.1:46119/default-avatar/defaultAvatar_full.fst";
    var nativeModelSelected = false;
    Audio.muted = false;
    Audio.noiseReduction = false;
    Audio.pushToTalk = false;
    var sequence = 0;
    var nativeTestSetup = null;
    var nativeNavigationRetry = null;
    var nativeMotionTest = null;
    var motionPending = false;
    var motionRequest = null;
    var motionURL = "https://127.0.0.1:46119/native-control/motion.json";
    var bridgeID = "{b42a2c92-2a33-400d-a6b4-30e3d3ff2282}";
    var placementPending = false;
    var placementRequest = null;
    var placementDiagnosticPrinted = false;
    // Packaged Qt's XMLHttpRequest sendCustomRequest does not read file: URLs.
    // This static test instruction contains only this visitor's public pose/session.
    var placementURL = "https://127.0.0.1:46119/native-control/placement.json";
    function checkPlacement() {
        if (placementPending || nativeTestSetup || !location.isConnected) { return; }
        placementPending = true;
        var request = new XMLHttpRequest();
        placementRequest = request;
        request.timeout = 1000;
        request.requestComplete.connect(function () {
            placementPending = false;
            placementRequest = null;
            if (!placementDiagnosticPrinted) {
                placementDiagnosticPrinted = true;
                print("DIRECT_LAB_NATIVE_CONTROL " + JSON.stringify({
                    localControlURL: placementURL, readyState: request.readyState,
                    status: request.status, responseLength: request.responseText.length
                }));
            }
            if (!request.responseText || request.responseText.length > 16384) { return; }
            try {
                var instruction = JSON.parse(request.responseText);
                if (!instruction.enabled || instruction.session !== String(MyAvatar.sessionUUID)) { return; }
                if (instruction.operation === "ordinary-domain-path") {
                    if (nativeNavigationRetry || instruction.url !== "hifi://127.0.0.3:46102/") { return; }
                    nativeNavigationRetry = { label: instruction.label, requestId: instruction.requestId,
                        url: instruction.url, beforeNavigation: MyAvatar.position };
                    location.handleLookupString(instruction.url);
                    print("DIRECT_LAB_NATIVE_PATH_RETRY " + JSON.stringify(nativeNavigationRetry));
                    return;
                }
                if (!instruction.offset ||
                    instruction.offset.x !== 0 || instruction.offset.y !== 0 || instruction.offset.z !== -3) { return; }
                var before = MyAvatar.position;
                var distance = Math.pow(before.x - 155.084, 2) + Math.pow(before.y + 98.5, 2) +
                    Math.pow(before.z + 397.328, 2);
                if (distance > 4) { return; }
                nativeTestSetup = { label: instruction.label, requestId: instruction.requestId,
                    session: String(MyAvatar.sessionUUID),
                    beforePlacement: before, offset: instruction.offset,
                    normalDomainSpawnObserved: instruction.normalDomainSpawnObserved };
                MyAvatar.position = Vec3.sum(before, instruction.offset);
                print("DIRECT_LAB_NATIVE_SETUP " + JSON.stringify(nativeTestSetup));
            } catch (ignored) { /* A pending or absent local control file does not move a visitor. */ }
        });
        request.open("GET", placementURL, true);
        request.send();
    }
    function point(value) {
        return value && ["x", "y", "z"].every(function (axis) {
            return typeof value[axis] === "number" && isFinite(value[axis]);
        });
    }
    function copyPoint(value) { return { x: value.x, y: value.y, z: value.z }; }
    function sameHorizontalPosition(first, second, tolerance) {
        return Math.abs(first.x - second.x) <= tolerance && Math.abs(first.z - second.z) <= tolerance;
    }
    function checkMotion() {
        if (motionPending || !location.isConnected || !nativeTestSetup ||
                (nativeMotionTest && nativeMotionTest.phase === "restored")) { return; }
        motionPending = true;
        var request = new XMLHttpRequest();
        motionRequest = request;
        request.timeout = 1000;
        request.requestComplete.connect(function () {
            motionPending = false;
            motionRequest = null;
            if (request.status !== 200 || !request.responseText || request.responseText.length > 4096) { return; }
            try {
                var instruction = JSON.parse(request.responseText);
                var session = String(MyAvatar.sessionUUID);
                var now = Date.now() / 1000;
                var nonce = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
                if (!instruction.enabled || instruction.session !== session || nativeTestSetup.session !== session ||
                        instruction.placementRequestId !== nativeTestSetup.requestId ||
                        typeof instruction.requestId !== "string" || !nonce.test(instruction.requestId) ||
                        typeof instruction.commandId !== "string" || !nonce.test(instruction.commandId) ||
                        typeof instruction.issuedUnixTime !== "number" || !isFinite(instruction.issuedUnixTime) ||
                        typeof instruction.expiresUnixTime !== "number" || !isFinite(instruction.expiresUnixTime) ||
                        instruction.issuedUnixTime > now + 2 || instruction.expiresUnixTime < now ||
                        instruction.expiresUnixTime - instruction.issuedUnixTime !== 6 ||
                        typeof instruction.referenceSequence !== "number" ||
                        Math.floor(instruction.referenceSequence) !== instruction.referenceSequence ||
                        instruction.referenceSequence < 1 ||
                        instruction.referenceSequence > sequence || instruction.referenceSequence < sequence - 16 ||
                        !point(instruction.beforePosition) || !point(instruction.offset) ||
                        instruction.offset.x !== 0 || instruction.offset.y !== 0 || instruction.offset.z !== -1) { return; }
                var before = copyPoint(MyAvatar.position);
                if (!sameHorizontalPosition(before, instruction.beforePosition, 0.25) ||
                        Math.abs(before.y - instruction.beforePosition.y) > 1 ||
                        Date.now() / 1000 >= instruction.expiresUnixTime) { return; }
                if (instruction.operation === "move") {
                    if (nativeMotionTest) { return; }
                    var target = { x: before.x, y: before.y, z: before.z - 1 };
                    nativeMotionTest = {
                        requestId: instruction.requestId, session: session,
                        placementRequestId: nativeTestSetup.requestId, phase: "moved",
                        label: "Explicit native-only one-metre -Z motion along the actual bridge after ordinary spawn and rig proof",
                        browserMoved: false, beforePosition: before, moveTargetPosition: target,
                        moveCommandId: instruction.commandId, moveAfterNativeSequence: sequence,
                        moveIssuedUnixTime: instruction.issuedUnixTime, moveAppliedUnixTime: now
                    };
                    MyAvatar.position = target;
                    nativeMotionTest.moveAppliedPosition = copyPoint(MyAvatar.position);
                    print("DIRECT_LAB_NATIVE_MOTION " + JSON.stringify(nativeMotionTest));
                } else if (instruction.operation === "restore") {
                    if (!nativeMotionTest || nativeMotionTest.phase !== "moved" ||
                            nativeMotionTest.requestId !== instruction.requestId ||
                            nativeMotionTest.moveCommandId === instruction.commandId ||
                            !sameHorizontalPosition(before, nativeMotionTest.moveTargetPosition, 0.25) ||
                            Math.abs(before.y - nativeMotionTest.beforePosition.y) > 1) { return; }
                    MyAvatar.position = copyPoint(nativeMotionTest.beforePosition);
                    nativeMotionTest.phase = "restored";
                    nativeMotionTest.restoreCommandId = instruction.commandId;
                    nativeMotionTest.restoreAfterNativeSequence = sequence;
                    nativeMotionTest.restoreIssuedUnixTime = instruction.issuedUnixTime;
                    nativeMotionTest.restoreAppliedUnixTime = now;
                    nativeMotionTest.restoreAppliedPosition = copyPoint(MyAvatar.position);
                    print("DIRECT_LAB_NATIVE_MOTION " + JSON.stringify(nativeMotionTest));
                }
            } catch (ignored) { /* Invalid or stale instructions never move this participant. */ }
        });
        request.open("GET", motionURL, true);
        request.send();
    }
    function meshEvidence(id) {
        try {
            var model = Graphics.getModel(id);
            var meshes = model.meshes;
            var vertices = 0;
            var indices = 0;
            for (var i = 0; i < meshes.length; i++) {
                vertices += meshes[i].numVertices;
                indices += meshes[i].numIndices;
            }
            return { objectID: String(model.objectID), meshCount: model.numMeshes,
                vertices: vertices, indices: indices, materialNames: model.materialNames };
        } catch (error) {
            return { meshCount: 0, unavailable: String(error).slice(0, 300) };
        }
    }
    function jointEvidence() {
        var result = { getterOnly: true, joints: {},
            singleJointAPIs: "getJointTranslation/getJointRotation: SkeletonModel parent-relative model pose",
            absoluteAPIs: "getAbsoluteJointTranslationInObjectFrame/getAbsoluteJointRotationInObjectFrame: avatar object frame, including native rig-to-avatar Y180 conversion",
            normalizationApplied: false };
        if (typeof MyAvatar.getJointIndex !== "function" ||
                typeof MyAvatar.getJointTranslation !== "function" ||
                typeof MyAvatar.getJointRotation !== "function" ||
                typeof MyAvatar.getAbsoluteJointTranslationInObjectFrame !== "function" ||
                typeof MyAvatar.getAbsoluteJointRotationInObjectFrame !== "function") {
            result.unavailable = "The native joint getter APIs are not exposed";
            return result;
        }
        ["Hips", "Head", "LeftArm", "RightArm"].forEach(function (name) {
            try {
                var index = MyAvatar.getJointIndex(name);
                if (index < 0) { result.joints[name] = { index: index, unavailable: "Joint is not loaded" }; return; }
                result.joints[name] = { index: index,
                    parentRelativeModelTranslation: MyAvatar.getJointTranslation(index),
                    parentRelativeModelRotation: MyAvatar.getJointRotation(index),
                    absoluteAvatarObjectTranslation: MyAvatar.getAbsoluteJointTranslationInObjectFrame(index),
                    absoluteAvatarObjectRotation: MyAvatar.getAbsoluteJointRotationInObjectFrame(index) };
            } catch (error) {
                result.joints[name] = { unavailable: String(error).slice(0, 300) };
            }
        });
        return result;
    }
    function report() {
        var position = MyAvatar.position;
        var spawnDistance = Math.pow(position.x - 155.084, 2) + Math.pow(position.y + 98.5, 2) +
            Math.pow(position.z + 397.328, 2);
        if (!nativeModelSelected && location.isConnected && !nativeTestSetup && spawnDistance <= 4) {
            nativeModelSelected = true;
            MyAvatar.useFullAvatarURL(nativeSkeletonModelURL, "Actual Overte mannequin lab fixture");
            print("DIRECT_LAB_NATIVE_MODEL_SETUP " + JSON.stringify({
                label: "Explicit native participant model selection using unchanged Overte mannequin assets",
                ordinaryDomainSpawnPosition: position,
                requestedSkeletonModelURL: nativeSkeletonModelURL,
                actualSkeletonModelURLAfterCall: MyAvatar.skeletonModelURL
            }));
        }
        var entities = Entities.findEntities(MyAvatar.position, 50);
        var loadedATPModels = 0;
        var availableATPModels = 0;
        entities.forEach(function (id) {
            var properties = Entities.getEntityProperties(id, ["type", "modelURL"]);
            if (properties.type === "Model" && properties.modelURL.indexOf("atp:") === 0) {
                availableATPModels++;
                if (Entities.isLoaded(id)) { loadedATPModels++; }
            }
        });
        var peers = AvatarList.getAvatarIdentifiers().slice(0, 20).map(function (id) {
            var avatar = AvatarList.getAvatar(id);
            return { id: String(id), displayName: avatar.displayName,
                position: avatar.position, audioLoudness: avatar.audioLoudness };
        });
        print("DIRECT_LAB_NATIVE " + JSON.stringify({
            sequence: ++sequence, observedAtUnixTime: Date.now() / 1000,
            connected: location.isConnected,
            domain: location.hostname, session: String(MyAvatar.sessionUUID),
            position: MyAvatar.position, orientation: MyAvatar.orientation,
            cameraPosition: Camera.position, cameraMode: Camera.mode,
            renderEntities: Scene.shouldRenderEntities,
            skeletonModelURL: MyAvatar.skeletonModelURL,
            avatarJointCount: MyAvatar.jointNames.length,
            nativeSkeletonJointEvidence: jointEvidence(),
            avatarGraphics: meshEvidence(MyAvatar.sessionUUID),
            entitiesNearSpawn: entities.length,
            availableATPModels: availableATPModels, loadedATPModels: loadedATPModels,
            httpsBridge: { id: bridgeID, loaded: Entities.isLoaded(bridgeID),
                modelURL: Entities.getEntityProperties(bridgeID, ["modelURL"]).modelURL,
                graphics: meshEvidence(bridgeID) },
            peers: peers, muted: Audio.muted, inputLevel: Audio.inputLevel,
            nativeTestSetup: nativeTestSetup,
            nativeNavigationRetry: nativeNavigationRetry,
            nativeMotionControlVersion: 2,
            nativeMotionTest: nativeMotionTest,
            syntheticAudioOnly: true
        }));
        checkPlacement();
        checkMotion();
    }
    report();
    var interval = Script.setInterval(report, 2000);
    Script.scriptEnding.connect(function () { Script.clearInterval(interval); });
}());
