"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");
const {
    FakeSignal, createMessagesApi, createScriptApi, createTabletApi, runProductionScript
} = require("../support");

const source = path.resolve(__dirname, "../../../../scripts/system/places/places.js");

function createXhrFactory(syncResponse) {
    const requests = [];
    class FakeXMLHttpRequest {
        constructor() {
            this.readyState = 0;
            this.status = 0;
            this.responseText = "";
            this.headers = {};
            this.aborted = false;
            requests.push(this);
        }
        open(method, url, async) {
            this.method = method;
            this.url = url;
            this.async = async;
        }
        setRequestHeader(name, value) { this.headers[name] = value; }
        send(body) {
            this.body = body;
            if (this.async === false && syncResponse) {
                const response = syncResponse(this.url);
                if (response instanceof Error) throw response;
                this.status = response.status;
                this.responseText = typeof response.payload === "string" ? response.payload : JSON.stringify(response.payload);
            }
        }
        abort() { this.aborted = true; }
        respond(status, payload) {
            this.status = status;
            this.responseText = typeof payload === "string" ? payload : JSON.stringify(payload);
            this.readyState = 4;
            this.onreadystatechange();
        }
        fail(kind = "error") { this[kind === "timeout" ? "ontimeout" : "onerror"](); }
    }
    return { FakeXMLHttpRequest, requests };
}

function startPlaces(options = {}) {
    const Script = createScriptApi();
    Script.resolvePath = () => "/packaged/places/places.js";
    Script.require = () => options.federation ?? [{ node: "https://meta.test" }];
    const Tablet = createTabletApi();
    const tablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
    const Messages = createMessagesApi();
    const xhr = createXhrFactory(options.syncResponse);
    const entityAdds = [];
    const entityDeletes = [];
    let nextEntity = 1;
    const navigation = { back: 0, forward: 0, lookups: [] };
    const location = {
        href: options.href ?? "hifi://current", domainID: options.domainID ?? "{different-domain}", hostChanged: new FakeSignal(),
        goBack() { navigation.back++; }, goForward() { navigation.forward++; },
        handleLookupString(value) { navigation.lookups.push(value); }
    };
    const bookmarkCalls = { added: [], removed: [], homes: [] };
    const settingValues = {
        placesAppMetaverseToFetch: options.metaversesToFetch ?? [],
        placesAppPinnedMetaverse: options.pinnedMetaverses ?? [],
        placesAppMaturityFilter: options.maturityFilter ?? ["everyone"]
    };
    const settingWrites = [];
    const announcements = [];
    const clipboard = [];
    let clock = 1_000;
    class AdvancingDate extends Date {
        constructor() { super(clock); clock += 1_000; }
    }
    const globals = {
        ANDROID_PHONE_INTERFACE: options.androidPhone ?? true,
        Date: AdvancingDate,
        AccountServices: { metaverseServerURL: "https://meta.test" },
        AvatarList: {
            getAvatarIdentifiers: () => options.avatarIds ?? [],
            getAvatar: (id) => ({ position: (options.avatarPositions ?? {})[id] ?? { x: 0, y: 0, z: 0 } })
        },
        Entities: {
            addEntity(properties) { entityAdds.push(properties); return `portal-${nextEntity++}`; },
            deleteEntity(id) { entityDeletes.push(id); }
        },
        LocationBookmarks: {
            getBookmarks: () => options.bookmarks ?? ({ Home: "hifi://home" }),
            addBookmark(...args) { bookmarkCalls.added.push(args); },
            removeBookmark(...args) { bookmarkCalls.removed.push(args); },
            getHomeLocationAddress: () => options.homeAddress ?? "",
            setHomeLocationToAddress(...args) { bookmarkCalls.homes.push(args); }
        },
        Messages,
        MyAvatar: {
            feetPosition: { x: 0, y: 0, z: 0 }, orientation: {}, position: { x: 0, y: 0, z: 0 },
            userHeight: 1.8, scale: 1
        },
        PlatformInfo: { has3DHTML: () => options.has3DHTML ?? false },
        Script,
        Settings: {
            getValue: (key, fallback) => Object.hasOwn(settingValues, key) ? settingValues[key] : fallback,
            setValue(key, value) { settingWrites.push([key, value]); settingValues[key] = value; }
        },
        Tablet,
        Vec3: {
            distance: (a, b) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z),
            multiplyQbyV: (_q, v) => v,
            sum: (a, b) => ({ x: a.x + b.x, y: a.y + b.y, z: a.z + b.z })
        },
        Window: {
            location: "unchanged", protocolSignature: () => options.protocol ?? "proto-1",
            copyToClipboard(value) { clipboard.push(value); },
            displayAnnouncement(value) { announcements.push(value); }
        },
        XMLHttpRequest: xhr.FakeXMLHttpRequest,
        location
    };
    runProductionScript(source, globals);
    const button = tablet.buttons.find((candidate) => candidate.properties.text === "PLACES");
    button.click();
    if (options.has3DHTML) {
        tablet.webEventReceived.emit(JSON.stringify({ channel: "com.overte.places", action: "READY_FOR_CONTENT" }));
    } else {
        tablet.fromQml.emit({ channel: "com.overte.places", action: "READY_FOR_CONTENT" });
    }
    return {
        Script, Messages, Window: globals.Window, announcements, bookmarkCalls, button, clipboard,
        entityAdds, entityDeletes, location, navigation, settingValues, settingWrites, tablet, xhr
    };
}

