#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");
const path = require("path");

function signal() {
    const listeners = [];
    return {
        connect(callback) {
            assert(!listeners.includes(callback), "duplicate signal connection");
            listeners.push(callback);
        },
        disconnect(callback) {
            const index = listeners.indexOf(callback);
            assert(index !== -1, "disconnect of an inactive signal");
            listeners.splice(index, 1);
        },
        emit(...args) {
            listeners.slice().forEach((callback) => callback(...args));
        },
        count() { return listeners.length; }
    };
}

const tabletShownChanged = signal();
const domainChanged = signal();
const domainConnectionRefused = signal();
const scriptEnding = signal();
const messageReceived = signal();
let activeIntervals = 0;
const requests = [];
let nextTimeout = 1;
const pendingTimeouts = new Map();
let appConfig;
let ui;

function AppUi(config) {
    appConfig = config;
    ui = {
        isOpen: false,
        tablet: { tabletShown: true, tabletShownChanged },
        sent: [],
        sendMessage(message) { this.sent.push(message); },
        messagesWaiting() {},
        open() {
            if (!this.isOpen) {
                this.isOpen = true;
                config.onOpened();
            }
        },
        close() {
            if (this.isOpen) {
                this.isOpen = false;
                config.onClosed();
            }
        }
    };
    return ui;
}

const emptySignal = () => signal();
const context = {
    ANDROID_PHONE_INTERFACE: true,
    print() {},
    location: { domainID: "{}" },
    Script: {
        require(name) {
            if (name === "appUi") { return AppUi; }
            return { request(options, callback) {
                requests.push({ options, callback });
                callback(null, { status: "success", data: { users: [] } });
            } };
        },
        include() {}, resolvePath(value) { return value; },
        setInterval() { activeIntervals += 1; return activeIntervals; },
        clearInterval() { assert(activeIntervals > 0); activeIntervals -= 1; },
        setTimeout(callback) {
            const id = nextTimeout++;
            pendingTimeouts.set(id, callback);
            return id;
        },
        clearTimeout(id) { assert(pendingTimeouts.delete(id), "clear of an inactive timeout"); },
        scriptEnding
    },
    Controller: { mousePressEvent: emptySignal(), mouseMoveEvent: emptySignal() },
    Window: { domainChanged, domainConnectionRefused },
    Messages: { subscribe() {}, unsubscribe() {}, messageReceived },
    Users: {
        requestsDomainListData: false, usernameFromIDReply: emptySignal(), avatarDisconnected: emptySignal(),
        requestUsernameFromID() {}, getPersonalMuteStatus() { return false; }, getIgnoreStatus() { return false; }
    },
    AvatarList: {
        getAvatarIdentifiers() { return []; }, getPalData() { return { data: [] }; },
        avatarAddedEvent: emptySignal(), avatarRemovedEvent: emptySignal(), avatarSessionChangedEvent: emptySignal()
    },
    Account: { metaverseServerURL: "https://example.invalid", username: "" },
    MyAvatar: { sessionUUID: "{}" }, Camera: {}, Overlays: {},
    Entities: { deleteEntity() {} }, Vec3: {}, Quat: {}, HMD: { active: false },
    Settings: { getValue() { return false; }, setValue() {} },
    UserActivityLogger: {}, XMLHttpRequest: function () {}, getControllerWorldLocation() {}
};

const palPath = path.resolve(__dirname, "../../../scripts/system/pal.js");
vm.runInNewContext(fs.readFileSync(palPath, "utf8"), context, { filename: palPath });
assert(appConfig, "People AppUi was not created");

assert.doesNotThrow(() => appConfig.onMessage(null), "null QML message is ignored");
assert.doesNotThrow(() => appConfig.onMessage({}), "method-less QML message is ignored");
assert.doesNotThrow(() => appConfig.onMessage({ method: "refreshNearby" }),
    "refresh without params is ignored");
const requestsBeforeValidation = requests.length;
[null, {}, "", "bad\nname"].forEach((name) => {
    appConfig.onMessage({ method: "removeConnection", params: name });
    appConfig.onMessage({ method: "removeFriend", params: name });
    appConfig.onMessage({ method: "addFriend", params: name });
});
assert.strictEqual(requests.length, requestsBeforeValidation,
    "invalid account names produce no server requests");
appConfig.onMessage({ method: "removeConnection", params: "user/name" });
assert(requests.at(-1).options.uri.endsWith("/connections/user%2Fname"),
    "account name is encoded as one REST path segment");
assert.doesNotThrow(() => requests.at(-1).callback(null, undefined),
    "missing server response fails closed");
assert.doesNotThrow(() => messageReceived.emit("com.highfidelity.pal", "not-json", "{}"),
    "malformed local message is ignored");
assert.strictEqual(ui.isOpen, false, "malformed messages do not open People");

messageReceived.emit("com.highfidelity.pal", JSON.stringify({ method: "select", params: [] }), "{}");
assert.strictEqual(ui.isOpen, true, "valid local selection opens People");
assert.strictEqual(pendingTimeouts.size, 1, "valid selection owns one deferred delivery");
const messagesBeforeClose = ui.sent.length;
ui.close();
assert.strictEqual(pendingTimeouts.size, 0, "close cancels deferred local selection");
assert.strictEqual(ui.sent.length, messagesBeforeClose, "cancelled selection is not delivered after close");

ui.open();
assert.strictEqual(activeIntervals, 1, "open starts one update interval");
assert.strictEqual(tabletShownChanged.count(), 1, "open connects tablet visibility once");
const directoryRequest = requests.find((entry) => entry.options.uri.includes("/api/v1/users?"));
assert(directoryRequest, "open requests connection directory data");
assert.doesNotThrow(() => directoryRequest.callback(null, { status: "success", data: null }),
    "malformed successful directory payload fails closed");
appConfig.onOpened();
assert.strictEqual(activeIntervals, 1, "duplicate open is idempotent");

ui.close(); // Models Android Back returning the tablet to Home.
assert.strictEqual(activeIntervals, 0, "Back/close clears the update interval");
assert.strictEqual(tabletShownChanged.count(), 0, "Back/close releases tablet visibility");

ui.open();
assert.strictEqual(activeIntervals, 1, "People can reopen after Back");
domainChanged.emit();
assert.strictEqual(ui.isOpen, false, "domain change closes People");
assert.strictEqual(activeIntervals, 0, "domain change tears down the runtime");

ui.open();
domainConnectionRefused.emit();
assert.strictEqual(ui.isOpen, false, "connection refusal closes People");
assert.strictEqual(activeIntervals, 0, "connection refusal tears down the runtime");

ui.open();
scriptEnding.emit();
assert.strictEqual(activeIntervals, 0, "shutdown clears the update interval");
assert.strictEqual(domainChanged.count(), 0, "shutdown releases domain signals");
assert.strictEqual(domainConnectionRefused.count(), 0, "shutdown releases refusal signals");

console.log("People lifecycle mock checks passed.");
