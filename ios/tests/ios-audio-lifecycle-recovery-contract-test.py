#!/usr/bin/env python3
"""Static contracts for integrated iOS audio lifecycle and recovery."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


audio_h = source("libraries/audio-client/src/AudioClient.h")
audio_cpp = source("libraries/audio-client/src/AudioClient.cpp")
bridge_h = source("libraries/audio-client/src/IOSAudioPermission.h")
bridge_mm = source("libraries/audio-client/src/IOSAudioPermission.mm")
application = source("interface/src/Application.cpp")
script_audio = source("interface/src/scripting/Audio.h")
audio_qml = source("interface/resources/qml/hifi/audio/Audio.qml")
constants = source("libraries/audio/src/AudioConstants.h")
matrix = json.loads(source("ios/tests/audio-device-acceptance.json"))
simulator_e2e = source("ios/ci/interface-audio-simulator-e2e.sh")

assert re.search(r"public slots:[\s\S]*void suspend\(\);[\s\S]*void resume\(\);", audio_h)
assert re.search(r"void Application::enterBackground\(\)[\s\S]*?\"suspend\", Qt::QueuedConnection", application)
assert re.search(r"void Application::enterForeground\(\)[\s\S]*?\"resume\", Qt::QueuedConnection", application)
for method in ("enterBackground", "enterForeground"):
    body = re.search(rf"void Application::{method}\(\) \{{([\s\S]*?)\n\}}", application)
    assert body and "BlockingQueuedConnection" not in body.group(1)

assert "if (_isStopping)" in audio_cpp
assert re.search(r"if \(_checkDevicesTimer\)[\s\S]*?_checkDevicesTimer->stop", audio_cpp)
assert re.search(r"if \(_checkPeakValuesTimer\)[\s\S]*?_checkPeakValuesTimer->stop", audio_cpp)
assert "requestIOSMicrophonePermission" in audio_cpp
assert "OverteIOSMicrophonePermissionState::Granted" in audio_cpp
assert re.search(r"Granted[\s\S]*switchInputToAudioDevice", audio_cpp)
assert "dispatch_once" not in re.search(
    r"void overteIOSRequestMicrophonePermission[\s\S]*?\n\}", bridge_mm
).group(0)

for notification in (
    "AVAudioSessionInterruptionNotification",
    "AVAudioSessionRouteChangeNotification",
    "AVAudioSessionMediaServicesWereResetNotification",
):
    assert notification in bridge_mm
for event in ("InterruptionBegan", "InterruptionEnded", "RouteChanged", "MediaServicesReset"):
    assert event in bridge_h and event in audio_cpp

assert "setPreferredSampleRate:48000.0" in bridge_mm
assert "setPreferredIOBufferDuration:0.01" in bridge_mm
assert re.search(r"Q_OS_IOS[\s\S]*?mobile_mode = true", audio_cpp)
assert re.search(r"Q_OS_IOS[\s\S]*?_audioOutput->setBufferSize\(requestedSize \* 2\)", audio_cpp)
assert "iOS audio output reopening with adaptive buffer frames=" in audio_cpp
assert re.search(r"const int SAMPLE_RATE = 24000", constants)

assert "microphonePermissionStatus" in script_audio
assert "Microphone access is disabled" in audio_qml
assert matrix["physicalExecutionRequired"] is True
assert "run_phase denied revoke" in simulator_e2e
assert "run_phase granted grant" in simulator_e2e
assert re.search(r"simctl privacy[^\n]*reset", simulator_e2e)
assert '"physicalAudioValidated": False' in simulator_e2e
case_ids = {case["id"] for case in matrix["cases"]}
assert {
    "permission-deny-and-settings-recovery",
    "background-foreground-10x",
    "interruption-recovery",
    "route-speaker-receiver-wired-bluetooth-hfp",
    "aec-double-talk",
    "format-buffer-latency",
} <= case_ids

print("PASS integrated iOS audio lifecycle, recovery, UI and device-matrix contracts")