function directoryPlace(overrides = {}) {
    return {
        id: "place-1", name: "Overte Hub", description: "Welcome", thumbnail: "https://img.test/a.png",
        maturity: "everyone", address: "hifi://hub", visibility: "open", path: "/0,0,0",
        tags: [], managers: [],
        domain: { id: "domain", name: "Hub", protocol_version: "proto-1", num_users: 2, capacity: 10 },
        ...overrides
    };
}

test("production Places delivers a successful asynchronous directory response", () => {
    const { tablet, xhr } = startPlaces();
    assert.equal(xhr.requests.length, 1);
    assert.equal(xhr.requests[0].async, true);
    assert.match(xhr.requests[0].url, /^https:\/\/meta[.]test\/api\/v1\/places/);

    xhr.requests[0].respond(200, { data: { places: [directoryPlace()] } });

    const result = tablet.qmlMessages.find((message) => message.action === "PLACE_DATA");
    assert.ok(result);
    assert.equal(result.data[0].name, "Overte Hub");
    assert.equal(result.data[0].address, "hifi://hub");
    assert.equal(result.metaverseServers[0].error, false);
    assert.ok(tablet.qmlMessages.some((message) => message.action === "BOOKMARKS_DATA"));
});

test("production Places completes safely for HTTP, transport, and malformed payload errors", () => {
    for (const finish of [
        (request) => request.respond(503, "unavailable"),
        (request) => request.fail(),
        (request) => request.fail("timeout"),
        (request) => request.respond(200, "{bad json"),
        (request) => request.respond(200, { data: { places: "not-an-array" } })
    ]) {
        const { tablet, xhr } = startPlaces();
        finish(xhr.requests[0]);
        const result = tablet.qmlMessages.find((message) => message.action === "PLACE_DATA");
        assert.ok(result, "failure still completes the directory flow");
        assert.equal(result.metaverseServers[0].error, true);
        assert.equal(result.data.some((place) => place.name === "Overte Hub"), false);
    }
});

test("production Places ignores stale response callbacks and navigation after shutdown", () => {
    const { Script, Window, tablet, xhr } = startPlaces();
    const request = xhr.requests[0];
    const before = tablet.qmlMessages.length;

    Script.end();
    assert.equal(request.aborted, true);
    request.respond(200, { data: { places: [directoryPlace()] } });
    tablet.fromQml.emit({ channel: "com.overte.places", action: "TELEPORT", address: "hifi://late" });

    assert.equal(tablet.qmlMessages.length, before);
    assert.equal(tablet.qmlMessages.some((message) => message.action === "PLACE_DATA"), false);
    assert.equal(Window.location, "unchanged");
    assert.equal(tablet.fromQml.listenerCount, 0);
});

