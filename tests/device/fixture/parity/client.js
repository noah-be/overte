// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
// Load this ordinary client script from the fixture server's ready metadata.
(function () {
    "use strict";
    var page = Script.resolvePath("index.html"), injected = Script.resolvePath("injected.js");
    var tablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
    var entity = null, tabletOpen = false, stopped = false;
    var button = tablet.addButton({text: "WEB TEST", sortOrder: 200});
    function respond(message, surface, send) {
        var packet;
        if (typeof message !== "string" || message.length > 4096) return;
        try { packet = JSON.parse(message); } catch (_) { return; }
        if (!packet || packet.contract !== "overte-web-parity-v1" || packet.action !== "echo" ||
                typeof packet.sequence !== "number" || !isFinite(packet.sequence) ||
                packet.sequence < 1 || packet.sequence > 1000000 || Math.floor(packet.sequence) !== packet.sequence) return;
        send(JSON.stringify({contract: packet.contract, action: "echo", sequence: packet.sequence, surface: surface}));
    }
    function worldEvent(id, message) {
        if (!stopped && entity && String(id) === String(entity)) {
            respond(message, "world", function (reply) { Entities.emitScriptEvent(entity, reply); });
        }
    }
    function tabletEvent(message) {
        // Deliberately no origin check in this bounded diagnostic echo. The
        // native source grant must reject a foreign document, not this script.
        if (!stopped) respond(message, "tablet", function (reply) { tablet.emitScriptEvent(reply); });
    }
    function screenChanged(type, url) {
        tabletOpen = type === "Web" && String(url).split("?")[0] === page;
        button.editProperties({isActive: tabletOpen});
    }
    function clicked() {
        if (tabletOpen) tablet.gotoHomeScreen();
        else tablet.gotoWebScreen(page);
    }
    // This is a temporary local entity in the same world on each client. It
    // neither writes domain content nor grants the page any other script APIs.
    var forward = Quat.getForward(MyAvatar.orientation);
    var center = Vec3.sum(MyAvatar.position, Vec3.multiply(2.5, forward));
    center.y += 1.4;
    entity = Entities.addEntity({type: "Web", name: "OVERTE_PARITY_WEB_REFERENCE", sourceUrl: page,
        scriptURL: injected, position: center, rotation: MyAvatar.orientation,
        dimensions: {x: 1.8, y: 2.2, z: 0.01}, dpi: 40, maxFPS: 30,
        grab: {grabbable: false}, collisionless: true}, "local");
    Entities.webEventReceived.connect(worldEvent);
    tablet.webEventReceived.connect(tabletEvent);
    tablet.screenChanged.connect(screenChanged);
    button.clicked.connect(clicked);
    print("Web parity reference loaded; use WEB TEST for tablet and the local surface ahead. Device outcomes remain unverified.");
    Script.scriptEnding.connect(function () {
        stopped = true;
        Entities.webEventReceived.disconnect(worldEvent);
        tablet.webEventReceived.disconnect(tabletEvent);
        tablet.screenChanged.disconnect(screenChanged);
        button.clicked.disconnect(clicked);
        if (tabletOpen) tablet.gotoHomeScreen();
        tablet.removeButton(button);
        if (entity) Entities.deleteEntity(entity);
    });
}());
