"""Received-PCM assertions, native signal parity, transport and fixture failures."""
from __future__ import annotations

import array
import base64
import hashlib
import importlib.util
import itertools
import json
import os
import shlex
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import wave

ROOT = Path(__file__).resolve().parents[3] / "tests/device"
sys.path.insert(0, str(ROOT))
from voice_contract import command, result, wav
from voice_peer import voice_signal as dsp
from voice_peer.fixture import VoicePeerFixture
from adapters.voice_transport import exchange as transport

os.environ.setdefault("OVERTE_DEVICE_ADAPTER_MANIFEST", str(ROOT / "adapters/mock/adapter.json"))
os.environ.setdefault("OVERTE_DEVICE_TARGET_SELECTOR", "voice-self-test")
os.environ.setdefault("OVERTE_DEVICE_ARTIFACT_DIR", tempfile.gettempdir())
SPEC = importlib.util.spec_from_file_location("voice_roundtrip_module", ROOT / "modules/voice_roundtrip.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
CHALLENGE = "0123456789abcdef0123456789abcdef"


class NativeVoiceSignalTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++") and shutil.which("pkg-config"), "native clock check requires a C++ compiler and Qt6 pkg-config")
    def test_actual_clock_survives_input_shutdown_and_cancels_on_lifecycle_loss(self):
        subprocess.run([sys.executable, str(ROOT / "contracts/audio/test_voice_clock.py")],
                       check=True, timeout=65)

    @unittest.skipUnless(shutil.which("c++") and shutil.which("pkg-config"), "native hook check requires a C++ compiler and Qt6 pkg-config")
    def test_actual_qt_hook_compiles_and_bounds_recording_lifecycle(self):
        source = (ROOT.parents[1] / "interface/src/scripting/TestScriptingInterface.cpp").read_text()
        start = source.index("QVariantMap TestScriptingInterface::voiceTest(")
        end = source.index("\n#endif", start)
        method = source[start:end]
        audio_source = (ROOT.parents[1] / "libraries/audio-client/src/AudioClient.cpp").read_text()
        input_start = audio_source.index("void AudioClient::handleAudioInput(QByteArray& audioBuffer) {")
        input_start = audio_source.index("#if defined(OVERTE_E2E_VOICE_TESTS)", input_start)
        input_end = audio_source.index("#endif", input_start)
        input_hook = audio_source[input_start:input_end].split("\n", 1)[1]
        fixture = r'''
#include <QCoreApplication>
#include <QObject>
#include <QThread>
#include <QSharedPointer>
#include <QVariantMap>
#include <QCryptographicHash>
#include <QRegularExpression>
#include <QTimer>
#include <QFile>
#include <QDir>
#include <QTemporaryDir>
#include <functional>
#include <cassert>
#include "VoiceTestSignal.h"
namespace AudioConstants { constexpr int SAMPLE_RATE = 24000; }
class AudioClient : public QObject {
public:
    bool recording = false;
    VoiceTestSignal signal;
    VoiceTestSignal& _voiceTestSignal = signal;
    bool _isStereoInput = false, _isMuted = false;
    bool _voiceTestInputEnabled = false, _voiceTestDelivering = false;
    bool prepared = false;
    bool prepareVoiceTest() {
        if (prepared) { return false; }
        signal.enable(); prepared = true; return true;
    }
    bool sendVoiceTest(const std::array<int, 12>& symbols) {
        if (!prepared || signal.active()) { return false; }
        signal.send(symbols); return true;
    }
    void resetVoiceTest() { signal.reset(); prepared = false; }
    void touchVoiceTest() {}
    QVariantMap voiceTestStatus() const { return {{"sending", signal.active()}, {"frames", signal.frames()}}; }
    void handleAudioInput(QByteArray& audioBuffer) { INPUT_HOOK }
    bool getRecording() { return recording; }
    VoiceTestSignal& voiceTestSignal() { return signal; }
    bool startRecording(const QString& path) {
        QFile file(path); if (!file.open(QIODevice::WriteOnly)) { return false; }
        file.write("received-wav"); recording = true; return true;
    }
    void stopRecording() { recording = false; }
};
struct DependencyManager {
    template<class T> static QSharedPointer<T> get() { static auto pointer = QSharedPointer<T>::create(); return pointer; }
};
class TestScriptingInterface : public QObject {
public:
    QString _testResultsLocation, _voiceCapturePath;
    quint64 _voiceCaptureGeneration = 0;
    QVariantMap voiceTest(const QVariantMap&);
};
METHOD
int main(int argc, char** argv) {
    QCoreApplication application(argc, argv);
    QTemporaryDir directory;
    TestScriptingInterface test;
    QVariantMap command { { "schemaVersion", 1 }, { "commandId", "fresh" }, { "action", "prepare" } };
    assert(!test.voiceTest(command).value("ok").toBool());
    test._testResultsLocation = directory.path();
    assert(test.voiceTest(command).value("ok").toBool());
    command["action"] = "send"; command["challenge"] = "invalid";
    assert(!test.voiceTest(command).value("ok").toBool());
    command["challenge"] = "0123456789abcdef0123456789abcdef";
    assert(test.voiceTest(command).value("ok").toBool());
    assert(!test.voiceTest(command).value("ok").toBool()); // overlapping sender
    command["action"] = "capture-start"; command["seconds"] = 100;
    assert(!test.voiceTest(command).value("ok").toBool());
    command["seconds"] = 8;
    assert(test.voiceTest(command).value("ok").toBool());
    assert(!test.voiceTest(command).value("ok").toBool()); // overlapping capture
    auto path = test._voiceCapturePath;
    command["action"] = "capture-stop";
    auto capture = test.voiceTest(command);
    assert(capture.value("ok").toBool());
    assert(QByteArray::fromBase64(capture.value("wavBase64").toByteArray()) == "received-wav");
    assert(!QFile::exists(path));
    assert(!test.voiceTest(command).value("ok").toBool());
    command["action"] = "reset";
    assert(test.voiceTest(command).value("ok").toBool());
    assert(!DependencyManager::get<AudioClient>()->signal.active());
    command["action"] = "send";
    assert(!test.voiceTest(command).value("ok").toBool()); // send requires an owned clock
    command["action"] = "reset";
    auto audio = DependencyManager::get<AudioClient>();
    audio->signal.send({0,1,2,3,4,5,6,7,0,1,2,3});
    QByteArray pcm(480, '\0');
    for (int i = 0; i < 51; ++i) { audio->handleAudioInput(pcm); }
    assert(pcm != QByteArray(480, '\0'));
    const int before = audio->signal.frames();
    audio->_isMuted = true;
    audio->handleAudioInput(pcm);
    assert(pcm == QByteArray(480, '\0')); // codec-flush input cannot leak synthetic audio
    assert(audio->signal.frames() == before + 240);
    audio->_isMuted = false;
    audio->handleAudioInput(pcm);
    assert(pcm != QByteArray(480, '\0'));
}
'''.replace("METHOD", method).replace("INPUT_HOOK", input_hook)
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        with tempfile.TemporaryDirectory() as private:
            root = Path(private)
            (root / "test.cpp").write_text(fixture)
            subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC", "-I" + str(ROOT.parents[1] / "libraries/audio-client/src"), str(root / "test.cpp"), "-o", str(root / "test"), *flags], check=True, timeout=30)
            subprocess.run([str(root / "test"), "--testScript", "probe.js"], check=True, timeout=5)

    @unittest.skipUnless(shutil.which("c++"), "native PCM check requires a C++ compiler")
    def test_actual_cpp_generator_matches_python_reference_and_reset(self):
        with tempfile.TemporaryDirectory() as private:
            root = Path(private)
            source = r'''
#include "VoiceTestSignal.h"
#include <cassert>
#include <cstdio>
#include <vector>
int main() {
    VoiceTestSignal signal;
    int16_t untouched[2] = {123, 456};
    signal.replace(untouched, 1, 2); assert(untouched[0] == 123);
    signal.enable(); signal.replace(untouched, 1, 2); assert(untouched[0] == 0);
    signal.send({ SYMBOLS });
    std::vector<int16_t> pcm(VoiceTestSignal::FRAMES * 2);
    for (int offset = 0; offset < VoiceTestSignal::FRAMES; offset += 240) {
        signal.replace(pcm.data() + offset * 2, 240, 2);
    }
    assert(!signal.active() && signal.frames() == VoiceTestSignal::FRAMES);
    signal.replace(untouched, 1, 2); assert(untouched[0] == 0);
    signal.reset(); untouched[0] = 777; signal.replace(untouched, 1, 2); assert(untouched[0] == 777);
    std::fwrite(pcm.data(), sizeof(int16_t), pcm.size(), stdout);
}
'''.replace("SYMBOLS", ",".join(map(str, dsp.sequence(CHALLENGE))))
            (root / "test.cpp").write_text(source)
            subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT.parents[1] / "libraries/audio-client/src"), str(root / "test.cpp"), "-o", str(root / "test")], check=True, timeout=30)
            completed = subprocess.run([str(root / "test")], capture_output=True, check=True, timeout=5)
            native = array.array("h")
            native.frombytes(completed.stdout)
            expected = dsp.samples(CHALLENGE)
            self.assertEqual(len(native), 2 * len(expected))
            self.assertLessEqual(max(abs(a - b) for a, b in zip(native[::2], expected)), 1)
            self.assertEqual(native[::2], native[1::2])
            path = root / "native.wav"
            with wave.open(str(path), "wb") as output:
                output.setparams((2, 2, 24000, 0, "NONE", "not compressed"))
                output.writeframes(completed.stdout)
            self.assertTrue(dsp.analyze(path, CHALLENGE)["passed"])


if __name__ == "__main__":
    unittest.main()
