// SPDX-License-Identifier: Apache-2.0
// The isolated second participant and representative real Overte test scene.
(function () {
    "use strict";
    Render.viewportResolutionScale = 0.5;
    Audio.muted = true;
    Audio.noiseReduction = false;
    MyAvatar.displayName = "Native-Lab-Participant";
    var initialized = false;
    var sceneIDs = [];
    var commandSequence = 0;
    var avatarSampleDiagnostics = typeof BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS !== 'undefined' && BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS === true
        && typeof createNativeAvatarSampleDiagnostics === 'function'
        ? createNativeAvatarSampleDiagnostics({print:print,window:Window,mode:typeof BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS_MODE !== 'undefined'?BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS_MODE:'full',stats:typeof Stats !== 'undefined'?Stats:null,avatar:MyAvatar,
            current:function(){return !!location.isConnected;}}) : null;
    function report(kind, data) {
        print("BROWSER_LAB " + JSON.stringify({ kind: kind, at: Date.now(), data: data }));
    }
    function entity(properties) {
        properties.name = "Browser Lab " + properties.name;
        var id = Entities.addEntity(properties);
        sceneIDs.push(id);
        return id;
    }
    function initialize() {
        if (initialized || !Entities.canRez()) { return; }
        initialized = true;
        MyAvatar.position = { x: 3, y: 1.8, z: 3 };
        MyAvatar.orientation = Quat.fromPitchYawRollDegrees(0, 180, 0);
        // These are domain entities, persisted and broadcast by the real entity server.
        var existing = Entities.findEntities({ x: 0, y: 0, z: 0 }, 50).filter(function (id) {
            return Entities.getEntityProperties(id, ["name"]).name.indexOf("Browser Lab ") === 0;
        });
        existing.forEach(function (id) { Entities.deleteEntity(id); });
        entity({ name: "Floor", type: "Box", position: { x: 0, y: -0.25, z: 0 },
            dimensions: { x: 20, y: 0.5, z: 20 }, color: { red: 110, green: 125, blue: 145 },
            collisionless: false, locked: false });
        entity({ name: "Collision Wall", type: "Box", position: { x: -3, y: 1.5, z: -4 },
            dimensions: { x: 5, y: 3, z: 0.5 }, color: { red: 90, green: 155, blue: 205 }, collisionless: false });
        entity({ name: "Interactable", type: "Box", position: { x: 0, y: 1.5, z: -3 },
            dimensions: { x: 1, y: 3, z: 1 }, color: { red: 235, green: 145, blue: 40 },
            collisionless: false, userData: JSON.stringify({ browserInteraction: "toggleColor", browserClient: { interactable: true } }) });
        entity({ name: "Sphere", type: "Sphere", position: { x: 2, y: 1, z: -4 },
            dimensions: { x: 1.2, y: 1.2, z: 1.2 }, color: { red: 175, green: 90, blue: 205 }, collisionless: false });
        entity({ name: "Welcome", type: "Text", position: { x: 0, y: 2.5, z: -6 },
            dimensions: { x: 4, y: 1, z: 0.01 }, text: "Overte browser and native laboratory",
            textColor: { red: 255, green: 255, blue: 255 }, backgroundColor: { red: 30, green: 40, blue: 60 }, lineHeight: 0.25 });
        var binary = new XMLHttpRequest();
        binary.open("GET", "http://127.0.0.1:45110/checker.png");
        binary.responseType = "arraybuffer";
        binary.onreadystatechange = function () {
            if (binary.readyState !== 4) { return; }
            if (binary.status !== 200) { report("binary-asset-error", { status: binary.status }); return; }
            Assets.putAsset({ data: binary.response, path: "/browser-lab/checker.png" }, function (error, result) {
                if (error) { report("binary-asset-error", { error: String(error) }); return; }
                report("binary-asset-created", { url: result.url, hash: result.hash, bytes: result.byteLength });
            });
        };
        binary.send();
        var request = new XMLHttpRequest();
        request.open("GET", "http://127.0.0.1:45110/textured-cube.gltf");
        request.onreadystatechange = function () {
            if (request.readyState !== 4) { return; }
            if (request.status !== 200) { report("asset-error", { status: request.status }); return; }
            Assets.putAsset({ data: request.responseText, path: "/browser-lab/textured-cube.gltf" }, function (error, result) {
                if (error) { report("asset-error", { error: String(error) }); return; }
                var id = entity({ name: "ATP Textured Model", type: "Model", modelURL: "atp:/browser-lab/textured-cube.gltf",
                    position: { x: -2, y: 1, z: -2 }, dimensions: { x: 1.5, y: 1.5, z: 1.5 }, collisionless: false });
                report("asset-created", { id: id, url: result.url, hash: result.hash });
            });
        };
        request.send();
        entity({ name: "HTTPS Textured Model", type: "Model",
            modelURL: "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/BoxTextured/glTF/BoxTextured.gltf",
            position: { x: 4, y: 0.7, z: -3 }, dimensions: { x: 1.4, y: 1.4, z: 1.4 }, collisionless: false });
        report("scene-created", { ids: sceneIDs, canRez: Entities.canRez(), canWriteAssets: Entities.canWriteAssets() });
    }
    Script.setInterval(function () {
        initialize();
        var ids = AvatarList.getAvatarIdentifiers();
        var avatars = ids.filter(function (id) { return id && String(id) !== String(MyAvatar.sessionUUID)
            && String(id).replace(/[{}-]/g, "") !== "00000000000000000000000000000000"; }).map(function (id) {
            var avatar = AvatarList.getAvatar(id);
            return { id: id, displayName: avatar.displayName, position: avatar.position };
        });
        var entities = Entities.findEntities({ x: 0, y: 0, z: 0 }, 50).map(function (id) {
            var e = Entities.getEntityProperties(id, ["name", "type", "color", "modelURL", "position"]);
            return { id: id, name: e.name, type: e.type, color: e.color, modelURL: e.modelURL, position: e.position };
        });
        report("observation", { selfId: MyAvatar.sessionUUID, position: MyAvatar.position, muted: Audio.muted, inputLevel: Audio.inputLevel,
            avatars: avatars, entities: entities });
        if (avatarSampleDiagnostics) avatarSampleDiagnostics.authorObservation();
    }, 2000);
    Script.setInterval(function () {
        var request = new XMLHttpRequest();
        request.open("GET", "http://127.0.0.1:45110/command.json?t=" + Date.now());
        request.onreadystatechange = function () {
            if (request.readyState !== 4 || request.status !== 200) { return; }
            var command;
            try { command = JSON.parse(request.responseText); } catch (error) { return; }
            if (!command.sequence || command.sequence <= commandSequence) { return; }
            commandSequence = command.sequence;
            if (command.position) { MyAvatar.position = command.position; }
            if (command.orientation) { MyAvatar.orientation = command.orientation; }
            if (command.camera) {
                Camera.mode = "independent";
                Camera.position = command.camera.position;
                Camera.lookAt(command.camera.target);
            }
            if (typeof command.muted === "boolean") { Audio.muted = command.muted; }
            report("command-applied", command);
            if (avatarSampleDiagnostics) avatarSampleDiagnostics.authorObservation();
        };
        request.send();
    }, 500);
    if (avatarSampleDiagnostics) Script.scriptEnding.connect(function(){avatarSampleDiagnostics.stop();});
    report("started", { version: About.version });
}());
