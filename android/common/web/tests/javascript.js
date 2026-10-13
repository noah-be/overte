"use strict";
// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const resources = path.resolve(__dirname, "../resources");
const emitted = [];
const window = { __overteNative: { postMessage(data) { emitted.push(JSON.parse(data)); } } };
window.top = window; window.window = window;
const context = vm.createContext(window);
vm.runInContext(fs.readFileSync(path.join(resources, "transport.js"), "utf8"), context);
context.qt.webChannelTransport.send('{"type":3,"id":0}'); assert.equal(emitted.length, 0);
context.__overteTransport.authorize("9223372036854775000", "5");
assert.equal(emitted[0].grant, "9223372036854775000", "grant survives JS integer precision limits");
let inbound;
context.qt.webChannelTransport.onmessage = message => { inbound = JSON.parse(message.data); };
context.__overteTransport.receive("9223372036854775000", "4", { ignored: true }); assert.equal(inbound, undefined);
context.__overteTransport.receive("9223372036854775000", "5", { received: true }); assert.equal(inbound.received, true);
context.__overteTransport.suspend(); context.qt.webChannelTransport.send("{}"); assert.equal(emitted.length, 1);
const states = [], events = [];
class Input {
    constructor(text, type = "text") { this.value = text; this.type = type; this.selectionStart = this.selectionEnd = text.length; }
    setRangeText(text, start, end) { this.value = this.value.slice(0, start) + text + this.value.slice(end); this.selectionStart = this.selectionEnd = start + text.length; }
    setSelectionRange(start, end, direction) { this.selectionStart = start; this.selectionEnd = end; this.selectionDirection = direction; }
    getBoundingClientRect() { return { x: 1, y: 2, width: 100, height: 40 }; }
    dispatchEvent(event) { events.push(event); }
}
const editor = { HTMLInputElement: Input, HTMLTextAreaElement: class extends Input {},
    CompositionEvent: class { constructor(type, values) { Object.assign(this, { type }, values); } },
    InputEvent: class { constructor(type, values) { Object.assign(this, { type }, values); } },
    __overteTransport: { editor(state) { states.push(state); } }, document: {
        activeElement: new Input("hello world"), addEventListener() {}
    } };
