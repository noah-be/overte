//
//  LoopbackAudio.qml
//  qml/hifi/audio
//
//  Created by Seth Alves on 2019-2-18
//  Copyright 2019 High Fidelity, Inc.
//  Copyright 2025 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import QtQuick 2.7
import QtQuick.Controls 2.2
import QtQuick.Layouts 1.3

import stylesUit 1.0
import controlsUit 1.0 as HifiControlsUit

ColumnLayout {
    id: root
    spacing: 6
    width: parent ? Math.max(200, parent.width - 2 * x) : 600
    property bool audioLoopedBack: AudioScriptingInterface.getLocalEcho();
    property var recordedStatus: AudioScriptingInterface.getRecordedVoiceTestStatus()
    property bool recordingRequested: false
    readonly property bool recordingActive: recordingRequested || recordedStatus.phase === "capturing"
        || recordedStatus.phase === "playing" || recordedStatus.phase === "draining"
    onVisibleChanged: {
        if (!visible) {
            AudioScriptingInterface.cancelRecordedVoiceTest()
            loopbackTimer.stop()
            stopAudioLoopback()
        }
    }
    function startAudioLoopback() {
        if (!audioLoopedBack) {
            audioLoopedBack = true;
            AudioScriptingInterface.setLocalEcho(true);
        }
    }
    function stopAudioLoopback() {
        if (audioLoopedBack) {
            audioLoopedBack = false;
            AudioScriptingInterface.setLocalEcho(false);
        }
    }

    HifiConstants { id: hifi; }

    Connections {
        target: AudioScriptingInterface
        function onRecordedVoiceTestStatusChanged(status) {
            root.recordingRequested = false
            root.recordedStatus = status
        }
    }

    function recordedDescription() {
        if (recordingRequested) { return qsTr("Starting microphone test...") }
        if (recordedStatus.phase === "capturing") { return qsTr("Recording: speak for three seconds") }
        if (recordedStatus.phase === "playing" || recordedStatus.phase === "draining") {
            return qsTr("Listen to your recording")
        }
        if (recordedStatus.phase === "completed") { return qsTr("Recording played locally") }
        if (recordedStatus.phase === "cancelled") { return qsTr("Voice test cancelled") }
        if (recordedStatus.error === "microphone-muted") { return qsTr("Unmute your microphone to record") }
        if (recordedStatus.error === "live-echo-enabled") { return qsTr("Stop live echo before recording") }
        if (recordedStatus.error === "no-microphone-signal") { return qsTr("No microphone signal was recorded") }
        if (recordedStatus.phase === "error") { return qsTr("Voice test unavailable: check microphone, output and permissions") }
        return qsTr("A three-second recording, stored only in memory")
    }

    function activateRecording() {
        if (recordingActive) { AudioScriptingInterface.cancelRecordedVoiceTest() }
        else {
            recordingRequested = true
            AudioScriptingInterface.startRecordedVoiceTest()
        }
    }

    function activateLiveEcho() {
        if (audioLoopedBack) {
            loopbackTimer.stop()
            stopAudioLoopback()
        } else {
            loopbackTimer.restart()
            startAudioLoopback()
        }
    }

    RowLayout {
        HifiControlsUit.Button {
            id: recordingButton
            objectName: "recordedVoiceTestButton"
            text: root.recordingActive ? qsTr("CANCEL RECORDING") : qsTr("RECORD AND PLAY VOICE")
            color: root.recordingActive ? hifi.buttons.red : hifi.buttons.blue
            fontSize: 15
            width: 200
            height: 32
            androidClickAction: function() { root.activateRecording() }
            onClicked: { if (!usesAndroidClickAction) { root.activateRecording() } }
        }
        RalewayRegular {
            Layout.leftMargin: 2
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            size: 18
            color: "white"
            text: root.recordedDescription()
        }
    }

    RowLayout {

    Timer {
        id: loopbackTimer
        interval: 8000;
        running: false;
        repeat: false;
        onTriggered: {
            stopAudioLoopback();
        }
    }

    HifiControlsUit.Button {
        id: liveEchoButton
        objectName: "liveVoiceEchoButton"
        text: audioLoopedBack ? qsTr("STOP LIVE ECHO") : qsTr("TEST LIVE ECHO");
        enabled: !root.recordingActive
        color: audioLoopedBack ? hifi.buttons.red : hifi.buttons.blue;
        fontSize: 15;
        width: 200;
        height: 32;
        androidClickAction: function() { root.activateLiveEcho() }
        onClicked: { if (!usesAndroidClickAction) { root.activateLiveEcho() } }
    }

    RalewayRegular {
        Layout.leftMargin: 2;
        size: 18;
        color: "white";
        font.italic: true
        text: audioLoopedBack ? qsTr("Speak in your input") : "";
    }
    }

    Component.onDestruction: {
        AudioScriptingInterface.cancelRecordedVoiceTest();
        loopbackTimer.stop();
        stopAudioLoopback();
    }
}
