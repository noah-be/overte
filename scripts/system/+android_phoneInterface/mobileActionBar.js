"use strict";

// A small, screen-space control surface for the phone client.  It deliberately
// uses Interface's QML dialogs instead of the legacy Android Java activities.
/* globals Audio, Controller, DialogsManager, QmlFragment, Script */

(function () {
    var navigationBar = new QmlFragment({ qml: "hifi/ActionBar.qml" });
    var audioBar = new QmlFragment({ qml: "hifi/AudioBar.qml" });
    var gotoButton;
    var loginButton;
    var microphoneButton;

    var BUTTON_STYLE = {
        width: 140,
        height: 140,
        iconSize: 72,
        textSize: 25,
        bottomMargin: 8,
        bgOpacity: 0.22,
        hoverBgOpacity: 0.45,
        activeBgOpacity: 0.45,
        activeHoverBgOpacity: 0.6,
        bgColor: "#20252b",
        hoverBgColor: "#2f788e",
        activeBgColor: "#b74646",
        activeHoverBgColor: "#d45b5b"
    };

    function buttonProperties(properties) {
        var result = {};
        var key;
        for (key in BUTTON_STYLE) {
            if (BUTTON_STYLE.hasOwnProperty(key)) {
                result[key] = BUTTON_STYLE[key];
            }
        }
        for (key in properties) {
            if (properties.hasOwnProperty(key)) {
                result[key] = properties[key];
            }
        }
        return result;
    }

    function hapticFeedback() {
        var device = Controller.findDevice("TouchscreenVirtualPad");
        if (device !== 65535) {
            Controller.triggerHapticPulseOnDevice(device, 0.1, 40.0, 0);
        }
    }

    function showAddressBar() {
        DialogsManager.showAddressBar();
    }

    function showLoginDialog() {
        DialogsManager.showLoginDialog();
    }

    function toggleMicrophone() {
        Audio.muted = !Audio.muted;
    }

    function updateMicrophoneButton() {
        if (microphoneButton) {
            microphoneButton.isActive = Audio.muted;
            microphoneButton.text = Audio.muted ? "UNMUTE" : "MUTE";
        }
    }

    gotoButton = navigationBar.addButton(buttonProperties({
        icon: "icons/tablet-icons/goto-i.svg",
        activeIcon: "icons/tablet-icons/goto-a.svg",
        text: "GO TO"
    }));
    loginButton = navigationBar.addButton(buttonProperties({
        icon: "images/login.svg",
        activeIcon: "images/login.svg",
        text: "LOGIN"
    }));
    microphoneButton = audioBar.addButton(buttonProperties({
        icon: "icons/tablet-icons/mic-unmute-i.svg",
        activeIcon: "icons/tablet-icons/mic-mute-a.svg",
        text: "MUTE"
    }));

    gotoButton.clicked.connect(showAddressBar);
    gotoButton.entered.connect(hapticFeedback);
    loginButton.clicked.connect(showLoginDialog);
    loginButton.entered.connect(hapticFeedback);
    microphoneButton.clicked.connect(toggleMicrophone);
    microphoneButton.entered.connect(hapticFeedback);
    Audio.mutedChanged.connect(updateMicrophoneButton);
    updateMicrophoneButton();

    Script.scriptEnding.connect(function () {
        Audio.mutedChanged.disconnect(updateMicrophoneButton);
        gotoButton.clicked.disconnect(showAddressBar);
        gotoButton.entered.disconnect(hapticFeedback);
        loginButton.clicked.disconnect(showLoginDialog);
        loginButton.entered.disconnect(hapticFeedback);
        microphoneButton.clicked.disconnect(toggleMicrophone);
        microphoneButton.entered.disconnect(hapticFeedback);
        navigationBar.close();
        audioBar.close();
    });
}());
