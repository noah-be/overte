"use strict";

// Native-QML Emote surface for the Android phone. It deliberately avoids the
// desktop Web tablet and controller mapping owned by system/emote.js.
/* globals AnimationCache, MyAvatar, Script, Tablet */

(function () {
    var TABLET_ID = "com.highfidelity.interface.tablet.system";
    var APP_SOURCE = Script.resolvePath("PhoneEmote.qml");
    var FPS = 60;
    var MSEC_PER_SEC = 1000;
    var RESOURCE_FINISHED = 3;
    var EMOTES = [
        "Crying", "Surprised", "Dancing", "Cheering", "Waving",
        "Fall", "Pointing", "Clapping", "Sit", "Love"
    ];
    var animations = {};
    var tablet = Tablet.getTablet(TABLET_ID);
    var appOpen = false;
    var activeName = "";
    var activeTimer = null;

    EMOTES.forEach(function (name) {
        var variants = name === "Sit" ? ["Sit1", "Sit2", "Sit3"] : [name];
        animations[name] = variants.map(function (variant) {
            var url = Script.resolvePath("../assets/animations/" + variant + ".fbx");
            return {
                url: url,
                resource: AnimationCache.prefetch(url),
                animation: AnimationCache.getAnimation(url)
            };
        });
    });

    var button = tablet.addButton({
        icon: "icons/tablet-icons/emote-i.svg",
        activeIcon: "icons/tablet-icons/emote-a.svg",
        text: "EMOTE",
        sortOrder: 12
    });

    function sendState(status) {
        if (appOpen) {
            tablet.sendToQml({
                method: "phoneEmote.state",
                active: activeName,
                status: status || (activeName ? "Playing " + activeName : "Choose an emote")
            });
        }
    }

    function stopActive(sendUpdate) {
        if (activeTimer !== null) {
            Script.clearTimeout(activeTimer);
            activeTimer = null;
        }
        if (activeName) {
            MyAvatar.restoreAnimation();
            activeName = "";
        }
        if (sendUpdate) {
            sendState("Choose an emote");
        }
    }

    function selectAnimation(name) {
        var variants = animations[name];
        if (!variants) {
            return null;
        }
        return variants[Math.floor(Math.random() * variants.length)];
    }

    function play(name) {
        if (EMOTES.indexOf(name) === -1) {
            sendState("Unsupported emote");
            return;
        }
        if (activeName === name) {
            stopActive(true);
            return;
        }

        var selected = selectAnimation(name);
        var frames = selected && selected.animation && selected.animation.frames;
        if (!selected || selected.resource.state !== RESOURCE_FINISHED ||
                !frames || !isFinite(frames.length) || frames.length <= 0) {
            sendState("Animation is still loading");
            return;
        }

        stopActive(false);
        activeName = name;
        MyAvatar.overrideAnimation(selected.url, FPS, false, 0, frames.length);
        sendState();
        activeTimer = Script.setTimeout(function () {
            activeTimer = null;
            MyAvatar.restoreAnimation();
            activeName = "";
            sendState("Choose an emote");
        }, MSEC_PER_SEC * frames.length / FPS);
    }

    function onClicked() {
        if (appOpen) {
            tablet.gotoHomeScreen();
        } else {
            tablet.loadQMLSource(APP_SOURCE);
        }
    }

    function onScreenChanged(type, source) {
        var wasOpen = appOpen;
        appOpen = type === "QML" && source === APP_SOURCE;
        if (wasOpen && !appOpen) {
            stopActive(false);
        }
    }

    function fromQml(message) {
        if (!appOpen || !message || typeof message.method !== "string") {
            return;
        }
        if (message.method === "phoneEmote.ready") {
            sendState();
        } else if (message.method === "phoneEmote.play" && typeof message.name === "string") {
            play(message.name);
        }
    }

    button.clicked.connect(onClicked);
    tablet.screenChanged.connect(onScreenChanged);
    tablet.fromQml.connect(fromQml);

    Script.scriptEnding.connect(function () {
        stopActive(false);
        button.clicked.disconnect(onClicked);
        tablet.screenChanged.disconnect(onScreenChanged);
        tablet.fromQml.disconnect(fromQml);
        tablet.removeButton(button);
    });
}());
