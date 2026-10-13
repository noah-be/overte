import QtQuick 2.7
import QtTest 1.2
import TestVoice 1.0
import "../production" as Production

Item {
    width: 600
    height: 300
    Component { id: component; Production.LoopbackAudio {} }
    TestCase {
        name: "RecordedVoiceControls"
        when: windowShown
        property var view
        function init() {
            AudioScriptingInterface.reset()
            view = component.createObject(parent)
            verify(view)
            wait(30)
        }
        function cleanup() { view.destroy(); wait(10) }
        function clickButton(name) {
            var button = findChild(view, name)
            verify(button)
            mouseClick(button, button.width / 2, button.height / 2)
        }
        function test_record_status_and_cancel_are_native_driven() {
            clickButton("recordedVoiceTestButton")
            compare(AudioScriptingInterface.starts, 1)
            verify(view.recordingActive)
            compare(view.recordedStatus.phase, "capturing")
            verify(!findChild(view, "liveVoiceEchoButton").enabled)
            AudioScriptingInterface.report("playing", "")
            compare(view.recordedDescription(), "Listen to your recording")
            clickButton("recordedVoiceTestButton")
            compare(AudioScriptingInterface.cancels, 1)
            verify(!view.recordingActive)
        }
        function test_muted_error_is_visible_without_automatic_unmute() {
            AudioScriptingInterface.rejectMuted = true
            clickButton("recordedVoiceTestButton")
            compare(AudioScriptingInterface.starts, 1)
            verify(!view.recordingActive)
            compare(view.recordedDescription(), "Unmute your microphone to record")
            compare(AudioScriptingInterface.echo, false)
        }
        function test_native_completion_does_not_enable_echo() {
            clickButton("recordedVoiceTestButton")
            AudioScriptingInterface.report("completed", "")
            verify(!view.recordingActive)
            compare(view.recordedDescription(), "Recording played locally")
            compare(AudioScriptingInterface.echo, false)
            compare(AudioScriptingInterface.starts, 1)
        }
        function test_hidden_panel_cancels_capture() {
            clickButton("recordedVoiceTestButton")
            view.visible = false
            compare(AudioScriptingInterface.cancels, 1)
            verify(!view.recordingActive)
        }
        function test_original_echo_and_destruction_cleanup() {
            clickButton("liveVoiceEchoButton")
            compare(AudioScriptingInterface.echo, true)
            clickButton("liveVoiceEchoButton")
            compare(AudioScriptingInterface.echo, false)
            clickButton("recordedVoiceTestButton")
            view.destroy(); view = null; wait(10)
            compare(AudioScriptingInterface.cancels, 1)
            view = component.createObject(parent)
        }
    }
}
