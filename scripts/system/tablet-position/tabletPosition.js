"use strict";

/* global Script, Tablet, Settings, Messages, MyAvatar */

(function () {
    var CHANNEL = "Pico-Tablet-Position";
    var QML_URL = Script.resolvePath("TabletPosition.qml");
    var sanitizeSettings = Script.require(
        Script.resolvePath("../libraries/picoTabletSettings.js"));
    var tablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
    var active = false;
    var button = tablet.addButton({
        icon: "icons/tablet-icons/menu-i.svg",
        activeIcon: "icons/tablet-icons/menu-a.svg",
        text: "POSITION",
        isActive: false
    });

    function currentValues() {
        var values = sanitizeSettings(
            Settings.getValue("picoTabletForwardOffset", 1.25),
            Settings.getValue("picoTabletUpOffset", -0.52),
            Settings.getValue("picoTabletTiltDegrees", -18)
        );
        return {
            type: "values",
            forward: values.forward,
            up: values.up,
            tilt: values.tilt
        };
    }

    function sendValues() {
        tablet.sendToQml(currentValues());
    }

    function onClicked() {
        if (active) {
            tablet.gotoHomeScreen();
        } else {
            tablet.loadQMLSource(QML_URL);
            Script.setTimeout(sendValues, 100);
        }
    }

    function onScreenChanged(type, url) {
        active = url === QML_URL;
        button.editProperties({ isActive: active });
        if (active) {
            sendValues();
        }
    }

    function onFromQml(message) {
        if (!active || !message || message.type !== "applyTabletPosition") {
            return;
        }
        Messages.sendLocalMessage(CHANNEL, JSON.stringify({
            method: "apply",
            forward: Number(message.forward),
            up: Number(message.up),
            tilt: Number(message.tilt)
        }));
    }

    button.clicked.connect(onClicked);
    tablet.screenChanged.connect(onScreenChanged);
    tablet.fromQml.connect(onFromQml);

    Script.scriptEnding.connect(function () {
        button.clicked.disconnect(onClicked);
        tablet.screenChanged.disconnect(onScreenChanged);
        tablet.fromQml.disconnect(onFromQml);
        tablet.removeButton(button);
    });
}());
