//
//  InputDeviceButton.qml
//
//  Created by Zach Fox on 2019-05-02
//  Based off of MicBarApplication.qml by Zach Pomerantz and Wayne Chen
//  Copyright 2019 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import QtQuick 2.10
import "../../audio" as SharedAudio
import TabletScriptingInterface 1.0
import "../simplifiedConstants" as SimplifiedConstants

Rectangle {
    id: micBar

    SimplifiedConstants.SimplifiedConstants {
        id: simplifiedUI
    }

    readonly property real level: isFinite(AudioScriptingInterface.inputLevel) ?
        Math.max(0, Math.min(1, AudioScriptingInterface.inputLevel)) : 0
    readonly property var clipping: AudioScriptingInterface.clipping
    property var muted: AudioScriptingInterface.muted
    property var pushToTalk: AudioScriptingInterface.pushToTalk
    property var pushingToTalk: AudioScriptingInterface.pushingToTalk
    readonly property var userSpeakingLevel: 0.4
    property bool gated: false
    onPushToTalkChanged: if (!pushToTalk && mouseArea) mouseArea.finishPushToTalk(false)
    onVisibleChanged: if (!visible && mouseArea) mouseArea.finishPushToTalk(false)

    readonly property string unmutedIcon: "images/mic-unmute-i.svg"
    readonly property string mutedIcon: "images/mic-mute-i.svg"
    readonly property string pushToTalkIcon: "images/mic-ptt-i.svg"
    readonly property string pushToTalkClippingIcon: "images/mic-ptt-clip-i.svg"
    readonly property string pushToTalkMutedIcon: "images/mic-ptt-mute-i.svg"
    readonly property string clippingIcon: "images/mic-clip-i.svg"
    readonly property string gatedIcon: "images/mic-gate-i.svg"
    
    Connections {
        target: AudioScriptingInterface

        function onNoiseGateOpened() {
            gated = false;
        }

        function onNoiseGateClosed() {
            gated = false;
        }
    }

    color: "#00000000"

    MouseArea {
        id: mouseArea
        property bool pushToTalkHeld: false
        function finishPushToTalk(withSound) {
            if (!pushToTalkHeld) return
            pushToTalkHeld = false
            AudioScriptingInterface.pushingToTalk = false
            if (withSound) Tablet.playSound(TabletEnums.ButtonClick)
        }
        
        anchors.fill: parent

        hoverEnabled: true
        scrollGestureEnabled: false
        onClicked: {
            if (pushToTalk) {
                return;
            }
            AudioScriptingInterface.muted = !muted;
            Tablet.playSound(TabletEnums.ButtonClick);
            muted = Qt.binding(function() { return AudioScriptingInterface.muted; }); // restore binding
        }

        onPressed: {
            if (pushToTalk) {
                pushToTalkHeld = true;
                AudioScriptingInterface.pushingToTalk = true;
                Tablet.playSound(TabletEnums.ButtonClick);
            }
        }

        onReleased: finishPushToTalk(true)

        onCanceled: finishPushToTalk(true)
        
        onContainsMouseChanged: {
            if (containsMouse) {
                Tablet.playSound(TabletEnums.ButtonHover);
            }
        }
    }

    QtObject {
        id: colors

        readonly property string unmutedColor: simplifiedUI.colors.controls.inputVolumeButton.text.noisy
        readonly property string gatedColor: "#00BDFF"
        readonly property string mutedColor: simplifiedUI.colors.controls.inputVolumeButton.text.muted
        readonly property string gutter: "#575757"
        readonly property string greenStart: "#39A38F"
        readonly property string greenEnd: "#1FC6A6"
        readonly property string yellow: "#C0C000"
        readonly property string fill: "#55000000"
        readonly property string icon: (muted || clipping) ? mutedColor : gated ? gatedColor : unmutedColor
    }

    Item {
        id: icon
        anchors.verticalCenter: parent.verticalCenter
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.rightMargin: 2
        width: pushToTalk ? (clipping && pushingToTalk ? 4 : 16) : (muted ? 20 : 16)
        height: 22

        Image {
            id: image
            visible: false
            source: pushToTalk ? (clipping && pushingToTalk ? pushToTalkClippingIcon : pushToTalkIcon) : muted ? mutedIcon :
                clipping ? clippingIcon : gated ? gatedIcon : unmutedIcon
            anchors.fill: parent
        }

        SharedAudio.TintedImage {
            opacity: mouseArea.containsMouse ? 1.0 : 0.7
            visible: level === 0 || micBar.muted || micBar.clipping
            anchors.fill: image
            source: image.source
            color: pushToTalk ? (pushingToTalk ? colors.icon : colors.mutedColor) : colors.icon
        }

        SharedAudio.LevelImage {
            visible: level > 0 && !micBar.muted && !micBar.clipping
            anchors.fill: image
            source: image.source
            level: micBar.level
            low: colors.greenStart
            middle: colors.greenEnd
            high: colors.yellow
        }
    }
}
