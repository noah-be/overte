"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { createTabletApi } = require("../support");

test("tablet API preserves proxy identity and button lifecycle", () => {
    const Tablet = createTabletApi();
    const tablet = Tablet.getTablet("system");
    assert.equal(Tablet.getTablet("system"), tablet);
    assert.notEqual(Tablet.getTablet("other"), tablet);

    const button = tablet.addButton({ text: "PLACES", sortOrder: 2 });
    let clicks = 0;
    button.clicked.connect(() => clicks++);
    button.editProperties({ isActive: true });
    button.click();
    tablet.removeButton(button);

    assert.equal(clicks, 1);
    assert.equal(button.properties.isActive, true);
    assert.deepEqual(tablet.buttons, []);
    assert.deepEqual(tablet.removedButtons, [button]);
});

test("tablet records navigation, QML messages, and Android presentation", () => {
    const tablet = createTabletApi().getTablet("system");
    const screens = [];
    tablet.screenChanged.connect((type, source) => screens.push([type, source]));

    tablet.loadQMLSource("Example.qml");
    tablet.gotoWebScreen("https://example.test", "inject.js");
    tablet.sendToQml({ ready: true });
    tablet.showAndroidTablet(1080, 1920);
    tablet.resizeAndroidTablet(1920, 1080);
    tablet.hideAndroidTablet();

    assert.deepEqual(screens, [["QML", "Example.qml"], ["Web", "https://example.test"]]);
    assert.deepEqual(tablet.qmlMessages, [{ ready: true }]);
    assert.deepEqual(tablet.presentationCalls, [
        { action: "show", width: 1080, height: 1920 },
        { action: "resize", width: 1920, height: 1080 },
        { action: "hide" }
    ]);
});
