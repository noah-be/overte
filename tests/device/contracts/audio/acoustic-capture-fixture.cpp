// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QTimer>
#include <QThread>
#include <QVariantMap>
#include <QCryptographicHash>
#include <QRegularExpression>
#include <QSharedPointer>
#include <functional>
#include <memory>
#include <vector>
#include "AcousticTestCapture.h"
#include "VoiceTestSignal.h"
#include "IOSAudioPermission.h"
#include <cassert>
#define Q_OS_IOS 1

namespace QAudio { enum State { ActiveState, SuspendedState, StoppedState, IdleState }; enum Error { NoError }; }
namespace AudioConstants { constexpr int SAMPLE_RATE = 24000; }
struct QAudioFormat {
    enum SampleFormat { Int16 };
    int rate { 24000 }, channels { 1 };
    int sampleRate() const { return rate; }
    int channelCount() const { return channels; }
    SampleFormat sampleFormat() const { return Int16; }
};
struct Input { QAudio::State state() const { return QAudio::ActiveState; } QAudio::Error error() const { return QAudio::NoError; } };
overte::audio::IOSAcousticTestState route { true, true, true, 0.5f, true };
overte::audio::IOSVoiceTestState native {overte::audio::Permission::Granted,overte::audio::Outcome::Capturing,true,false,true};
quint64 revision = 1;
auto overteIOSAcousticTestState() -> overte::audio::IOSAcousticTestState { return route; }
auto overteIOSVoiceTestState() -> overte::audio::IOSVoiceTestState { return native; }
std::uint64_t overteIOSAudioOutputRevision() { return revision; }
bool overteIOSMicrophonePermissionGranted() { return native.captureAllowed; }
bool restoreModeSucceeds = true;
bool overteIOSSetAcousticTestMode(bool enabled) {
    if (!enabled && !restoreModeSucceeds) { return false; }
    route.measurementMode = enabled; ++revision; return true;
}
class AudioClient : public QObject {
public:
    bool startAcousticCapture(int);
    QVariantMap acousticCaptureStatus() const;
    QByteArray takeAcousticCapture();
    void resetAcousticCapture();
    void processMicAudioInput(QByteArray&);
    bool voiceTestLifecycleAllowed() const { return native.foreground && !native.interrupted; }
    bool getLocalEcho() const { return localEcho; }
    bool getServerEcho() const { return serverEcho; }
    bool getRecording() const { return false; }
    QVariantMap voiceTestStatus() const {
        return { {"sourceEnabled",_voiceTestInputEnabled}, {"sourceClockActive",_voiceTestInputEnabled},
                 {"iosForeground",native.foreground}, {"iosInterrupted",native.interrupted},
                 {"iosCaptureAllowed",native.captureAllowed} };
    }
    bool _voiceTestInputEnabled { false }, _isMuted { false }, localEcho { false }, serverEcho { false };
    VoiceTestSignal _voiceTestSignal;
    Input input;
    Input* _audioInput { &input };
    void* _inputDevice { &input };
    QAudioFormat _inputFormat;
    AcousticTestCapture _acousticCapture;
    quint64 _acousticCaptureGeneration { 0 }, _acousticOutputRevision { 0 }, _voiceTestMicCallbacks { 0 };
};
CAPTURE_METHODS
PHYSICAL_INPUT_WIRING

