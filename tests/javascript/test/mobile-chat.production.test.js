"use strict";
const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");
const { FakeSignal, createScriptApi, createTabletApi, createMessagesApi, runProductionScript } = require("../support");
const source = path.resolve(__dirname, "../../../scripts/communityScripts/armored-chat/armored_chat.js");

function start({ desktop = false, config = {} } = {}) {
    const Script = createScriptApi();
    const Tablet = createTabletApi();
    const tablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
    tablet.toolbarMode = desktop;
    tablet.tabletShown = true;
    const Messages = createMessagesApi();
    Messages.sendLocalMessage = (channel, message) => Messages.sendMessage(channel, message, true);
    const values = new Map([["ArmoredChat-Messages", []], ["ArmoredChat-Config", config]]);
    const Controller = { keyPressEvent: new FakeSignal() };
    const windows = [];
    function window() {
        const value = { title: "Chat", visible: false, closed: new FakeSignal(), fromQml: new FakeSignal(),
            packets: [], sendToQml(packet) { this.packets.push(packet); }, close() { this.closedByScript = true; } };
        windows.push(value); return value;
    }
    runProductionScript(source, { Script, Tablet, Messages, Controller,
        HMD: { active: false }, Settings: {
            getValue(key, fallback) { return values.has(key) ? values.get(key) : fallback; },
            setValue(key, value) { values.set(key, value); }
        }, MyAvatar: { position: { x: 0, y: 0, z: 0 }, sessionDisplayName: "Local" },
        AvatarManager: { getPalData() { return { data: [] }; }, avatarAddedEvent: new FakeSignal() },
        Users: { avatarDisconnected: new FakeSignal() }, Vec3: { distance(a, b) { return Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z); } },
        OverlayWindow: function() { return window(); }, Desktop: { createWindow: window, PresentationMode: { NATIVE: 1, VIRTUAL: 2 } },
        console: { log() {} }
    });
    return { Script, Messages, tablet, values, Controller, windows, open() {
        tablet.buttons[0].click(); tablet.fromQml.emit({ type: "initialized" });
    }, receive(packet) { Messages.injectMessage("chat", JSON.stringify(packet)); } };
}
const packet = { action: "send_chat_message", message: "hello", displayName: "Peer", channel: "domain" };

test("normal mobile CHAT opens the actual tablet QML and exchanges real chat packets", () => {
    const s = start();
    assert.equal(s.windows.length, 0);
    s.open();
    assert.equal(s.tablet.navigation[0].type, "qml");
    assert.equal(s.tablet.qmlMessages[0].tabletMode, true);
    s.tablet.fromQml.emit({ type: "send_message", message: "from touch", channel: "domain" });
    const sent = s.Messages.sent.filter(p => p.channel === "chat");
    assert.equal(JSON.parse(sent[0].message).message, "from touch");
    assert.equal(s.values.get("ArmoredChat-Messages").length, 1);
    assert.equal(s.tablet.qmlMessages.at(-1).message, "from touch");
    assert.equal(s.Messages.sent.filter(p => p.channel === "Chat").length, 1);
});
test("closed apps keep bounded history and replay it exactly once on reopen", () => {
    const s = start({ config: { maximum_messages: 2 } });
    s.open(); s.tablet.gotoHomeScreen();
    const count = s.tablet.qmlMessages.length;
    for (const message of ["first", "second", "third"]) s.receive({ ...packet, message });
    assert.equal(s.tablet.qmlMessages.length, count);
    assert.deepEqual(Array.from(s.values.get("ArmoredChat-Messages"), p => p.message), ["second", "third"]);
    s.open();
    const replay = s.tablet.qmlMessages.slice(count);
    assert.equal(replay.filter(p => p.type === "clear_messages").length, 1);
    assert.deepEqual(replay.filter(p => p.type === "show_message").map(p => p.message), ["second", "third"]);
});
test("only active chat sends; malformed and distant messages do not break reception", () => {
    const s = start();
    s.tablet.fromQml.emit({ type: "send_message", message: "foreign", channel: "domain" });
    assert.equal(s.Messages.sent.length, 0);
    s.open();
    s.Messages.injectMessage("chat", "not json"); s.Messages.injectMessage("chat", "null");
    s.receive({ ...packet, channel: "local", position: { x: 30, y: 0, z: 0 } });
    s.receive({ ...packet, channel: "local" }); s.receive(packet);
    assert.equal(s.values.get("ArmoredChat-Messages").length, 1);
    s.tablet.fromQml.emit({ type: "send_message", message: "wrong", channel: "arbitrary" });
    s.tablet.fromQml.emit({ type: "setting_change", setting: "external_window", value: true });
    assert.equal(s.Messages.sent.filter(p => p.channel === "chat").length, 0);
    assert.equal(s.values.get("ArmoredChat-Config").external_window, undefined);
});
test("legacy incoming chat, local distance and history clearing work", () => {
    const s = start(); s.open();
    s.receive({ type: "TransmitChatMessage", channel: "Local", displayName: "Older peer", message: "near",
        position: { x: 2, y: 0, z: 0 } });
    assert.equal(s.tablet.qmlMessages.at(-1).message, "near");
    s.tablet.fromQml.emit({ type: "action", action: "erase_history" });
    assert.equal(s.values.get("ArmoredChat-Messages"), null);
    assert.equal(s.tablet.qmlMessages.at(-1).type, "clear_messages");
});
test("typing and signal ownership end on hide, close and script shutdown", () => {
    const s = start(); s.open();
    s.tablet.fromQml.emit({ type: "action", action: "start_typing" });
    s.tablet.tabletShown = false; s.tablet.tabletShownChanged.emit();
    assert.equal(JSON.parse(s.Messages.sent.at(-1).message).action, "typing_stop");
    assert.equal(s.tablet.qmlMessages.at(-1).type, "chat.hidden");
    s.tablet.fromQml.emit({ type: "chat.close" });
    assert.equal(s.tablet.navigation.at(-1).type, "home"); s.Script.end();
    assert.equal(s.tablet.buttons.length, 0); assert.equal(s.tablet.fromQml.listenerCount, 0);
    assert.equal(s.tablet.screenChanged.listenerCount, 0); assert.equal(s.Messages.messageReceived.listenerCount, 0);
    assert.equal(s.Messages.subscriptions.size, 0); assert.equal(s.Controller.keyPressEvent.listenerCount, 0);
});
test("desktop retains external window and Enter quick-message behavior", () => {
    const s = start({ desktop: true }); assert.equal(s.windows.length, 2);
    s.tablet.buttons[0].click(); assert.equal(s.windows[1].visible, true);
    s.Controller.keyPressEvent.emit({ key: 16777220 });
    assert.equal(s.windows[0].packets.at(-1).type, "change_visibility");
    s.windows[1].fromQml.emit({ type: "setting_change", setting: "external_window", value: true });
    assert.equal(s.windows[1].presentationMode, 1); s.Script.end();
    assert.ok(s.windows.every(w => w.closedByScript));
});
