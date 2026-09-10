#include <QtCore/QCoreApplication>
#include <QtCore/QDebug>
#include <QtCore/QStringList>
#include "security/redaction/SafeDiagnostics.h"
#include <cassert>

static QStringList messages;
static void capture(QtMsgType, const QMessageLogContext&, const QString& message) { messages.append(message); }
// Explicit diagnostic-expression boundaries, not audio/native behavior mocks.
namespace QAudio { enum State { ActiveState, StoppedState }; enum Error { NoError }; }
struct AudioState {
    QAudio::State state() const { return QAudio::ActiveState; }
    QAudio::Error error() const { return QAudio::NoError; }
};
struct Format {
    int sampleRate() const { return 48000; }
    int channelCount() const { return 1; }
    int sampleSize() const { return 16; }
};

static int hifiAudioSampleSize(const Format& format) { return format.sampleSize(); }

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    auto previous = qInstallMessageHandler(capture);
    const QString canary("private-device-id / private-user/capture.wav");
    qInfo().noquote() << canary;
    qWarning().noquote() << canary;
    assert(messages.size() == 2 && messages[0] == canary && messages[1] == canary);
    messages.clear();
    AudioState input;
    auto _audioInput = &input;
    Format _inputFormat;
    const quint64 gateTraceBlocks = 10, gateTraceOpenBlocks = 3, traceFrames = 5;
    const double traceLoudnessTotal = 2, traceLoudnessPeak = 1, _noiseReductionThreshold = 0.2;
    const bool _isNoiseGateEnabled = true, _isNoiseReductionAutomatic = false, _isMuted = false;
    const int captureSeconds = 1, _inputReadsSinceLastCheck = 2;
    const bool _androidAudioInputActive = true;
    const quint64 androidCapturedCallbacks = 2;
    // Complete original statements, including original conditional watchdog
    // streaming. No device-name/path getter is declared or replaced here.
#include "trace-sinks.inc"
    assert(messages.size() == 11);
    for (const auto& message : messages) {
        assert(message.startsWith("PICO_MIC_") && message.contains("OVT_REDACTED"));
        assert(!message.contains(canary) && !message.contains("capture.wav"));
    }
    qInstallMessageHandler(previous);
}
