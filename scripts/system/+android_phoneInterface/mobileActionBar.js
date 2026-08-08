"use strict";

// A small, screen-space control surface for the phone client.  It deliberately
// uses Interface's QML dialogs instead of the legacy Android Java activities.
/* globals Audio, Camera, Controller, DialogsManager, Menu, print, QmlFragment, Script, Window */

(function () {
    var navigationBar;
    var audioBar;
    var gotoButton;
    var loginButton;
    var cameraButton;
    var microphoneButton;
    var currentButtonStyle;

    var BASE_BUTTON_STYLE = {
        bgOpacity: 0.22,
        hoverBgOpacity: 0.45,
        activeBgOpacity: 0.45,
        activeHoverBgOpacity: 0.6,
        bgColor: "#20252b",
        hoverBgColor: "#2f788e",
        activeBgColor: "#b74646",
        activeHoverBgColor: "#d45b5b"
    };

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    // Window dimensions use Qt logical pixels on Android. Scaling from the short
    // edge keeps controls usable on both compact landscape screens and large,
    // high-density phones without relying on a device-specific DPI value.
    function calculateLayout(width, height) {
        var shortEdge = Math.min(width, height);
        var buttonSize = clamp(Math.round(shortEdge * 0.16), 72, 180);
        var edgeMargin = clamp(Math.round(shortEdge * 0.025), 12, 32);
        var flowPadding = 4;
        var flowSpacing = 10;

        return {
            buttonStyle: {
                width: buttonSize,
                height: buttonSize,
                iconSize: Math.round(buttonSize * 0.52),
                textSize: clamp(Math.round(buttonSize * 0.18), 16, 30),
                bottomMargin: clamp(Math.round(buttonSize * 0.06), 5, 11)
            },
            navigationPosition: { x: edgeMargin, y: edgeMargin },
            navigationSize: {
                x: buttonSize + 2 * flowPadding,
                y: 3 * buttonSize + 2 * flowSpacing + 2 * flowPadding
            },
            audioPosition: {
                x: Math.max(edgeMargin, width - edgeMargin - buttonSize - 2 * flowPadding),
                y: edgeMargin
            },
            audioSize: { x: buttonSize + 2 * flowPadding, y: buttonSize + 2 * flowPadding }
        };
    }

    function applyButtonStyle(button, style) {
        var key;
        if (!button) {
            return;
        }
        for (key in style) {
            if (style.hasOwnProperty(key)) {
                try {
                    button[key] = style[key];
                } catch (error) {
                    // The QML button may have been destroyed during a geometry update.
                    return;
                }
            }
        }
    }

    function createFragment(qml) {
        try {
            return new QmlFragment({ qml: qml });
        } catch (error) {
            print("[mobileActionBar.js] Could not create " + qml + ": " + error);
            return null;
        }
    }

    function addButton(bar, properties) {
        if (!bar || typeof bar.addButton !== "function") {
            return null;
        }
        try {
            return bar.addButton(properties) || null;
        } catch (error) {
            print("[mobileActionBar.js] Could not add button: " + error);
            return null;
        }
    }

    function connectSignal(object, signalName, handler) {
        if (object && object[signalName] && typeof object[signalName].connect === "function") {
            try {
                object[signalName].connect(handler);
            } catch (error) {
                print("[mobileActionBar.js] Could not connect " + signalName + ": " + error);
            }
        }
    }

    function disconnectSignal(object, signalName, handler) {
        if (object && object[signalName] && typeof object[signalName].disconnect === "function") {
            try {
                object[signalName].disconnect(handler);
            } catch (error) {
                // The QML object may already have been destroyed during shutdown.
            }
        }
    }

    function closeFragment(fragment) {
        if (fragment && typeof fragment.close === "function") {
            try {
                fragment.close();
            } catch (error) {
                // The fragment may already have been closed by QML teardown.
            }
        }
    }

    function updateLayout() {
        var width = Window.innerWidth;
        var height = Window.innerHeight;
        var layout;

        if (width <= 0 || height <= 0) {
            return;
        }

        layout = calculateLayout(width, height);
        currentButtonStyle = layout.buttonStyle;
        if (navigationBar) {
            navigationBar.setPosition(layout.navigationPosition.x, layout.navigationPosition.y);
            navigationBar.setSize(layout.navigationSize.x, layout.navigationSize.y);
        }
        if (audioBar) {
            audioBar.setPosition(layout.audioPosition.x, layout.audioPosition.y);
            audioBar.setSize(layout.audioSize.x, layout.audioSize.y);
        }
        applyButtonStyle(gotoButton, currentButtonStyle);
        applyButtonStyle(loginButton, currentButtonStyle);
        applyButtonStyle(cameraButton, currentButtonStyle);
        applyButtonStyle(microphoneButton, currentButtonStyle);
    }

    function buttonProperties(properties) {
        var result = {};
        var key;
        for (key in BASE_BUTTON_STYLE) {
            if (BASE_BUTTON_STYLE.hasOwnProperty(key)) {
                result[key] = BASE_BUTTON_STYLE[key];
            }
        }
        for (key in currentButtonStyle) {
            if (currentButtonStyle.hasOwnProperty(key)) {
                result[key] = currentButtonStyle[key];
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

    function isFirstPersonMode(mode) {
        return mode === "first person" || mode === "first person look at";
    }

    function updateCameraButton(mode) {
        var firstPerson = isFirstPersonMode(mode || Camera.mode);
        if (cameraButton) {
            cameraButton.editProperties({
                isActive: !firstPerson,
                text: firstPerson ? "1ST" : "3RD"
            });
        }
    }

    function toggleCameraMode() {
        // Use the native menu actions even though the phone menu bar is hidden.
        // They update camera mode and boom length atomically; assigning
        // Camera.mode directly can leave a first-person camera with a
        // third-person boom and trigger a recursive mode correction.
        Menu.triggerOption(isFirstPersonMode(Camera.mode) ? "Third Person" : "First Person");
    }

    currentButtonStyle = calculateLayout(Math.max(Window.innerWidth, 1), Math.max(Window.innerHeight, 1)).buttonStyle;

    navigationBar = createFragment("hifi/ActionBar.qml");
    audioBar = createFragment("hifi/AudioBar.qml");

    gotoButton = addButton(navigationBar, buttonProperties({
        icon: "icons/tablet-icons/goto-i.svg",
        activeIcon: "icons/tablet-icons/goto-a.svg",
        text: "GO TO"
    }));
    loginButton = addButton(navigationBar, buttonProperties({
        icon: "images/login.svg",
        activeIcon: "images/login.svg",
        text: "LOGIN"
    }));
    cameraButton = addButton(navigationBar, buttonProperties({
        icon: "icons/myview-i.svg",
        activeIcon: "icons/myview-a.svg",
        text: "1ST"
    }));
    microphoneButton = addButton(audioBar, buttonProperties({
        icon: "icons/tablet-icons/mic-unmute-i.svg",
        activeIcon: "icons/tablet-icons/mic-mute-a.svg",
        text: Audio.muted ? "UNMUTE" : "MUTE",
        isActive: Audio.muted,
        bindToAudioMute: true
    }));

    connectSignal(gotoButton, "clicked", showAddressBar);
    connectSignal(gotoButton, "entered", hapticFeedback);
    connectSignal(loginButton, "clicked", showLoginDialog);
    connectSignal(loginButton, "entered", hapticFeedback);
    connectSignal(cameraButton, "clicked", toggleCameraMode);
    connectSignal(cameraButton, "entered", hapticFeedback);
    connectSignal(microphoneButton, "clicked", toggleMicrophone);
    connectSignal(microphoneButton, "entered", hapticFeedback);
    Camera.modeUpdated.connect(updateCameraButton);
    updateCameraButton(Camera.mode);
    Window.geometryChanged.connect(updateLayout);
    // QML fragments also perform their initial placement in Component.onCompleted;
    // defer once so the phone-specific adaptive placement wins deterministically.
    Script.setTimeout(updateLayout, 0);

    Script.scriptEnding.connect(function () {
        Window.geometryChanged.disconnect(updateLayout);
        disconnectSignal(gotoButton, "clicked", showAddressBar);
        disconnectSignal(gotoButton, "entered", hapticFeedback);
        disconnectSignal(loginButton, "clicked", showLoginDialog);
        disconnectSignal(loginButton, "entered", hapticFeedback);
        disconnectSignal(cameraButton, "clicked", toggleCameraMode);
        disconnectSignal(cameraButton, "entered", hapticFeedback);
        disconnectSignal(microphoneButton, "clicked", toggleMicrophone);
        disconnectSignal(microphoneButton, "entered", hapticFeedback);
        Camera.modeUpdated.disconnect(updateCameraButton);
        closeFragment(navigationBar);
        closeFragment(audioBar);
    });
}());