test("production Places rejects malformed portal messages and tears down valid portals", () => {
    const { Script, Messages, entityAdds, entityDeletes, tablet } = startPlaces();
    for (const payload of [
        "not-json", "null", "[]",
        JSON.stringify({ action: "REZ_PORTAL", position: { x: NaN, y: 0, z: 0 }, url: "hifi://ok" }),
        JSON.stringify({ action: "REZ_PORTAL", position: { x: 1, y: 0, z: 0 }, url: "bad\nurl" })
    ]) {
        Messages.injectMessage("com.overte.places.portalRezzer", payload, "peer");
    }
    assert.equal(entityAdds.length, 0);

    Messages.injectMessage("com.overte.places.portalRezzer", JSON.stringify({
        action: "REZ_PORTAL", position: { x: 1, y: 0, z: 0 },
        url: "hifi://safe", name: "Safe", placeID: "safe-id"
    }), "peer");
    assert.equal(entityAdds.length, 1);
    assert.equal(Script.timers.size, 1);

    Script.end();
    assert.equal(Script.timers.size, 0);
    assert.deepEqual(entityDeletes, ["portal-1"]);
    assert.equal(Messages.subscriptions.size, 0);
    assert.equal(Messages.messageReceived.listenerCount, 0);
    assert.equal(tablet.screenChanged.listenerCount, 0);
});

test("production Places fetches selected federated and pinned metaverses sequentially", () => {
    const harness = startPlaces({
        federation: [{ node: "https://other.test" }, { node: "https://meta.test" }],
        pinnedMetaverses: ["https://other.test", "https://external.test"],
        metaversesToFetch: ["https://other.test", "https://external.test"]
    });
    assert.equal(harness.xhr.requests.length, 1);
    assert.match(harness.xhr.requests[0].url, /^https:\/\/meta[.]test/);
    harness.xhr.requests[0].respond(200, { data: { places: [directoryPlace({ id: "local", name: "Local" })] } });
    assert.equal(harness.xhr.requests.length, 2);
    assert.match(harness.xhr.requests[1].url, /^https:\/\/other[.]test/);
    harness.xhr.requests[1].respond(200, { data: { places: [directoryPlace({ id: "other", name: "Other" })] } });
    assert.equal(harness.xhr.requests.length, 3);
    assert.match(harness.xhr.requests[2].url, /^https:\/\/external[.]test/);
    harness.xhr.requests[2].respond(503, "offline");

    const result = harness.tablet.qmlMessages.findLast((message) => message.action === "PLACE_DATA");
    assert.deepEqual(Array.from(result.data.filter((place) => place.id), (place) => place.name), ["Local", "Other"]);
    assert.equal(result.metaverseServers.length, 3);
    assert.equal(result.metaverseServers.find((server) => server.url === "https://external.test").error, true);
});

test("production Places aborts an older directory generation when content is refreshed", () => {
    const harness = startPlaces();
    const stale = harness.xhr.requests[0];
    harness.tablet.fromQml.emit({ channel: "com.overte.places", action: "READY_FOR_CONTENT" });
    assert.equal(stale.aborted, true);
    assert.equal(harness.xhr.requests.length, 2);
    stale.respond(200, { data: { places: [directoryPlace({ name: "Stale" })] } });
    harness.xhr.requests[1].respond(200, { data: { places: [directoryPlace({ name: "Fresh" })] } });
    const results = harness.tablet.qmlMessages.filter((message) => message.action === "PLACE_DATA");
    assert.equal(results.length, 1);
    assert.equal(results[0].data[0].name, "Fresh");
});

