"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");
const { FakeSignal, createScriptApi, runProductionScript } = require("../support");

const source = path.resolve(__dirname,
    "../../../../../scripts/system/+android_phoneInterface/mobileActionBar.js");

class FakeButton {
    constructor(properties) {
        Object.assign(this, properties);
        this.clicked = new FakeSignal();
        this.entered = new FakeSignal();
    }
}

class FakeFragment {
    constructor(options) {
        if (FakeFragment.failCreation) {
            throw new Error("fragment unavailable");
        }
        this.qml = options.qml;
        this.buttons = [];
        this.positions = [];
        this.sizes = [];
        this.visible = true;
        this.closed = false;
        FakeFragment.instances.push(this);
    }

    addButton(properties) {
        if (FakeFragment.failButtons) {
            throw new Error("button unavailable");
        }
        const button = new FakeButton(properties);
        this.buttons.push(button);
        return button;
    }

    setPosition(x, y) { this.positions.push({ x, y }); }
    setSize(x, y) { this.sizes.push({ x, y }); }
    close() { this.closed = true; }
}
FakeFragment.instances = [];
FakeFragment.failCreation = false;
FakeFragment.failButtons = false;

function start({
    width = 1000,
    height = 500,
    muted = false,
    cameraMode = "first person",
    operatingSystem
} = {}) {
    FakeFragment.instances = [];
    FakeFragment.failCreation = false;
    FakeFragment.failButtons = false;
    const Script = createScriptApi();
    const Window = { innerWidth: width, innerHeight: height, geometryChanged: new FakeSignal() };
    const tablet = {
        tabletShown: false,
        tabletShownChanged: new FakeSignal(),
        shown: [],
        resized: [],
        showAndroidTablet(w, h) { this.shown.push([w, h]); },
        resizeAndroidTablet(w, h) { this.resized.push([w, h]); }
    };
    const Tablet = { getTablet() { return tablet; } };
    const controllerCalls = [];
    const Controller = {
        device: 9,
        touchBeginEvent: new FakeSignal(),
        touchEndEvent: new FakeSignal(),
        findDevice(name) { controllerCalls.push(["find", name]); return this.device; },
        triggerHapticPulseOnDevice(...args) { controllerCalls.push(["haptic", ...args]); },
        setVPadHidden(value) { controllerCalls.push(["hidden", value]); },
        captureTouchEvents() { controllerCalls.push(["capture"]); },
        releaseTouchEvents() { controllerCalls.push(["release"]); }
    };
    const Audio = { muted };
    const Camera = { mode: cameraMode };
    const MyAvatar = { cameraBoomLength: 2.25 };
    const DialogsManager = { calls: 0, showAddressBar() { this.calls += 1; } };
    const prints = [];
    const globals = {
        Audio, Camera, Controller, DialogsManager, MyAvatar, QmlFragment: FakeFragment,
        Script, Tablet, Window, print: (message) => prints.push(message)
    };
    if (operatingSystem) {
        globals.PlatformInfo = { getOperatingSystemType() { return operatingSystem; } };
    }
    runProductionScript(source, globals);
    const [navigation, audio] = FakeFragment.instances;
    return { Script, Window, tablet, Controller, controllerCalls, Audio, Camera, MyAvatar,
        DialogsManager, prints, navigation, audio };
}

test("production action bar creates adaptive controls and applies deferred geometry", () => {
    const state = start({ width: 1000, height: 500 });
    assert.equal(state.navigation.qml, "hifi/ActionBar.qml");
    assert.equal(state.audio.qml, "hifi/AudioBar.qml");
    assert.deepEqual(state.navigation.buttons.map((button) => button.text), ["GO TO", "TABLET", "VIEW"]);
    assert.equal(state.audio.buttons[0].text, "MUTE");
    assert.equal(state.navigation.buttons[0].width, 80);
    assert.equal(state.Script.timers.size, 1);

    state.Script.runTimer([...state.Script.timers.keys()][0]);
    assert.deepEqual(state.navigation.positions.at(-1), { x: 13, y: 13 });
    assert.deepEqual(state.navigation.sizes.at(-1), { x: 88, y: 268 });
    assert.deepEqual(state.audio.positions.at(-1), { x: 899, y: 13 });
});

test("buttons perform navigation, tablet, microphone and haptic actions", () => {
    const state = start();
    const [gotoButton, tabletButton] = state.navigation.buttons;
    const microphoneButton = state.audio.buttons[0];

    gotoButton.clicked.emit();
    tabletButton.clicked.emit();
    microphoneButton.clicked.emit();
    gotoButton.entered.emit();

    assert.equal(state.DialogsManager.calls, 1);
    assert.deepEqual(state.tablet.shown, [[1000, 500]]);
    assert.equal(state.Audio.muted, true);
    assert.deepEqual(state.controllerCalls.at(-1), ["haptic", 9, 0.1, 40, 0]);

    state.Controller.device = 65535;
    const before = state.controllerCalls.length;
    tabletButton.entered.emit();
    assert.equal(state.controllerCalls.length, before + 1);
    assert.deepEqual(state.controllerCalls.at(-1), ["find", "TouchscreenVirtualPad"]);
});