class AudioData {
public:
    std::vector<int16_t> pcm;
    static std::shared_ptr<const AudioData> make(uint32_t size, uint32_t channels, const int16_t* samples) {
        assert(channels == 1);
        auto result = std::make_shared<AudioData>();
        result->pcm.assign(samples, samples + size);
        return result;
    }
};
struct AudioInjectorOptions { bool localOnly { false }, positionSet { true }; float volume { 0.0f }; };
class AudioInjector { public: bool active { true }; bool isPlaying() const { return active; } };
class AudioInjectorManager {
public:
    std::shared_ptr<const AudioData> played;
    QSharedPointer<AudioInjector> playSound(std::shared_ptr<const AudioData> data, const AudioInjectorOptions& options) {
        assert(options.localOnly && !options.positionSet && options.volume == 1.0f);
        played = data;
        return QSharedPointer<AudioInjector>::create();
    }
    void stop(const QSharedPointer<AudioInjector>& injector) { injector->active = false; }
};
struct DomainHandler {
    bool connected { true }, serverless { true };
    bool isConnected() const { return connected; }
    bool isServerless() const { return serverless; }
};
struct NodeList { DomainHandler domain; const DomainHandler& getDomainHandler() const { return domain; } };
struct DependencyManager {
    template<class T> static QSharedPointer<T> get() { static auto instance = QSharedPointer<T>::create(); return instance; }
};
class TestScriptingInterface : public QObject {
public:
    QString _testResultsLocation, _voiceCapturePath, _acousticChallenge;
    bool _acousticPrepared { false };
    quint64 _acousticGeneration { 0 };
    QSharedPointer<AudioInjector> _acousticInjector;
    QVariantMap acousticTest(const QVariantMap&);
};
ACOUSTIC_API

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    AudioClient audio;
    assert(audio.startAcousticCapture(8));
    assert(!audio.startAcousticCapture(8));
    QByteArray chunk(240 * 2, '\x01');
    for (int i = 0; i < 800; ++i) { audio.processMicAudioInput(chunk); }
    assert(audio.acousticCaptureStatus()["captureComplete"].toBool());
    assert(audio.acousticCaptureStatus()["physicalInputCallbacks"].toInt() == 800);
    const auto wav = audio.takeAcousticCapture();
    assert(wav.size() == 44 + 8 * 24000 * 2);
    assert(wav.startsWith("RIFF") && wav.mid(8, 4) == "WAVE" && wav.mid(44) == QByteArray(8 * 24000 * 2, '\x01'));
    assert(!audio.acousticCaptureStatus()["captureComplete"].toBool());
    assert(audio.takeAcousticCapture().isEmpty());

    audio._voiceTestInputEnabled = true;
    assert(!audio.startAcousticCapture(8));
    audio._voiceTestInputEnabled = false;
    route.builtInSpeaker = false;
    assert(!audio.startAcousticCapture(8));
    route.builtInSpeaker = true;
    native.captureAllowed = false;
    assert(!audio.startAcousticCapture(8));
    native.captureAllowed = true;
    audio.localEcho = true;
    assert(!audio.startAcousticCapture(8));
    audio.localEcho = false;
    assert(!audio.startAcousticCapture(100));

    assert(audio.startAcousticCapture(8));
    audio.processMicAudioInput(chunk);
    ++revision;
    audio.processMicAudioInput(chunk);
    assert(audio.acousticCaptureStatus()["captureInvalid"].toBool());
    assert(audio.takeAcousticCapture().isEmpty());
    assert(audio.startAcousticCapture(8));
    audio._inputFormat.rate = 48000;
    audio.processMicAudioInput(chunk);
    assert(audio.takeAcousticCapture().isEmpty());
    audio._inputFormat.rate = 24000;
    assert(audio.startAcousticCapture(8));
    audio._voiceTestInputEnabled = true;
    audio.processMicAudioInput(chunk);
    assert(audio.takeAcousticCapture().isEmpty());
    audio._voiceTestInputEnabled = false;
    assert(audio.startAcousticCapture(8));
    native.captureAllowed = false;
    audio.processMicAudioInput(chunk);
    assert(audio.takeAcousticCapture().isEmpty());
    native.captureAllowed = true;
    assert(audio.startAcousticCapture(8));
    audio.processMicAudioInput(chunk);
    assert(audio.takeAcousticCapture().isEmpty()); // short input cannot pass

    AcousticTestCapture bounded;
    assert(bounded.start(48000, 2, 6));
    bounded.append(QByteArray(3 * 1024 * 1024, 0), 48000, 2);
    assert(bounded.complete() && bounded.bytes() == 6 * 48000 * 4);
    bounded.reset();
    assert(bounded.start(48000, 2, 6));
    bounded.append(QByteArray(1, 0), 48000, 2);
    assert(bounded.invalid() && bounded.wav().isEmpty());

    TestScriptingInterface test;
    QVariantMap command { {"schemaVersion",1}, {"commandId","fresh"}, {"action","prepare"} };
    assert(!test.acousticTest(command)["ok"].toBool()); // test-script launch alone is insufficient
    test._testResultsLocation = "fixture-results";
    native.foreground = false;
    command["action"] = "status";
    assert(test.acousticTest(command)["ok"].toBool()); // read-only observation while a permission dialog owns foreground
    command["action"] = "prepare";
    assert(!test.acousticTest(command)["ok"].toBool());
    native.foreground = true;
    native.captureAllowed = false;
    assert(!test.acousticTest(command)["ok"].toBool());
    native.captureAllowed = true;
    route.physicalDevice = false;
    assert(!test.acousticTest(command)["ok"].toBool());
    route.physicalDevice = true;
    DependencyManager::get<NodeList>()->domain.connected = true;
    DependencyManager::get<NodeList>()->domain.serverless = false;
    assert(!test.acousticTest(command)["ok"].toBool());
    // connectedToServerless() marks a local scene as connected too. It must
    // remain usable while an actual domain-server connection remains refused.
    DependencyManager::get<NodeList>()->domain.serverless = true;
    auto physical = DependencyManager::get<AudioClient>();
    physical->_voiceTestInputEnabled = true;
    assert(!test.acousticTest(command)["ok"].toBool());
    physical->_voiceTestInputEnabled = false;
    assert(test.acousticTest(command)["ok"].toBool());
    assert(!test.acousticTest(command)["ok"].toBool()); // overlapping owner
    command["action"] = "capture-start";
    command["seconds"] = 8;
    command["challenge"] = "0123456789abcdef0123456789abcdef";
    assert(test.acousticTest(command)["ok"].toBool());
    assert(!test.acousticTest(command)["ok"].toBool());
    command.remove("seconds"); command["action"] = "play";
    const auto output = test.acousticTest(command);
    assert(output["ok"].toBool() && output["playing"].toBool());
    assert(!physical->_voiceTestInputEnabled && !physical->_voiceTestSignal.active());
    const auto speaker = DependencyManager::get<AudioInjectorManager>()->played;
    assert(speaker && speaker->pcm.size() == VoiceTestSignal::FRAMES);
    assert(speaker->pcm[12100] != 0);
    assert(physical->_acousticCapture.bytes() == 0); // output is never a capture source
    for (int i = 0; i < 800; ++i) { physical->processMicAudioInput(chunk); }
    command.remove("challenge"); command["action"] = "capture-stop";
    const auto recorded = test.acousticTest(command);
    assert(recorded["ok"].toBool() && recorded["physicalInputCallbacks"].toInt() == 800);
    assert(QByteArray::fromBase64(recorded["wavBase64"].toByteArray()).mid(44) == QByteArray(8 * 24000 * 2, '\x01'));
    assert(!test.acousticTest(command)["ok"].toBool());
    command["action"] = "reset";
    restoreModeSucceeds = false;
    assert(!test.acousticTest(command)["ok"].toBool() && test._acousticPrepared);
    restoreModeSucceeds = true;
    assert(test.acousticTest(command)["ok"].toBool() && !test._acousticPrepared);
    assert(!route.measurementMode && !test._acousticInjector);
    assert(test.acousticTest(command)["ok"].toBool()); // cleanup is idempotent
    return 0;
}
