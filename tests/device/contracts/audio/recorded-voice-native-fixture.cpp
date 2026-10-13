// Host boundaries for the actual AudioClient preview methods. No device claim.
#include <QCoreApplication>
#include <QBuffer>
#include <QElapsedTimer>
#include <QThread>
#include <QTimer>
#include <QVariantMap>
#include <QDebug>
#include <QMutex>
#include <atomic>
#include <cassert>
#include <cstring>
#include <mutex>
#include "libraries/audio-client/src/PhoneVoiceTestBuffer.h"

namespace QAudio { enum State { ActiveState, IdleState, StoppedState }; enum Error { NoError, IOError }; }
namespace AudioConstants { constexpr int SAMPLE_SIZE = 2; }
constexpr int USECS_PER_SECOND = 1000000, USECS_PER_MSEC = 1000, OUTPUT_CHANNEL_COUNT = 2;
#define audioclient nullptr
#define qCDebug(category) qDebug()
#define qCWarning(category) qWarning()

struct Format {
    int sampleRate() const { return 48000; }
    int channelCount() const { return 2; }
    qint64 bytesForDuration(qint64 duration) const { return duration * 192000 / USECS_PER_SECOND; }
};
struct Input {
    QAudio::State currentState = QAudio::ActiveState;
    QAudio::Error currentError = QAudio::NoError;
    QAudio::State state() const { return currentState; }
    QAudio::Error error() const { return currentError; }
};
struct Output : Input {
    QBuffer device;
    int capacity = 65536;
    QIODevice* start() { device.open(QIODevice::WriteOnly); return &device; }
    void reset() { device.close(); device.setData({}); }
    int bytesFree() const { return capacity; }
    int bufferSize() const { return 65536; }
};
struct AudioSRC {
    AudioSRC(int, int, int) {}
    int getMaxOutput(int frames) const { return frames; }
};
static int possibleResampling(AudioSRC*, int16_t* in, int16_t* out, int count, int, int, int) {
    std::memcpy(out, in, static_cast<size_t>(count) * sizeof(int16_t)); return count;
}
static void channelUpmix(int16_t*, int16_t*, int, int) { assert(false); }
static void channelDownmix(int16_t*, int16_t*, int) { assert(false); }
struct Reverb { void render(int16_t*, int16_t*, int) {} };
struct Received { bool hasReverb() const { return false; } };

class AbstractAudioInterface : public QObject {
    Q_OBJECT
public slots:
    virtual void startRecordedVoiceTest() = 0;
    virtual void cancelRecordedVoiceTest() = 0;
signals:
    void recordedVoiceTestStatusChanged(const QVariantMap& status);
    void isStereoInputChanged(bool stereo);
};

class AudioClient : public AbstractAudioInterface {
    Q_OBJECT
public:
    AudioClient() {
        connect(this, &AbstractAudioInterface::recordedVoiceTestStatusChanged, this,
                [this](const QVariantMap& next) { status = next; });
    }
    using Lock = std::unique_lock<std::mutex>;
    std::mutex _deviceMutex;
    Input input;
    Output output;
    Input* _audioInput = &input;
    QIODevice* _inputDevice = &output.device;
    Output* _audioOutput = &output;
    Output* _loopbackAudioOutput = &output;
    QIODevice* _loopbackOutputDevice = nullptr;
    Format _inputFormat, _outputFormat;
    std::atomic<bool> _audioOutputInitialized { true };
    bool _isMuted = false, _audioPaused = false, _audioLifecycleRunning = true;
    bool _shouldEchoLocally = false, _audioGateOpen = false, _reverb = false;
    bool _isPlayingBackRecording = false, _androidAudioInputActive = false;
    QByteArray _loopbackPendingAudio;
    AudioSRC* _loopbackResampler = nullptr;
    Reverb _sourceReverb;
    Received _receivedAudioStream;
    void updateReverbOptions() {}
    QVariantMap status;
    // Production private state/declarations are inserted by the runner.
    @STATE@
public slots:
    void startRecordedVoiceTest();
    void cancelRecordedVoiceTest();
    void setLocalEcho(bool);
    void handleLocalEchoAndReverb(QByteArray&);
};

class AudioScriptingInterface : public QObject {
    Q_OBJECT
public:
    void setLocalAudioInterface(AbstractAudioInterface*);
    Q_INVOKABLE void startRecordedVoiceTest();
    Q_INVOKABLE void cancelRecordedVoiceTest();
    Q_INVOKABLE QVariantMap getRecordedVoiceTestStatus() const;
signals:
    void recordedVoiceTestStatusChanged(const QVariantMap& status);
    void isStereoInputChanged(bool stereo);
private:
    void updateRecordedVoiceTestStatus(const QVariantMap&);
    AbstractAudioInterface* _localAudioInterface = nullptr;
    mutable QMutex _recordedVoiceTestMutex;
    QVariantMap _recordedVoiceTestStatus { { "phase", "idle" }, { "error", "" } };
};

@METHODS@
@SCRIPTING@

