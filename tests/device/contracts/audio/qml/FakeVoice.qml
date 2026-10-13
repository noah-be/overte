pragma Singleton
import QtQuick 2.7
QtObject {
    property int starts: 0
    property int cancels: 0
    property bool echo: false
    property bool rejectMuted: false
    property var status: ({ phase: "idle", error: "" })
    signal recordedVoiceTestStatusChanged(var status)
    function getRecordedVoiceTestStatus() { return status }
    function getLocalEcho() { return echo }
    function setLocalEcho(value) { echo = value }
    function report(phase, error) {
        status = { phase: phase, error: error }
        recordedVoiceTestStatusChanged(status)
    }
    function startRecordedVoiceTest() {
        starts++
        report(rejectMuted ? "error" : "capturing", rejectMuted ? "microphone-muted" : "")
    }
    function cancelRecordedVoiceTest() { cancels++; report("cancelled", "") }
    function reset() { starts = 0; cancels = 0; echo = false; rejectMuted = false; status = { phase: "idle", error: "" } }
}
