"""Execute the actual AudioClient recovery method with a deterministic sink seam."""
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).parents[1] / 'lifecycle'))
from test_login_dialog_domain_receiver import block

source = (ROOT / 'libraries/audio-client/src/AudioClient.cpp').read_text()
method = block(source, 'void AudioClient::refreshIOSAudioOutput()')
# Execute the original loopback entry up to the native/mixer seam. Failed sink
# startup leaves a sink object but no loopback backend; that must return early.
echo = block(source, 'void AudioClient::handleLocalEchoAndReverb(')
echo = echo[:echo.index('    // if this person wants local loopback')] + '    ++echoCalls;\n}'

fixture = r'''
#include <QObject>
#include <QByteArray>
#include <QThread>
#include <QString>
#include <atomic>
#include <mutex>
#include <cassert>
#include <cstdint>
namespace QAudio {
enum State { ActiveState, IdleState, StoppedState, SuspendedState };
enum Error { NoError, OpenError };
}
struct Sink {
    QAudio::State s { QAudio::ActiveState };
    QAudio::Error e { QAudio::NoError };
    auto state() const { return s; }
    auto error() const { return e; }
};
struct HifiAudioDeviceInfo {};
enum class HifiAudioDeviceMode { Output };
using Lock = std::unique_lock<std::mutex>;
bool allowed = false;
std::uint64_t revision = 1;
bool overteIOSAudioPlaybackAllowed() { return allowed; }
std::uint64_t overteIOSAudioOutputRevision() { return revision; }
struct AudioClient : QObject {
    std::mutex _checkDevicesMutex;
    bool _audioLifecycleRunning = true;
    Sink sink;
    Sink* _audioOutput = nullptr;
    std::atomic<bool> _audioOutputInitialized { false };
    std::uint64_t _iosOutputRevision = 0;
    unsigned _iosOutputRecoveryAttempts = 0;
    unsigned starts = 0, stops = 0;
    bool fail = false;
    bool _isMuted = false, _shouldEchoLocally = true, _reverb = false, _audioGateOpen = true;
    Sink* _loopbackAudioOutput = nullptr;
    QByteArray _loopbackPendingAudio;
    struct { bool hasReverb() const { return false; } } _receivedAudioStream;
    int echoCalls = 0;
    void handleLocalEchoAndReverb(QByteArray&);

    HifiAudioDeviceInfo defaultAudioDeviceForMode(HifiAudioDeviceMode, QString) { return {}; }
    bool switchOutputToAudioDevice(HifiAudioDeviceInfo, bool stop = false) {
        if (stop) { ++stops; _audioOutput = nullptr; _audioOutputInitialized = false; return true; }
        ++starts;
        _audioOutput = &sink;
        sink.s = fail ? QAudio::StoppedState : QAudio::ActiveState;
        sink.e = fail ? QAudio::OpenError : QAudio::NoError;
        _audioOutputInitialized = !fail;
        return !fail;
    }
    void refreshIOSAudioOutput();
};
/* METHOD */
/* ECHO */
int main() {
    AudioClient a;
    QByteArray input;
    a._audioOutput = &a.sink;
    a._loopbackPendingAudio = "pending";
    a.handleLocalEchoAndReverb(input);
    assert(a.echoCalls == 0 && a._loopbackPendingAudio.isEmpty());
    a._loopbackAudioOutput = &a.sink;
    a.handleLocalEchoAndReverb(input);
    assert(a.echoCalls == 0); // a partially initialized output is not usable
    a._audioOutputInitialized = true;
    a.handleLocalEchoAndReverb(input);
    assert(a.echoCalls == 1); // healthy echo still reaches the mixer
    a._audioOutput = nullptr;
    a._audioOutputInitialized = false;

    a.refreshIOSAudioOutput();
    assert(a.starts == 0);
    allowed = true;
    a.refreshIOSAudioOutput();
    assert(a.starts == 1);
    for (int i = 0; i < 100; ++i) a.refreshIOSAudioOutput();
    assert(a.starts == 1); // repeated notifications preserve a healthy sink
    a.sink.s = QAudio::IdleState;
    a.refreshIOSAudioOutput();
    assert(a.starts == 1); // idle is a usable output
    ++revision;
    a.refreshIOSAudioOutput();
    assert(a.starts == 2); // route/session generation replaces even a healthy sink
    allowed = false;
    a.refreshIOSAudioOutput();
    a.refreshIOSAudioOutput();
    assert(a.stops == 1 && !a._audioOutput);
    allowed = true;
    ++revision;
    a.refreshIOSAudioOutput();
    assert(a.starts == 3); // foreground/interruption resume
    a.sink.s = QAudio::SuspendedState;
    a.refreshIOSAudioOutput();
    assert(a.starts == 4);
    ++revision;
    a.fail = true;
    for (int i = 0; i < 100; ++i) a.refreshIOSAudioOutput();
    assert(a.starts == 6); // no unbounded stateChanged retry loop
    ++revision;
    a.fail = false;
    a.refreshIOSAudioOutput();
    assert(a.starts == 7 && a._audioOutputInitialized);
    a._audioLifecycleRunning = false;
    ++revision;
    a.refreshIOSAudioOutput();
    assert(a.starts == 7); // shutdown cannot resurrect output
}
'''
flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
with tempfile.TemporaryDirectory(prefix='overte-ios-output-') as scratch:
    path = Path(scratch)
    (path / 'test.cpp').write_text(fixture.replace('/* METHOD */', method).replace('/* ECHO */', echo))
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-fPIC', '-pthread',
                    str(path / 'test.cpp'), '-o', str(path / 'test'), *flags], check=True, timeout=40)
    subprocess.run([str(path / 'test')], check=True, timeout=5)
print('PASS actual AudioClient output recovery: resume, route, idle, failure limit, shutdown')