test("production Places handles malformed entries, protocol filtering, capacity, and local attendance", () => {
    const harness = startPlaces({
        domainID: "{domain}", avatarIds: ["near", "far"],
        avatarPositions: { near: { x: 1, y: 0, z: 0 }, far: { x: 99, y: 0, z: 0 } }
    });
    harness.xhr.requests[0].respond(200, { data: { places: [
        null,
        { id: "missing-domain" },
        ...Array.from({ length: 6 }, (_, index) => directoryPlace({ id: `old-${index}`, name: "Old", domain: { ...directoryPlace().domain, protocol_version: "old" } })),
        directoryPlace({ id: "full", name: "Full", thumbnail: "", path: "/0,0,0", tags: ["a", "b"], managers: ["m"], domain: { ...directoryPlace().domain, num_users: 10, capacity: 10 } }),
        directoryPlace({ id: "empty", name: "Empty", path: "/100,0,0", description: "", thumbnail: "", tags: undefined, managers: [] , domain: { ...directoryPlace().domain, num_users: 0 } })
    ] } });
    const result = harness.tablet.qmlMessages.find((message) => message.action === "PLACE_DATA");
    const full = result.data.find((place) => place.id === "full");
    const empty = result.data.find((place) => place.id === "empty");
    assert.equal(full.domainAccessStatus, "FULL");
    assert.equal(full.place_attendance, 1);
    assert.equal(full.tags, "a, b.");
    assert.equal(empty.domainAccessStatus, "NOBODY");
    assert.equal(empty.place_attendance, 1);
    assert.match(result.warning, /places are not listed/);
});

test("production Places implements navigation, bookmark, home, copy and preference actions", () => {
    const harness = startPlaces({ homeAddress: "hifi://saved-home" });
    const emit = (action, details = {}) => harness.tablet.fromQml.emit({ channel: "com.overte.places", action, ...details });
    emit("TELEPORT", { address: "hifi://destination" });
    emit("GET_BOOKMARKS");
    emit("DELETE_BOOKMARK", { name: "Old" });
    emit("ADD_BOOKMARK", { name: "New" });
    emit("RENAME_BOOKMARK", { originalName: "Before", name: "After", url: "hifi://after" });
    emit("SET_HOME");
    emit("COPY_URL", { address: "hifi://copy" });
    emit("GO_HOME");
    emit("GO_BACK");
    emit("GO_FORWARD");
    emit("PIN_META", { metaverseIndex: 0, value: true });
    emit("FETCH_META", { metaverseIndex: 0, value: true });
    emit("ADD_MS", { metaverseUrl: "https://added.test" });
    emit("SET_MATURITY_FILTER", { filter: ["teen"] });

    assert.equal(harness.Window.location, "hifi://destination");
    assert.deepEqual(harness.bookmarkCalls.removed, [["Old"], ["Before"]]);
    assert.deepEqual(harness.bookmarkCalls.added, [["New", "hifi://current"], ["After", "hifi://after"]]);
    assert.deepEqual(harness.bookmarkCalls.homes, [["hifi://current"]]);
    assert.deepEqual(harness.clipboard, ["hifi://copy"]);
    assert.deepEqual(harness.navigation, { back: 1, forward: 1, lookups: ["hifi://saved-home"] });
    assert.equal(harness.settingValues.placesAppMaturityFilter[0], "teen");
    assert.ok(harness.settingWrites.some(([key]) => key === "placesAppPinnedMetaverse"));
    assert.ok(harness.settingWrites.some(([key]) => key === "placesAppMetaverseToFetch"));
});

test("production Places refreshes UI on host changes and rejects invalid UI addresses", () => {
    const harness = startPlaces();
    const initial = harness.tablet.qmlMessages.length;
    harness.tablet.fromQml.emit({ channel: "com.overte.places", action: "TELEPORT", address: "bad\naddress" });
    harness.tablet.fromQml.emit({ channel: "com.overte.places", action: "REQUEST_PORTAL", address: "" });
    assert.equal(harness.Window.location, "unchanged");
    assert.equal(harness.Messages.sent.length, 0);
    harness.location.hostChanged.emit("new-host");
    assert.ok(harness.tablet.qmlMessages.length >= initial + 2);
    assert.equal(harness.xhr.requests.length, 2);
    harness.xhr.requests[1].respond(200, { data: { places: [] } });
    assert.ok(harness.tablet.qmlMessages.length >= initial + 4);
});

