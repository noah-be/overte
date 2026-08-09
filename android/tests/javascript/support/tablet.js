"use strict";

const { FakeSignal } = require("./signal");

class FakeTabletButton {
    constructor(properties = {}) {
        this.clicked = new FakeSignal();
        this.properties = { ...properties };
    }

    editProperties(properties) {
        Object.assign(this.properties, properties);
    }

    click() {
        this.clicked.emit();
    }
}

class FakeTablet {
    constructor(id) {
        this.id = id;
        this.buttons = [];
        this.removedButtons = [];
        this.navigation = [];
        this.qmlMessages = [];
        this.presentationCalls = [];
        this.screenChanged = new FakeSignal();
        this.fromQml = new FakeSignal();
        this.webEventReceived = new FakeSignal();
        this.scriptEvents = [];
        this.tabletShownChanged = new FakeSignal();
    }

    addButton(properties) {
        const button = new FakeTabletButton(properties);
        this.buttons.push(button);
        return button;
    }

    removeButton(button) {
        const index = this.buttons.indexOf(button);
        if (index !== -1) {
            this.buttons.splice(index, 1);
        }
        this.removedButtons.push(button);
    }

    gotoHomeScreen() {
        this.#navigate("home");
    }

    gotoMenuScreen(submenu = "") {
        this.#navigate("menu", submenu);
    }

    gotoWebScreen(url, injectedJavaScriptUrl) {
        this.#navigate("web", url, injectedJavaScriptUrl);
    }

    loadQMLSource(source) {
        this.#navigate("qml", source);
    }

    pushOntoStack(source) {
        this.#navigate("stack", source);
    }

    sendToQml(message) {
        this.qmlMessages.push(message);
    }

    emitScriptEvent(message) {
        this.scriptEvents.push(message);
    }

    showAndroidTablet(width, height) {
        this.presentationCalls.push({ action: "show", width, height });
        this.tabletShownChanged.emit(true);
    }

    resizeAndroidTablet(width, height) {
        this.presentationCalls.push({ action: "resize", width, height });
    }

    hideAndroidTablet() {
        this.presentationCalls.push({ action: "hide" });
        this.tabletShownChanged.emit(false);
    }

    #navigate(type, ...args) {
        const destination = { type, args };
        this.navigation.push(destination);
        const eventTypes = { home: "Home", menu: "Menu", web: "Web", qml: "QML", stack: "QML" };
        this.screenChanged.emit(eventTypes[type] || type, args[0]);
    }
}

function createTabletApi() {
    const tablets = new Map();
    return {
        getTablet(id) {
            if (!tablets.has(id)) {
                tablets.set(id, new FakeTablet(id));
            }
            return tablets.get(id);
        },
        tablets
    };
}

module.exports = { FakeTablet, FakeTabletButton, createTabletApi };
