"use strict";
const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");
const fs = require("node:fs");
const vm = require("node:vm");
const { resolveObjectURL } = require("node:buffer");
const { FakeSignal, createScriptApi, createTabletApi, runProductionScript } = require("../support");
const source = path.resolve(__dirname, "../../device/fixture/parity/client.js");

function start() {
    const Script = createScriptApi();
    Script.resolvePath = (name) => "http://reference.test:1234/parity/" + name;
    const Tablet = createTabletApi(), tablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
    const created = [], sent = [], deleted = [];
    const Entities = {
        webEventReceived: new FakeSignal(),
        addEntity(properties, scope) { created.push({ properties, scope }); return "owned-local-web"; },
        emitScriptEvent(id, message) { sent.push({ id, message: JSON.parse(message) }); },
        deleteEntity(id) { deleted.push(id); }
    };
    runProductionScript(source, { Script, Tablet, Entities, print() {},
        MyAvatar: { position: {x: 2, y: 0, z: 5}, orientation: {x: 0, y: 0, z: 0, w: 1} },
        Quat: {getForward() {return {x: 0, y: 0, z: -1};}},
        Vec3: {sum(a,b) {return {x:a.x+b.x,y:a.y+b.y,z:a.z+b.z};}, multiply(v,a) {return {x:v*a.x,y:v*a.y,z:v*a.z};}}
    });
    return {Script, tablet, Entities, created, sent, deleted};
}
const packet = JSON.stringify({contract: "overte-web-parity-v1", action: "echo", sequence: 3});

function startDocument() {
    const nodes = new Map(), handlers = new Map();
    const document = { getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, {style: {}, addEventListener() {}, textContent: ""});
        return nodes.get(id);
    }};
    const window = {location: new URL("http://reference.test/parity/index.html"),
        setInterval() {}, addEventListener(event, callback) { handlers.set(event, callback); }};
    vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, "../../device/fixture/parity/reference.js"), "utf8"),
        {document, window, URL, encodeURI});
    return {node: document.getElementById, handlers};
}

test("document preview uses an actual opaque blob URL and releases replaced, cleared and hidden selections", () => {
    const s = startDocument(), picker = s.node("file"), preview = s.node("filePreview");
    const image = new Blob(["test image bytes"], {type: "image/png"});
    const select = (files) => { picker.files = files; picker.onchange(); };
    try {
        select([image]);
        const first = preview.src;
        assert.match(first, /^blob:/);
        assert.equal(resolveObjectURL(first).size, image.size);
        assert.equal(preview.style.display, "block");
        select([image]);
        assert.equal(resolveObjectURL(first), undefined);
        const second = preview.src;
        select([]);
        assert.equal(resolveObjectURL(second), undefined);
        assert.equal(preview.style.display, "none");
        select([image]);
        const third = preview.src;
        s.handlers.get("pagehide")();
        assert.equal(resolveObjectURL(third), undefined);
    } finally { s.handlers.get("pagehide")(); }
});

test("non-image selections remain text diagnostics and never become document source URLs", () => {
    const s = startDocument(), picker = s.node("file"), preview = s.node("filePreview");
    picker.files = [new Blob(["<script>untrusted content</script>"], {type: "text/html"})];
    picker.onchange();
    assert.equal(preview.src, undefined);
    assert.equal(preview.style.display, "none");
    assert.match(s.node("fileStatus").textContent, /text\/html/);
    assert.equal(s.node("fileStatus").innerHTML, undefined);
});

test("reference uses the real API entry points and only one local source-owned entity", () => {
    const s = start(), properties = s.created[0].properties;
    assert.equal(s.created.length, 1);
    assert.equal(s.created[0].scope, "local");
    assert.equal(properties.type, "Web");
    assert.equal(properties.sourceUrl, "http://reference.test:1234/parity/index.html");
    assert.equal(properties.scriptURL, "http://reference.test:1234/parity/injected.js");
    assert.deepEqual({...properties.position}, {x: 2, y: 1.4, z: 2.5});
    s.tablet.buttons[0].click();
    assert.equal(s.tablet.navigation.at(-1).type, "web");
    assert.equal(s.tablet.navigation.at(-1).args[0], properties.sourceUrl);
    s.tablet.buttons[0].click();
    assert.equal(s.tablet.navigation.at(-1).type, "home");
    s.Script.end();
});

test("echo accepts only the bounded protocol and owned world entity", () => {
    const s = start();
    s.Entities.webEventReceived.emit("foreign-entity", packet);
    for (const invalid of ["null", "broken", "[]", "x".repeat(4097),
        JSON.stringify({contract:"overte-web-parity-v1",action:"echo",sequence:1.5}),
        JSON.stringify({contract:"overte-web-parity-v1",action:"other",sequence:1})]) {
        s.Entities.webEventReceived.emit("owned-local-web", invalid);
    }
    assert.equal(s.sent.length, 0);
    s.Entities.webEventReceived.emit("owned-local-web", packet);
    assert.deepEqual(s.sent[0], {id: "owned-local-web", message: {contract: "overte-web-parity-v1", action: "echo", sequence: 3, surface: "world"}});
    s.Script.end();
});

test("diagnostic does not conceal native origin enforcement by filtering tablet documents", () => {
    const s = start();
    s.tablet.gotoWebScreen("http://second-origin.test:5678/parity/index.html");
    s.tablet.webEventReceived.emit(packet);
    assert.equal(JSON.parse(s.tablet.scriptEvents.at(-1)).surface, "tablet");
    s.Script.end();
});

test("script shutdown removes only its owned surface/button and every handler", () => {
    const s = start();
    s.tablet.buttons[0].click();
    s.Script.end();
    assert.deepEqual(s.deleted, ["owned-local-web"]);
    assert.equal(s.tablet.buttons.length, 0);
    assert.equal(s.tablet.navigation.at(-1).type, "home");
    assert.equal(s.Entities.webEventReceived.listenerCount, 0);
    assert.equal(s.tablet.webEventReceived.listenerCount, 0);
    assert.equal(s.tablet.screenChanged.listenerCount, 0);
});