static void pump(int duration) {
    QElapsedTimer elapsed; elapsed.start();
    while (elapsed.elapsed() < duration) { QCoreApplication::processEvents(); QThread::msleep(5); }
}
static QByteArray pcm(int16_t value) {
    QByteArray bytes(1920, 0);
    for (int i = 0; i < bytes.size(); i += 2) { std::memcpy(bytes.data() + i, &value, 2); }
    return bytes;
}
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    AudioClient audio;
    AudioScriptingInterface scripting;
    scripting.startRecordedVoiceTest();
    assert(scripting.getRecordedVoiceTestStatus()["error"] == "unsupported");
    scripting.setLocalAudioInterface(&audio);
    audio._isMuted = true;
    audio.startRecordedVoiceTest();
    assert(audio.status["error"] == "microphone-muted" && audio._isMuted && !audio._recordedVoiceTestActive);
    audio._isMuted = false;
    audio._shouldEchoLocally = true;
    audio.startRecordedVoiceTest();
    assert(audio.status["error"] == "live-echo-enabled" && audio._shouldEchoLocally);
    audio._shouldEchoLocally = false;
    audio.input.currentState = QAudio::StoppedState;
    audio.startRecordedVoiceTest();
#if defined(ANDROID_APP_PICO_INTERFACE)
    assert(audio.status["error"] == "input-unavailable");
    audio._androidAudioInputActive = true;
    audio.startRecordedVoiceTest();
    assert(audio._recordedVoiceTestActive);
    audio.cancelRecordedVoiceTest();
    audio._androidAudioInputActive = false;
#endif
    assert(audio.status["error"] == "input-unavailable" || audio.status["phase"] == "cancelled");
    audio.input.currentState = QAudio::ActiveState;
    scripting.startRecordedVoiceTest();
    assert(!audio._recordedVoiceTestActive);  // Native call is queued.
    pump(20);
    assert(scripting.getRecordedVoiceTestStatus()["phase"] == "capturing");
    auto quiet = pcm(100);
    for (int frame = 0; frame < 300; ++frame) { audio.handleLocalEchoAndReverb(quiet); }
    assert(audio._recordedVoiceTest.capturedBytes() == 576000 && audio._recordedVoiceTest.playing());
    assert(audio.output.device.data() == QByteArray(576000, 0));
    // Playback uses the saved input, never the loud microphone feedback.
    audio.output.device.buffer().clear(); audio.output.device.seek(0);
    auto feedback = pcm(30000);
    for (int frame = 0; frame < 300; ++frame) { audio.handleLocalEchoAndReverb(feedback); }
    assert(audio._recordedVoiceTest.finished());
    assert(audio.output.device.data().size() == 576000);
    for (int frame = 0; frame < 20; ++frame) { audio.handleLocalEchoAndReverb(feedback); }
    assert(audio.output.device.data().size() == 576000);  // Native output can become idle.
    int16_t replay = 0; std::memcpy(&replay, audio.output.device.data().constData(), 2);
    assert(replay == 3200);
    pump(800);
    assert(audio.status["phase"] == "completed" && audio.status["playedBytes"] == 576000);
    assert(scripting.getRecordedVoiceTestStatus() == audio.status);
    assert(!audio._recordedVoiceTestActive && audio._recordedVoiceTest.capturedBytes() == 0);
    assert(audio.output.device.data().isEmpty() && !audio._shouldEchoLocally && !audio._isMuted);
    audio.startRecordedVoiceTest();
    auto silence = pcm(0);
    for (int frame = 0; frame < 300; ++frame) { audio.handleLocalEchoAndReverb(silence); }
    assert(audio.status["error"] == "no-microphone-signal" && !audio._recordedVoiceTestActive);
    audio.startRecordedVoiceTest();
    audio.handleLocalEchoAndReverb(quiet);
    scripting.cancelRecordedVoiceTest();
    pump(20);
    assert(audio.status["phase"] == "cancelled" && audio._recordedVoiceTest.capturedBytes() == 0);
    audio.startRecordedVoiceTest();
    audio._audioPaused = true;
    audio.handleLocalEchoAndReverb(quiet);
    assert(audio.status["phase"] == "cancelled" && !audio._recordedVoiceTestActive);
    audio._audioPaused = false;
    audio.startRecordedVoiceTest();
    audio.input.currentError = QAudio::IOError;
    pump(350);
    assert(audio.status["phase"] == "cancelled");
    audio.input.currentError = QAudio::NoError;
    audio.startRecordedVoiceTest();
    audio.output.capacity = 0;
    for (int frame = 0; frame < 26; ++frame) { audio.handleLocalEchoAndReverb(quiet); }
    assert(audio.status["error"] == "playback-queue-overflow");
    audio.output.capacity = 65536;
    audio.startRecordedVoiceTest();
    audio.setLocalEcho(true);
    assert(audio.status["phase"] == "cancelled" && audio._shouldEchoLocally);
    audio.handleLocalEchoAndReverb(quiet);
#if defined(ANDROID_APP_PHONE_INTERFACE)
    // The original phone live-echo API no longer silently records instead.
    assert(audio.output.device.data() == quiet);
#endif
    audio.setLocalEcho(false);
    return 0;
}

#include "voice.moc"
