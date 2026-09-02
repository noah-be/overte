"use strict";

// Registers the deliberately small first-party app set for the Android
// screen-space Tablet. Keep button properties immutable after registration:
// cross-thread writes to QML-backed button proxies are unsafe on this client.
/* globals Script, Tablet */

(function () {
    var SYSTEM_TABLET = "com.highfidelity.interface.tablet.system";
    var AUDIO_SOURCE = "hifi/audio/Audio.qml";
    var SETTINGS_SOURCE = Script.resolvePath("../settings/Settings.qml");
    var GENERAL_SETTINGS_SOURCE = "hifi/tablet/TabletGeneralPreferences.qml";
    // Settings QML is packaged first-party content, but keep its navigation
    // boundary fail-closed as well. Never turn an arbitrary QML message into a
    // local or remote component load.
    var SETTINGS_ROUTES = {
        "hifi/tablet/TabletGeneralPreferences.qml": GENERAL_SETTINGS_SOURCE,
        "hifi/dialogs/GeneralPreferencesDialog.qml": GENERAL_SETTINGS_SOURCE,
        "hifi/audio/Audio.qml": AUDIO_SOURCE,
        "hifi/dialogs/security/Security.qml": "hifi/dialogs/security/Security.qml",
        "hifi/dialogs/security/EntityScriptQMLAllowlist.qml":
            "hifi/dialogs/security/EntityScriptQMLAllowlist.qml",
        "hifi/dialogs/security/ScriptSecurity.qml":
            "hifi/dialogs/security/ScriptSecurity.qml"
    };
    var SETTINGS_CHILD_SOURCES = {
        "hifi/tablet/TabletGeneralPreferences.qml": true,
        "hifi/audio/Audio.qml": true,
        "hifi/dialogs/security/Security.qml": true
    };
    var tablet = Tablet.getTablet(SYSTEM_TABLET);
    var currentSource = "";

    function openOrReturnHome(source) {
        if (currentSource === source) {
            tablet.gotoHomeScreen();
        } else {
            tablet.loadQMLSource(source);
        }
    }

    var audioButton = tablet.addButton({
        icon: "icons/tablet-icons/mic-unmute-i.svg",
        activeIcon: "icons/tablet-icons/mic-mute-a.svg",
        text: "AUDIO",
        sortOrder: 1
    });
    var settingsButton = tablet.addButton({
        icon: Script.resolvePath("../settings/img/icon_white.png"),
        activeIcon: Script.resolvePath("../settings/img/icon_black.png"),
        text: "SETTINGS",
        semanticId: "app.settings",
        sortOrder: 2
    });
    var menuButton = tablet.addButton({
        icon: "icons/tablet-icons/menu-i.svg",
        activeIcon: "icons/tablet-icons/menu-a.svg",
        text: "MENU",
        sortOrder: 3
    });

    function openAudio() {
        openOrReturnHome(AUDIO_SOURCE);
    }

    function openSettings() {
        openOrReturnHome(SETTINGS_SOURCE);
    }

    function openMenu() {
        tablet.gotoMenuScreen();
    }

    function onScreenChanged(type, source) {
        currentSource = type === "Home" || type === "Closed" ? "" : source;
    }

    function fromQml(message) {
        if (!message || typeof message !== "object") {
            return;
        }
        if (message.type === "settings.back" &&
                Object.prototype.hasOwnProperty.call(SETTINGS_CHILD_SOURCES, currentSource)) {
            tablet.loadQMLSource(SETTINGS_SOURCE);
            return;
        }
        if (currentSource !== SETTINGS_SOURCE || message.type !== "switchApp" ||
                typeof message.appUrl !== "string" ||
                !Object.prototype.hasOwnProperty.call(SETTINGS_ROUTES, message.appUrl)) {
            return;
        }
        tablet.loadQMLSource(SETTINGS_ROUTES[message.appUrl]);
    }

    audioButton.clicked.connect(openAudio);
    settingsButton.clicked.connect(openSettings);
    menuButton.clicked.connect(openMenu);
    tablet.screenChanged.connect(onScreenChanged);
    tablet.fromQml.connect(fromQml);

    Script.scriptEnding.connect(function () {
        audioButton.clicked.disconnect(openAudio);
        settingsButton.clicked.disconnect(openSettings);
        menuButton.clicked.disconnect(openMenu);
        tablet.screenChanged.disconnect(onScreenChanged);
        tablet.fromQml.disconnect(fromQml);
        tablet.removeButton(audioButton);
        tablet.removeButton(settingsButton);
        tablet.removeButton(menuButton);
    });
}());
