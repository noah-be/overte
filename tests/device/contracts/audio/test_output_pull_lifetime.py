# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
"""Exercise production pull-source ownership and retirement with real Qt events.

The sink is an explicit backend seam; this does not qualify CoreAudio hardware.
The source declaration and stop/cancellation/close sequence come from production.
"""
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).parents[1] / "lifecycle"))
from test_login_dialog_domain_receiver import block

FIXTURE = r'''
#include <QCoreApplication>
#include <QEvent>
#include <QIODevice>
#include <QMetaObject>
#include <QThread>
#include <atomic>
#include <cassert>
#include <cstdio>
#include <memory>
struct LocalInjectorsStream {};
struct MixedProcessedAudioStream {};
namespace AudioConstants { constexpr int NETWORK_FRAME_BYTES_STEREO = 960; }
struct Sink : QObject {
    bool stopped = false;
    void stop() { stopped = true; }
};
struct AudioClient : QObject {
    /* SOURCE_DECLARATION */;
    LocalInjectorsStream injectors;
    MixedProcessedAudioStream received;
    AudioOutputIODevice _audioOutputIODevice { injectors, received, this };
    Sink sink;
    Sink* _audioOutput = &sink;
    std::atomic<bool> _audioOutputInitialized { true };
    void retire() {
        assert(QThread::currentThread() == thread());
        /* RETIREMENT */
    }
};
qint64 AudioClient::AudioOutputIODevice::readData(char*, qint64) { return 0; }

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    AudioClient audio;
    QThread worker;
    audio.moveToThread(&worker);
    // A pointer to the owner in a member field does not move its QObject thread.
    assert(audio._audioOutputIODevice.parent() == &audio);
    assert(audio._audioOutputIODevice.thread() == &worker);
    worker.start();
    int staleCalls = 0, freshCalls = 0, telemetry = 0, unrelated = 0;
    QObject other;
    other.moveToThread(&worker);
    for (int replacement = 0; replacement < 50; ++replacement) {
        QMetaObject::invokeMethod(&audio, [&] {
            audio._audioOutputInitialized = true;
            audio.sink.stopped = false;
            audio._audioOutputIODevice.start();
            auto retired = std::make_shared<bool>(false);
            // These are posted while active but delivered only after retirement.
            for (int i = 0; i < 100; ++i) {
                QMetaObject::invokeMethod(&audio._audioOutputIODevice, [&, retired] {
                    assert(QThread::currentThread() == audio.thread());
                    if (*retired) ++staleCalls;
                }, Qt::QueuedConnection);
            }
            QMetaObject::invokeMethod(&audio, [&] { ++telemetry; }, Qt::QueuedConnection);
            QMetaObject::invokeMethod(&other, [&] { ++unrelated; }, Qt::QueuedConnection);
            audio.retire();
            assert(audio.sink.stopped && !audio._audioOutputIODevice.isOpen());
            *retired = true;
            audio._audioOutputIODevice.start();
            QMetaObject::invokeMethod(&audio._audioOutputIODevice,
                                     [&] { ++freshCalls; }, Qt::QueuedConnection);
        }, Qt::BlockingQueuedConnection);
        // An event-loop barrier makes the queued-event assertions deterministic.
        QMetaObject::invokeMethod(&audio, [] {}, Qt::BlockingQueuedConnection);
        assert(staleCalls == 0);
        assert(freshCalls == replacement + 1);
        assert(telemetry == replacement + 1 && unrelated == replacement + 1);
    }
    QMetaObject::invokeMethod(&audio, [&] {
        audio._audioOutputIODevice.close();
        other.moveToThread(app.thread());
        audio.moveToThread(app.thread());
    }, Qt::BlockingQueuedConnection);
    worker.quit();
    assert(worker.wait(2000));
    std::puts("PASS: 50 replacements reject 5000 stale pulls; fresh pulls and telemetry survive");
}
'''


class OutputPullLifetime(unittest.TestCase):
    def test_ownership_and_retired_callbacks(self):
        header = (ROOT / "libraries/audio-client/src/AudioClient.h").read_text()
        source = (ROOT / "libraries/audio-client/src/AudioClient.cpp").read_text()
        declaration = block(header, "class AudioOutputIODevice : public QIODevice")
        switch = block(source, "bool AudioClient::switchOutputToAudioDevice(")
        retirement = switch.split("    if (_audioOutput) {", 1)[1].split(
            "        //must be deleted", 1)[0]
        flags = shlex.split(subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        mutations = (
            ("production", declaration, retirement, None),
            ("unparented-source", declaration.replace("QIODevice(audio),", ""),
             retirement, "parent() == &audio"),
            ("uncancelled-pulls", declaration,
             retirement.replace(
                 "QCoreApplication::removePostedEvents(&_audioOutputIODevice, QEvent::MetaCall);", ""),
             "staleCalls == 0"),
        )
        with tempfile.TemporaryDirectory(prefix="overte-output-lifetime-") as temporary:
            directory = Path(temporary)
            for name, decl, retire, expected_failure in mutations:
                with self.subTest(variant=name):
                    cpp = directory / (name + ".cpp")
                    binary = directory / name
                    cpp.write_text(FIXTURE.replace("/* SOURCE_DECLARATION */", decl)
                                   .replace("/* RETIREMENT */", retire))
                    subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread",
                                    str(cpp), "-o", str(binary), *flags], check=True, timeout=40)
                    # Prevent expected mutation assertions from writing host cores.
                    result = subprocess.run(["bash", "-c", 'ulimit -c 0; exec "$1"',
                                             "output-lifetime", str(binary)],
                                            capture_output=True, text=True, timeout=8)
                    if expected_failure:
                        self.assertNotEqual(result.returncode, 0, "mutation survived")
                        self.assertIn(expected_failure, result.stderr)
                    else:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        print(result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