test("camera toggle preserves the third-person boom across both directions", () => {
    const state = start({ cameraMode: "first person look at" });
    const cameraButton = state.navigation.buttons[2];

    cameraButton.clicked.emit();
    assert.equal(state.Camera.mode, "look at");
    assert.equal(state.MyAvatar.cameraBoomLength, 1.5);

    state.MyAvatar.cameraBoomLength = 3.75;
    cameraButton.clicked.emit();
    assert.equal(state.MyAvatar.cameraBoomLength, 0.5);
    assert.equal(state.Camera.mode, "first person look at");

    cameraButton.clicked.emit();
    assert.equal(state.MyAvatar.cameraBoomLength, 3.75);
});

test("tablet visibility owns touch capture and hides both action bars", () => {
    const state = start();
    state.tablet.tabletShown = true;
    state.tablet.tabletShownChanged.emit();
    assert.equal(state.navigation.visible, false);
    assert.equal(state.audio.visible, false);
    assert.deepEqual(state.controllerCalls.slice(-2), [["hidden", true], ["capture"]]);

    state.tablet.tabletShown = false;
    state.tablet.tabletShownChanged.emit();
    assert.equal(state.navigation.visible, true);
    assert.equal(state.audio.visible, true);
    assert.deepEqual(state.controllerCalls.slice(-2), [["hidden", false], ["release"]]);
});

test("geometry changes resize the tablet and clamp small and large control layouts", () => {
    const state = start({ width: 200, height: 100 });
    state.Window.geometryChanged.emit();
    assert.equal(state.navigation.buttons[0].width, 72);
    assert.deepEqual(state.tablet.resized.at(-1), [200, 100]);

    state.Window.innerWidth = 3000;
    state.Window.innerHeight = 2000;
    state.Window.geometryChanged.emit();
    assert.equal(state.navigation.buttons[0].width, 180);
    assert.equal(state.navigation.buttons[0].textSize, 30);
});

test("iOS uses compact controls and deduplicates native touch against QML clicks", () => {
    const state = start({ width: 1366, height: 1024, operatingSystem: "IOS" });
    const gotoButton = state.navigation.buttons[0];

    assert.equal(gotoButton.width, 108);
    assert.equal(state.Controller.touchBeginEvent.listenerCount, 1);
    assert.equal(state.Controller.touchEndEvent.listenerCount, 1);

    state.Controller.touchBeginEvent.emit({ x: 40, y: 40 });
    state.Controller.touchEndEvent.emit({ x: 40, y: 40 });
    gotoButton.clicked.emit();

    assert.equal(state.DialogsManager.calls, 1);
    assert.equal(state.prints.filter((message) =>
        message.includes("OVERTE_MOBILE_ACTION_BAR action=goto")).length, 1);

    state.Script.end();
    assert.equal(state.Controller.touchBeginEvent.listenerCount, 0);
    assert.equal(state.Controller.touchEndEvent.listenerCount, 0);
});

test("shutdown cancels deferred work, disconnects every signal and closes fragments", () => {
    const state = start();
    const buttons = [...state.navigation.buttons, ...state.audio.buttons];
    const timerId = [...state.Script.timers.keys()][0];

    state.Script.end();

    assert.equal(state.Script.timers.size, 0);
    assert.deepEqual(state.Script.clearedTimers, [timerId]);
    assert.equal(state.Window.geometryChanged.listenerCount, 0);
    assert.equal(state.tablet.tabletShownChanged.listenerCount, 0);
    assert.equal(state.navigation.closed, true);
    assert.equal(state.audio.closed, true);
    for (const button of buttons) {
        assert.equal(button.clicked.listenerCount, 0);
        assert.equal(button.entered.listenerCount, 0);
    }
    assert.deepEqual(state.controllerCalls.slice(-2), [["hidden", false], ["release"]]);
});

test("zero-sized windows remain idle until valid geometry becomes available", () => {
    const state = start({ width: 0, height: 0 });
    state.Script.runTimer([...state.Script.timers.keys()][0]);
    assert.equal(state.navigation.positions.length, 0);

    state.Window.innerWidth = 640;
    state.Window.innerHeight = 360;
    state.Window.geometryChanged.emit();
    assert.equal(state.navigation.positions.length, 1);
    assert.deepEqual(state.tablet.resized.at(-1), [640, 360]);
});

test("missing QML fragments fail closed while lifecycle cleanup remains usable", () => {
    FakeFragment.instances = [];
    FakeFragment.failCreation = true;
    const Script = createScriptApi();
    const Window = { innerWidth: 640, innerHeight: 360, geometryChanged: new FakeSignal() };
    const tablet = {
        tabletShown: false,
        tabletShownChanged: new FakeSignal(),
        resizeAndroidTablet() {},
        showAndroidTablet() {}
    };
    const releases = [];
    const prints = [];
    runProductionScript(source, {
        Audio: { muted: false }, Camera: { mode: "first person" },
        Controller: {
            findDevice() { return 65535; }, setVPadHidden(value) { releases.push(value); },
            captureTouchEvents() {}, releaseTouchEvents() { releases.push("release"); }
        },
        DialogsManager: { showAddressBar() {} }, MyAvatar: { cameraBoomLength: 1.5 },
        QmlFragment: FakeFragment, Script, Tablet: { getTablet() { return tablet; } }, Window,
        print: (message) => prints.push(message)
    });

    assert.equal(prints.length, 2);
    Window.geometryChanged.emit();
    Script.end();
    assert.equal(Window.geometryChanged.listenerCount, 0);
    assert.deepEqual(releases.slice(-2), [false, "release"]);
    FakeFragment.failCreation = false;
});
