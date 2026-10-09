#!/usr/bin/env python3
"""Execute the production clock, input/mute path and Android shutdown with device fixtures."""
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
    fixture = Path(__file__).with_name("voice-clock-fixture.cpp").read_text()
    for key, value in {
        "VOICE_MEMBERS": members, "VOICE_METHODS": clock,
        "AUDIO_INPUT_METHOD": method(source, "void AudioClient::handleAudioInput(QByteArray& audioBuffer) {"),
        "MUTE_METHOD": method(source, "void AudioClient::setMuted(bool muted, bool emitSignal) {"),
        "STOP_METHOD": method(source, "void AudioClient::stop() {").replace("qCDebug(audioclient)", "qDebug()").replace("qCWarning(audioclient)", "qWarning()"),
        "INPUT_SHUTDOWN_PREFIX": shutdown,
    }.items():
        fixture = fixture.replace(key, value)
    flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
    with tempfile.TemporaryDirectory(prefix="overte-voice-clock-") as private:
        root = Path(private)
        (root / "clock.cpp").write_text(fixture)
        subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC", "-pthread",
                        "-DOVERTE_E2E_VOICE_TESTS=1", "-I" + str(ROOT),
                        "-I" + str(ROOT / "libraries/audio-client/src"), str(root / "clock.cpp"),
                        "-o", str(root / "clock"), *flags], check=True, timeout=45)
        subprocess.run([str(root / "clock")], check=True, timeout=15)
    print("PASS production voice clock, complete muted/unmuted source, input shutdown, lifecycle, reset, lease and late-clock failure; OS/device/gate/encoder operations are fixtures")


if __name__ == "__main__":
    run()