test("production Places enforces portal distance and count limits and expires portals", () => {
    const harness = startPlaces();
    const rez = (x, id) => harness.Messages.injectMessage("com.overte.places.portalRezzer", JSON.stringify({
        action: "REZ_PORTAL", position: { x, y: 0, z: 0 }, url: `hifi://${id}`, name: id, placeID: id
    }), "peer");
    rez(101, "too-far");
    assert.equal(harness.entityAdds.length, 0);
    for (let index = 0; index < 17; index++) rez(1, `p${index}`);
    assert.equal(harness.entityAdds.length, 15);
    const timer = [...harness.Script.timers.keys()][0];
    harness.Script.runTimer(timer);
    assert.equal(harness.entityDeletes.length, 1);
    rez(1, "replacement");
    assert.equal(harness.entityAdds.length, 16);
});

test("production Places supports the desktop web and synchronous directory path", () => {
    const harness = startPlaces({
        androidPhone: false, has3DHTML: true,
        federation: [{ node: "https://other.test" }],
        metaversesToFetch: ["https://other.test"],
        syncResponse: (url) => url.startsWith("https://meta.test")
            ? { status: 200, payload: { data: { places: [directoryPlace({ id: "desktop", name: "Desktop" })] } } }
            : { status: 500, payload: "unavailable" }
    });
    assert.equal(harness.tablet.navigation[0].type, "web");
    assert.equal(harness.tablet.scriptEvents.find((message) => message.action === "PLACE_DATA").data[0].name, "Desktop");
    assert.equal(harness.button.properties.isActive, true);
    harness.button.click();
    assert.equal(harness.tablet.navigation.at(-1).type, "home");
    assert.equal(harness.button.properties.isActive, false);
    assert.equal(harness.tablet.webEventReceived.listenerCount, 0);
});

test("production Places keeps desktop requests fail-closed for invalid JSON and thrown transports", () => {
    for (const syncResponse of [
        () => ({ status: 200, payload: "{broken" }),
        () => { throw new Error("transport"); }
    ]) {
        const harness = startPlaces({ androidPhone: false, has3DHTML: true, syncResponse });
        const result = harness.tablet.scriptEvents.find((message) => message.action === "PLACE_DATA");
        assert.ok(result);
        assert.equal(result.data.some((place) => place.id), false);
    }
});

test("production Places responds safely to malformed UI events and external screen changes", () => {
    const harness = startPlaces();
    harness.tablet.fromQml.emit(null);
    harness.tablet.fromQml.emit({ channel: "wrong", action: "TELEPORT", address: "hifi://wrong" });
    harness.tablet.fromQml.emit("not an object");
    const active = harness.xhr.requests.at(-1);
    harness.tablet.screenChanged.emit("QML", "unrelated.qml");
    assert.equal(active.aborted, true);
    assert.equal(harness.tablet.fromQml.listenerCount, 0);
    assert.equal(harness.Window.location, "unchanged");
    harness.location.hostChanged.emit("after-close");
    assert.equal(harness.xhr.requests.length, 1);
});

test("production Places falls back to the tutorial when no home is configured", () => {
    const harness = startPlaces({ homeAddress: "" });
    harness.tablet.fromQml.emit({ channel: "com.overte.places", action: "GO_HOME" });
    assert.equal(harness.Window.location, "file:///~/serverless/tutorial.json");
});

