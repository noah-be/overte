#!/usr/bin/env python3
"""Execute the production clock, input/mute path and iOS shutdown with OS fixtures."""
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]


def method(source: str, signature: str) -> str:
    start = source.index(signature)
    opening = source.index("{", start)
    # These methods have balanced braces in comments/strings as well as code.
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def run() -> None:
    source = (ROOT / "libraries/audio-client/src/AudioClient.cpp").read_text()
    header = (ROOT / "libraries/audio-client/src/AudioClient.h").read_text()
    start = header.index("    VoiceTestSignal _voiceTestSignal;")
    members = header[start:header.index("#endif", start)]
    start = source.index("bool AudioClient::voiceTestLifecycleAllowed() const {")
    clock = source[start:source.index("\n#endif\n\nvoid AudioClient::handleAudioInput", start)]
    start = source.index("bool AudioClient::switchInputToAudioDevice(")
    end = source.index("    if (isShutdownRequest) {", start)
    end += len(method(source[end:], "    if (isShutdownRequest) {"))
    shutdown = source[start:end] + "\n"
    shutdown = shutdown.replace("qCDebug(audioclient)", "qDebug()")
    refresh = "void AudioClient::refreshIOSAudioInput() {}"
    if "void AudioClient::refreshIOSAudioInput() {" in source:
        refresh = method(source, "void AudioClient::refreshIOSAudioInput() {")
    actual_adapter = (ROOT / "ios/audio/IOSAudioAdapter.cpp").is_file()
    if actual_adapter:
        native = r'''
struct Native final:overte::ios::NativeAudioOperations {
 overte::audio::Permission granted=overte::audio::Permission::Granted;
 bool failStart=false;
 bool activate(bool capture,std::function<bool()> current)override{return current() && !(capture && failStart);}
 bool deactivate()override{return true;}
 overte::audio::Permission permission()override{return granted;}
 void requestPermission(std::function<bool()>,std::function<void(overte::audio::Permission)>)override{}
};
auto makeNative(){return std::make_shared<Native>();}
auto makeAdapter(std::shared_ptr<Native> native){return std::make_shared<overte::ios::IOSAudioAdapter>(native);}
void foreground(std::shared_ptr<overte::ios::IOSAudioAdapter> adapter,bool value){adapter->foreground(value);}
void deny(std::shared_ptr<Native> native,std::shared_ptr<overte::ios::IOSAudioAdapter> adapter){native->granted=overte::audio::Permission::Denied;adapter->refreshPermission();}
void failCapture(std::shared_ptr<Native> native,std::shared_ptr<overte::ios::IOSAudioAdapter> adapter){native->granted=overte::audio::Permission::Granted;adapter->refreshPermission();native->failStart=true;adapter->muted(true);adapter->muted(false);}
'''
    else:
        native = r'''
struct Native:overte::audio::IOSAudioSessionAdapter {
 overte::audio::IOSVoiceTestState state {overte::audio::Permission::Granted,overte::audio::Outcome::Capturing,true,false,true};
 bool microphonePermissionGranted()override{return state.captureAllowed;}
 void requestMicrophonePermission()override{}
 bool activate()override{return true;}bool deactivate()override{return true;}
 void muted(bool value)override{state.captureAllowed=!value && state.permission==overte::audio::Permission::Granted;}
 overte::audio::IOSVoiceTestState voiceTestState()const override{return state;}
};
auto makeNative(){return std::make_shared<Native>();}
auto makeAdapter(std::shared_ptr<Native> native){return native;}
void foreground(std::shared_ptr<Native> adapter,bool value){adapter->state.foreground=value;}
void deny(std::shared_ptr<Native> native,std::shared_ptr<Native>){native->state.permission=overte::audio::Permission::Denied;native->state.captureAllowed=false;}
void failCapture(std::shared_ptr<Native> native,std::shared_ptr<Native>){native->state.permission=overte::audio::Permission::Granted;native->state.outcome=overte::audio::Outcome::Failed;native->state.captureAllowed=false;}
'''
    fixture = Path(__file__).with_name("voice-clock-fixture.cpp").read_text()
    for key, value in {
        "NATIVE_ADAPTER_INCLUDE": '#include "ios/audio/IOSAudioAdapter.h"' if actual_adapter else "",
        "NATIVE_ADAPTER_FIXTURE": native, "VOICE_MEMBERS": members, "VOICE_METHODS": clock,
        "AUDIO_INPUT_METHOD": method(source, "void AudioClient::handleAudioInput(QByteArray& audioBuffer) {"),
        "IOS_REFRESH_METHOD": refresh,
        "MUTE_METHOD": method(source, "void AudioClient::setMuted(bool muted, bool emitSignal) {"),
        "STOP_METHOD": method(source, "void AudioClient::stop() {").replace("qCDebug(audioclient)", "qDebug()").replace("qCWarning(audioclient)", "qWarning()"),
        "INPUT_SHUTDOWN_PREFIX": shutdown, "HAS_IOS_REFRESH": "true" if refresh != "void AudioClient::refreshIOSAudioInput() {}" else "false",
    }.items():
        fixture = fixture.replace(key, value)
    flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
    with tempfile.TemporaryDirectory(prefix="overte-voice-clock-") as private:
        root = Path(private)
        (root / "clock.cpp").write_text(fixture)
        extra = [str(ROOT / "ios/audio/IOSAudioAdapter.cpp")] if actual_adapter else []
        subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC", "-pthread",
                        "-DOVERTE_E2E_VOICE_TESTS=1", "-I" + str(ROOT),
                        "-I" + str(ROOT / "libraries/audio-client/src"), str(root / "clock.cpp"), *extra,
                        "-x", "c++", str(ROOT / "libraries/audio-client/src/IOSAudioPermission.mm"),
                        "-o", str(root / "clock"), *flags], check=True, timeout=45)
        subprocess.run([str(root / "clock")], check=True, timeout=15)
    print("PASS production voice clock, complete muted/unmuted source, input shutdown, lifecycle, reset, lease and late-clock failure; OS/device/gate/encoder operations are fixtures")


if __name__ == "__main__":
    run()
