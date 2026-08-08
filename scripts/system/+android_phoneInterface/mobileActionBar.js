"use strict";

// A small, screen-space control surface for the phone client.  It deliberately
// uses Interface's QML dialogs instead of the legacy Android Java activities.
/* globals Audio, Camera, Controller, DialogsManager, MyAvatar, print, QmlFragment, Script, Tablet, Window */

(function () {
    var navigationBar;
    var audioBar;
    var gotoButton;
    var tabletButton;
    var cameraButton;
    var microphoneButton;
    var systemTablet;
    var currentButtonStyle;
    var thirdPersonBoomLength = 1.5;
    var deferredLayoutTimer = null;
    var shuttingDown = false;

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

        if (shuttingDown || width <= 0 || height <= 0) {
            return;
        }

        layout = calculateLayout(width, height);
        currentButtonStyle = layout.buttonStyle;
        applyBarGeometry(navigationBar, layout.navigationPosition, layout.navigationSize);
        applyBarGeometry(audioBar, layout.audioPosition, layout.audioSize);
        applyButtonStyle(gotoButton, currentButtonStyle);
        applyButtonStyle(tabletButton, currentButtonStyle);
        applyButtonStyle(cameraButton, currentButtonStyle);
        applyButtonStyle(microphoneButton, currentButtonStyle);
    }

    function applyBarGeometry(bar, position, size) {
        if (!bar) {
            return;
        }
        try {
            bar.setPosition(position.x, position.y);
            bar.setSize(size.x, size.y);
        } catch (error) {
            // The Activity can destroy a fragment between a geometry signal
            // and script shutdown. The next startup creates a fresh surface.
        }
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

    function showTablet() {
        var tablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
        tablet.showAndroidTablet(Window.innerWidth, Window.innerHeight);
    }

    function resizeTablet() {
        systemTablet.resizeAndroidTablet(Window.innerWidth, Window.innerHeight);
    }

    function tabletVisibilityChanged() {
        var tabletShown = systemTablet.tabletShown;
        Controller.setVPadHidden(tabletShown);
        if (tabletShown) {
            Controller.captureTouchEvents();
        } else {
            Controller.releaseTouchEvents();
        }
        if (navigationBar) {
            navigationBar.visible = !tabletShown;
        }
        if (audioBar) {
            audioBar.visible = !tabletShown;
        }
    }

    function toggleMicrophone() {
        Audio.muted = !Audio.muted;
    }

    function isFirstPersonMode(mode) {
        return mode === "first person" || mode === "first person look at";
    }

    function toggleCameraMode() {
        if (isFirstPersonMode(Camera.mode)) {
            Camera.mode = "look at";
            MyAvatar.cameraBoomLength = thirdPersonBoomLength;
        } else {
            thirdPersonBoomLength = Math.max(MyAvatar.cameraBoomLength, 1.5);
            // The automatic view correction requires the first-person mode and
            // boom to agree. Set the boom first to avoid a corrective mode loop.
            MyAvatar.cameraBoomLength = 0.5;
            Camera.mode = "first person look at";
        }
    }

    currentButtonStyle = calculateLayout(Math.max(Window.innerWidth, 1), Math.max(Window.innerHeight, 1)).buttonStyle;
    systemTablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");

    navigationBar = createFragment("hifi/ActionBar.qml");
    audioBar = createFragment("hifi/AudioBar.qml");

    gotoButton = addButton(navigationBar, buttonProperties({
        icon: "icons/tablet-icons/goto-i.svg",
        activeIcon: "icons/tablet-icons/goto-a.svg",
        text: "GO TO"
    }));
    tabletButton = addButton(navigationBar, buttonProperties({
        icon: "icons/tablet-icons/menu-i.svg",
        activeIcon: "icons/tablet-icons/menu-a.svg",
        text: "TABLET"
    }));
    cameraButton = addButton(navigationBar, buttonProperties({
        icon: "icons/myview-i.svg",
        activeIcon: "icons/myview-i.svg",
        text: "VIEW"
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
    connectSignal(tabletButton, "clicked", showTablet);
    connectSignal(tabletButton, "entered", hapticFeedback);
    connectSignal(cameraButton, "clicked", toggleCameraMode);
    connectSignal(cameraButton, "entered", hapticFeedback);
    connectSignal(microphoneButton, "clicked", toggleMicrophone);
    connectSignal(microphoneButton, "entered", hapticFeedback);
    Window.geometryChanged.connect(updateLayout);
    Window.geometryChanged.connect(resizeTablet);
    systemTablet.tabletShownChanged.connect(tabletVisibilityChanged);
    tabletVisibilityChanged();
    // QML fragments also perform their initial placement in Component.onCompleted;
    // defer once so the phone-specific adaptive placement wins deterministically.
    deferredLayoutTimer = Script.setTimeout(function () {
        deferredLayoutTimer = null;
        updateLayout();
    }, 0);

    Script.scriptEnding.connect(function () {
        shuttingDown = true;
        if (deferredLayoutTimer !== null) {
            Script.clearTimeout(deferredLayoutTimer);
            deferredLayoutTimer = null;
        }
        Window.geometryChanged.disconnect(updateLayout);
        Window.geometryChanged.disconnect(resizeTablet);
        systemTablet.tabletShownChanged.disconnect(tabletVisibilityChanged);
        Controller.setVPadHidden(false);
        Controller.releaseTouchEvents();
        disconnectSignal(gotoButton, "clicked", showAddressBar);
        disconnectSignal(gotoButton, "entered", hapticFeedback);
        disconnectSignal(tabletButton, "clicked", showTablet);
        disconnectSignal(tabletButton, "entered", hapticFeedback);
        disconnectSignal(cameraButton, "clicked", toggleCameraMode);
        disconnectSignal(cameraButton, "entered", hapticFeedback);
        disconnectSignal(microphoneButton, "clicked", toggleMicrophone);
        disconnectSignal(microphoneButton, "entered", hapticFeedback);
        closeFragment(navigationBar);
        closeFragment(audioBar);
        navigationBar = null;
        audioBar = null;
        gotoButton = null;
        tabletButton = null;
        cameraButton = null;
        microphoneButton = null;
    });
}());