editor.window = editor; editor.top = editor;
vm.runInContext(fs.readFileSync(path.join(resources, "editor.js"), "utf8"), vm.createContext(editor));
editor.__overteEditor.publish(); assert.equal(states.at(-1).text, "hello world");
editor.__overteEditor.edit({ text: "Earth", replaceStart: -5, replaceLength: 5 });
assert.equal(editor.document.activeElement.value, "hello Earth");
editor.__overteEditor.edit({ text: "x", composing: true });
editor.__overteEditor.edit({ text: "xy", composing: true });
assert.equal(editor.document.activeElement.value, "hello Earthxy");
editor.__overteEditor.edit({ text: "z", composing: false });
assert.equal(editor.document.activeElement.value, "hello Earthz", "commit replaces preedit instead of duplicating it");
editor.document.activeElement = new Input("a😀");
editor.__overteEditor.edit({ action: "backspace" }); assert.equal(editor.document.activeElement.value, "a");
editor.document.activeElement = new Input("a😀b");
editor.__overteEditor.edit({ text: "bad", replaceStart: -2, replaceLength: 1 });
assert.equal(editor.document.activeElement.value, "a😀b", "nonlocal replacement cannot split UTF-16 pair");
editor.document.activeElement = new Input("secret", "password"); editor.__overteEditor.publish();
assert.equal(states.at(-1).text, ""); assert.equal(states.at(-1).sensitive, true);
editor.document.activeElement = new Input("a".repeat(20000)); editor.__overteEditor.publish();
assert(states.at(-1).text.length <= 16384); assert.equal(states.at(-1).cursor, 8192);
editor.document.activeElement = new Input("ab😀cd");
editor.__overteEditor.edit({ action: "left" }); editor.__overteEditor.edit({ action: "left" }); editor.__overteEditor.edit({ action: "left" });
assert.equal(editor.document.activeElement.selectionStart, 2, "navigation crosses a whole UTF-16 codepoint");
editor.__overteEditor.edit({ action: "right", extend: true }); editor.__overteEditor.publish();
assert.equal(states.at(-1).cursor, 4); assert.equal(states.at(-1).anchor, 2);
editor.document.activeElement = new Input("before-after");
editor.document.activeElement.setSelectionRange(7, 7);
editor.__overteEditor.edit({ text: "XY", composing: true, cursor: 1 });
assert.equal(editor.document.activeElement.selectionStart, 8);
editor.__overteEditor.edit({ text: "C", replaceStart: -1, replaceLength: 2 });
assert.equal(editor.document.activeElement.value, "beforeCfter", "Qt replacement skips old preedit when counting surrounding characters");
assert(events.some(event => event.type === "compositionstart"));
assert(events.some(event => event.type === "compositionupdate"));
assert(events.some(event => event.type === "compositionend"));
editor.document.activeElement = new Input("left-right");
editor.document.activeElement.setSelectionRange(5, 5);
editor.__overteEditor.edit({ action: "ime", commit: "", preedit: "XYZ", replaceStart: 0, replaceLength: 0, cursor: 1 });
assert.equal(editor.document.activeElement.value, "left-XYZright");
assert.equal(editor.document.activeElement.selectionStart, 6);
editor.__overteEditor.edit({ action: "ime", commit: "Q", preedit: "", replaceStart: -2, replaceLength: 1, cursor: 0 });
assert.equal(editor.document.activeElement.value, "lefQ-right", "atomic IME removes preedit even when replacement is entirely before it");
editor.__overteEditor.edit({ action: "ime", commit: "", preedit: "ABC", replaceStart: 0, replaceLength: 0, cursor: 2 });
editor.__overteEditor.edit({ action: "ime", commit: "", preedit: "", replaceStart: 0, replaceLength: 0, cursor: 0 });
assert.equal(editor.document.activeElement.value, "lefQ-right", "composition cancellation restores the committed DOM text");
editor.__overteEditor.edit({ action: "ime", commit: "", preedit: "", replaceStart: 0, replaceLength: 0, cursor: 0, selection: { start: 0, length: 3 } });
editor.__overteEditor.publish(); assert.equal(states.at(-1).anchor, 0); assert.equal(states.at(-1).cursor, 3);
if (process.argv[2]) {
    const messages = [], client = { __overteNative: { postMessage(data) { messages.push(JSON.parse(data)); } }, console };
    client.window = client; client.top = client;
    const scope = vm.createContext(client);
    vm.runInContext(fs.readFileSync(path.join(resources, "transport.js"), "utf8"), scope);
    vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), scope);
    vm.runInContext(fs.readFileSync(path.resolve(__dirname, "../../../../interface/resources/html/createGlobalEventBridge.js"), "utf8"), scope);
    client.EventBridge.emitWebEvent("early message");
    client.__overteTransport.authorize("7", "9");
    const init = JSON.parse(messages[0].payload);
    client.__overteTransport.receive("7", "9", { type: 10, id: init.id, data: {
        eventBridge: { methods: [["emitWebEvent", 5]], signals: [["scriptEventReceived", 4]], properties: [], enums: {} }
    } });
    assert(messages.some(message => { const p = JSON.parse(message.payload); return p.type === 6 && p.args[0] === "early message"; }));
    let event; client.EventBridge.scriptEventReceived.connect(message => { event = message; });
    client.__overteTransport.receive("7", "9", { type: 1, object: "eventBridge", signal: 4, args: ["native event"] });
    assert.equal(event, "native event", "real Qt5 QWebChannel and existing global bridge interoperate");
}
console.log("PASS: transport epochs, DOM selection/composition/replacement/privacy and QWebChannel compatibility");