test("production Places sends validated portal requests and ignores duplicate request callbacks", () => {
    const harness = startPlaces({ federation: [{ node: "https://meta.test" }, { node: "https://not-selected.test" }] });
    harness.tablet.fromQml.emit({
        channel: "com.overte.places", action: "REQUEST_PORTAL", address: "hifi://portal", name: "Portal", placeID: "id"
    });
    assert.equal(harness.Messages.sent.length, 1);
    const sent = JSON.parse(harness.Messages.sent[0].message);
    assert.equal(sent.url, "hifi://portal");
    assert.deepEqual(sent.position, { x: 0, y: 0, z: -2 });

    const request = harness.xhr.requests[0];
    request.respond(200, { data: { places: [] } });
    const before = harness.tablet.qmlMessages.filter((message) => message.action === "PLACE_DATA").length;
    request.onerror();
    assert.equal(harness.tablet.qmlMessages.filter((message) => message.action === "PLACE_DATA").length, before);
});

test("production Places handles invalid desktop response shapes and malformed web events", () => {
    const harness = startPlaces({
        androidPhone: false, has3DHTML: true,
        syncResponse: () => ({ status: 200, payload: { data: { places: "invalid" } } })
    });
    assert.equal(harness.tablet.scriptEvents.find((message) => message.action === "PLACE_DATA").metaverseServers[0].error, true);
    harness.tablet.webEventReceived.emit("{bad json");
    harness.tablet.webEventReceived.emit("null");
    assert.equal(harness.Window.location, "unchanged");
});

test("production Places recovers deterministically across repeated backend disconnects", () => {
    const harness = startPlaces();
    harness.xhr.requests[0].fail();
    for (let generation = 1; generation <= 6; generation++) {
        harness.location.hostChanged.emit(`host-${generation}`);
        const request = harness.xhr.requests.at(-1);
        if (generation < 6) {
            generation % 2 === 0 ? request.fail("timeout") : request.respond(502, "offline");
        } else {
            request.respond(200, { data: { places: [directoryPlace({ id: "recovered", name: "Recovered" })] } });
        }
    }
    const results = harness.tablet.qmlMessages.filter((message) => message.action === "PLACE_DATA");
    assert.equal(results.length, 7);
    assert.equal(results.at(-1).data[0].name, "Recovered");
    assert.equal(harness.xhr.requests.every((request) => request.async === true), true);
});

test("production Places remains fail-closed for fixed-seed malformed JSON and UI payloads", () => {
    const harness = startPlaces();
    let state = 0x504c4143;
    const next = () => {
        state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
        return state;
    };
    const alphabet = "{}[],:\\\"\\n\\t abcdef0123456789";
    for (let caseIndex = 0; caseIndex < 512; caseIndex++) {
        const length = next() % 80;
        let payload = "";
        for (let index = 0; index < length; index++) payload += alphabet[next() % alphabet.length];
        assert.doesNotThrow(() => harness.tablet.fromQml.emit(payload));
        assert.doesNotThrow(() => harness.Messages.injectMessage(
            "com.overte.places.portalRezzer", payload, `seeded-peer-${caseIndex}`
        ));
    }
    assert.equal(harness.Window.location, "unchanged");
    assert.equal(harness.entityAdds.length, 0);
    assert.equal(harness.Messages.sent.length, 0);
});

test("production Places processes a large adversarial directory batch exactly once", () => {
    const harness = startPlaces();
    let state = 0x4f565254;
    const places = Array.from({ length: 2_000 }, (_, index) => {
        state = (Math.imul(state, 1103515245) + 12345) >>> 0;
        if ((state & 3) === 0) return null;
        if ((state & 3) === 1) return { id: `broken-${index}`, domain: null };
        return directoryPlace({ id: `generated-${index}`, name: `Generated ${index}` });
    });
    assert.doesNotThrow(() => harness.xhr.requests[0].respond(200, { data: { places } }));
    const results = harness.tablet.qmlMessages.filter((message) => message.action === "PLACE_DATA");
    assert.equal(results.length, 1);
    assert.ok(results[0].data.length > 0);
    assert.ok(results[0].data.length <= places.length);
});
