//
//  Created by Bradley Austin Davis on 2016/12/12
//  Copyright 2013-2016 High Fidelity, Inc.
//  Copyright 2023 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//  SPDX-License-Identifier: Apache-2.0
//
#include "TestScriptingInterface.h"

#include <QtCore/QCoreApplication>
#include <QtCore/QLoggingCategory>
#include <QtCore/QThread>
#if defined(Q_OS_IOS)
#include <QSaveFile>
#endif

#include <shared/FileUtils.h>
#include <shared/QtHelpers.h>
#include <DependencyManager.h>
#include <MainWindow.h>
#include <OffscreenUi.h>
#include <ScriptValue.h>
#include <StatTracker.h>
#include <Trace.h>

#include "Application.h"
#include "NetworkingConstants.h"
#if defined(Q_OS_IOS) && defined(OVERTE_IOS_E2E_TEST_BUILD)
#include "../IOSTouchUiMetrics.h"
#include <QDateTime>
#include <QRegularExpression>
#include <QInputMethod>
#include <QPointer>
#include <QQuickItem>
#include <QTimer>
#include <ui/TabletScriptingInterface.h>
#include <display-plugins/VulkanDisplayPlugin.h>
#include <vk/Context.h>
#include <shared/IOSRuntimeLogging.h>
#endif

#if defined(OVERTE_E2E_VOICE_TESTS)
#include <AudioClient.h>
#include <AudioInjectorManager.h>
#include <IOSAudioPermission.h>
#include <vector>
#include <QCryptographicHash>
#include <QRegularExpression>
#include <QTimer>
#endif

Q_LOGGING_CATEGORY(trace_test, "trace.test")

TestScriptingInterface* TestScriptingInterface::getInstance() {
    static TestScriptingInterface sharedInstance;
    return &sharedInstance;
}

#if defined(Q_OS_IOS) && defined(OVERTE_IOS_E2E_TEST_BUILD)
QVariantMap TestScriptingInterface::iosNativeUiSnapshot() {
    if (_testResultsLocation.isEmpty() ||
            !QCoreApplication::arguments().contains("--testScript")) {
        return { { "schemaVersion", 1 }, { "valid", false } };
    }
    QVariantMap result;
    if (QThread::currentThread() == qApp->thread()) {
        result = observeIOSNativeAccessibility();
    } else {
        QMetaObject::invokeMethod(qApp, [&] { result = observeIOSNativeAccessibility(); },
                                  Qt::BlockingQueuedConnection);
    }
    return result;
}

bool TestScriptingInterface::iosTextTest(const QVariantMap& command) {
    const QString id = command.value("commandId").toString();
    const QString action = command.value("operation").toString();
    const QString directory = _testResultsLocation;
    if (directory.isEmpty() || !QCoreApplication::arguments().contains("--testScript") ||
            command.size() != 4 || command.value("schemaVersion").toInt() != 1 ||
            command.value("action").toString() != "text-fixture" ||
            !QRegularExpression("^ios-[0-9a-f]{32}$").match(id).hasMatch() ||
            (action != "focus" && action != "snapshot" && action != "dismiss")) { return false; }
    return QMetaObject::invokeMethod(qApp, [id, action, directory] {
        static QPointer<QQuickItem> panel;
        static QPointer<QQuickItem> field;
        const auto finish = [id, action, directory](QQuickItem* created = nullptr) {
            if (created) {
                panel = created;
                field = panel->findChild<QQuickItem*>("controlled.text");
            }
            bool ok = panel && field && panel->metaObject()->indexOfProperty("submittedCount") >= 0;
            if (ok && action == "focus") {
                panel->setVisible(true);
                ok = field->setProperty("text", QString());
                field->forceActiveFocus(Qt::OtherFocusReason);
                qGuiApp->inputMethod()->show();
            } else if (ok && action == "dismiss") {
                field->setFocus(false);
                panel->setFocus(false);
                panel->setVisible(false);
                qGuiApp->inputMethod()->hide();
            }
            QVariantMap result { {"schemaVersion", 1}, {"commandId", id}, {"ok", ok},
                {"processId", QCoreApplication::applicationPid()},
                {"sampleEpochMs", QDateTime::currentMSecsSinceEpoch()} };
            if (ok && DependencyManager::isSet<TabletScriptingInterface>()) {
                const auto metrics = DependencyManager::get<TabletScriptingInterface>()->getTouchUiRuntimeMetrics();
                if (!metrics.value("valid").toBool()) { result["ok"] = false; }
                else {
                    result["snapshot"] = QVariantMap { {"schemaVersion", 1},
                        {"value", field->property("text").toString()},
                        {"focused", field->hasActiveFocus()},
                        {"keyboardVisible", metrics.value("keyboardVisible").toBool()},
                        {"submittedCount", panel->property("submittedCount").toInt()} };
                }
            } else { result["ok"] = false; }
            QSaveFile output(QDir(directory).absoluteFilePath("ios-text-observation.json"));
            output.setDirectWriteFallback(false);
            const auto bytes = QJsonDocument::fromVariant(result).toJson(QJsonDocument::Compact);
            if (output.open(QIODevice::WriteOnly)) {
                output.setPermissions(QFile::ReadOwner | QFile::WriteOwner);
                if (output.write(bytes) == bytes.size()) { output.commit(); }
            }
        };
        if (!DependencyManager::isSet<OffscreenUi>()) { finish(); return; }
        if (action == "focus" && !panel) {
            DependencyManager::get<OffscreenUi>()->load(QUrl("qrc:/qml/hifi/ControlledTextInput.qml"),
                [finish](QQmlContext*, QQuickItem* created) {
                    QPointer<QQuickItem> guarded(created);
                    QTimer::singleShot(0, qApp, [finish, guarded] { finish(guarded); });
                });
        } else { finish(); }
    }, Qt::QueuedConnection);
}

QVariantMap TestScriptingInterface::iosRenderObservation() {
    if (_testResultsLocation.isEmpty() || !QCoreApplication::arguments().contains("--testScript")) {
        return { {"schemaVersion", 1}, {"valid", false} };
    }
    QVariantMap result;
    const auto observe = [&] {
        const auto plugin = qApp->getActiveDisplayPlugin();
        const auto* vulkan = plugin ? dynamic_cast<VulkanDisplayPlugin*>(plugin.get()) : nullptr;
        const auto device = vks::Context::get().device;
        const auto frame = iosRuntimeEntityEvidenceSnapshot();
        const bool hardware = device && (device->properties.deviceType == VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU ||
            device->properties.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU);
        result = { {"schemaVersion", 1}, {"valid", vulkan && device && frame.armed && frame.committed && !frame.capacityExceeded},
            {"processId", QCoreApplication::applicationPid()}, {"sampleEpochMs", QDateTime::currentMSecsSinceEpoch()},
            {"backend", QString("Vulkan/MoltenVK")}, {"hardwareAccelerated", hardware},
            {"surfaceVisible", qApp->applicationState() == Qt::ApplicationActive && qApp->getWindow() && qApp->getWindow()->isVisible()},
            {"generation", QString::number(frame.generation)},
            {"acceptedPresentCalls", QString::number(frame.acceptedPresentCalls)},
            {"frameSequence", frame.lastPresentedFrame} };
    };
    if (QThread::currentThread() == qApp->thread()) { observe(); }
    else { QMetaObject::invokeMethod(qApp, observe, Qt::BlockingQueuedConnection); }
    return result;
}

#endif

#if defined(OVERTE_E2E_VOICE_TESTS)
QVariantMap TestScriptingInterface::voiceTest(const QVariantMap& command) {
    if (QThread::currentThread() != thread()) {
        QVariantMap result;
        QMetaObject::invokeMethod(this, [&] { result = voiceTest(command); }, Qt::BlockingQueuedConnection);
        return result;
    }
    const QString id = command.value("commandId").toString();
    QVariantMap result { { "schemaVersion", 1 }, { "commandId", id }, { "ok", false } };
    // Both an explicit test build and an active test-script launch are required.
    if (_testResultsLocation.isEmpty() || !QCoreApplication::arguments().contains("--testScript") ||
        command.value("schemaVersion").toInt() != 1 ||
        !QRegularExpression("^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$").match(id).hasMatch()) {
        result["error"] = "voice-test-not-enabled";
        return result;
    }
    auto audio = DependencyManager::get<AudioClient>();
    const auto onAudio = [&](const std::function<void()>& callback) {
        if (QThread::currentThread() == audio->thread()) { callback(); }
        else { QMetaObject::invokeMethod(audio.data(), callback, Qt::BlockingQueuedConnection); }
    };
    const auto appendAudioStatus = [&] {
        onAudio([&] {
            const auto status = audio->voiceTestStatus();
            for (auto it = status.cbegin(); it != status.cend(); ++it) { result[it.key()] = it.value(); }
        });
    };
    const QString action = command.value("action").toString();
    if (_acousticPrepared && action != "status") {
        result["error"] = "acoustic-test-busy";
        return result;
    }
    if (action == "prepare") {
        if (audio->getRecording() || !_voiceCapturePath.isEmpty()) {
            result["error"] = "voice-recording-busy";
            return result;
        }
        bool prepared = false;
        onAudio([&] { prepared = audio->prepareVoiceTest(); });
        if (!prepared) { result["error"] = "voice-source-unavailable"; appendAudioStatus(); return result; }
    } else if (action == "send") {
        const QString challenge = command.value("challenge").toString();
        if (!QRegularExpression("^[0-9a-f]{32}$").match(challenge).hasMatch()) {
            result["error"] = "voice-invalid-challenge";
            return result;
        }
        const QByteArray digest = QCryptographicHash::hash("overte-voice-v1:" + challenge.toLatin1(), QCryptographicHash::Sha256);
        std::array<int, 12> symbols;
        symbols[0] = static_cast<unsigned char>(digest[0]) % 8;
        for (int i = 1; i < 12; ++i) { symbols[i] = (symbols[i - 1] + 1 + static_cast<unsigned char>(digest[i]) % 7) % 8; }
        bool sent = false;
        onAudio([&] { sent = audio->sendVoiceTest(symbols); });
        if (!sent) { result["error"] = "voice-send-unavailable"; appendAudioStatus(); return result; }
    } else if (action == "capture-start") {
        const int seconds = command.value("seconds").toInt();
        if (seconds < 6 || seconds > 10 || audio->getRecording() || !_voiceCapturePath.isEmpty()) {
            result["error"] = "voice-invalid-capture";
            return result;
        }
        QDir directory(_testResultsLocation);
        if (!directory.exists()) { result["error"] = "voice-results-unavailable"; return result; }
        _voiceCapturePath = directory.absoluteFilePath("voice-" + id + ".wav");
        // Never overwrite an unrelated or stale recording.
        if (QFile::exists(_voiceCapturePath) || !audio->startRecording(_voiceCapturePath)) {
            _voiceCapturePath.clear();
            result["error"] = "voice-capture-unavailable";
            return result;
        }
        QFile::setPermissions(_voiceCapturePath, QFile::ReadOwner | QFile::WriteOwner);
        const quint64 generation = ++_voiceCaptureGeneration;
        QTimer::singleShot(seconds * 1000, this, [this, audio, generation] {
            if (_voiceCaptureGeneration == generation && !_voiceCapturePath.isEmpty()) { audio->stopRecording(); }
        });
        QTimer::singleShot((seconds + 30) * 1000, this, [this, audio, generation] {
            if (_voiceCaptureGeneration == generation && !_voiceCapturePath.isEmpty()) {
                audio->stopRecording();
                QFile::remove(_voiceCapturePath);
                _voiceCapturePath.clear();
            }
        });
    } else if (action == "capture-stop") {
        if (_voiceCapturePath.isEmpty()) { result["error"] = "voice-no-capture"; return result; }
        audio->stopRecording();
        QFile capture(_voiceCapturePath);
        if (!capture.open(QIODevice::ReadOnly) || capture.size() > 5 * 1024 * 1024) {
            result["error"] = "voice-capture-invalid";
        } else {
            const QByteArray wav = capture.readAll();
            result["wavBase64"] = QString::fromLatin1(wav.toBase64());
            result["sha256"] = QString::fromLatin1(QCryptographicHash::hash(wav, QCryptographicHash::Sha256).toHex());
            result["ok"] = true;
        }
        capture.close();
        QFile::remove(_voiceCapturePath);
        _voiceCapturePath.clear();
        ++_voiceCaptureGeneration;
        return result;
    } else if (action == "reset") {
        onAudio([&] { audio->resetVoiceTest(); });
        if (!_voiceCapturePath.isEmpty()) { audio->stopRecording(); QFile::remove(_voiceCapturePath); _voiceCapturePath.clear(); }
        ++_voiceCaptureGeneration;
    } else if (action != "status") {
        result["error"] = "voice-invalid-action";
        return result;
    }
    onAudio([&] { audio->touchVoiceTest(); });
    appendAudioStatus();
    result["ok"] = true;
    return result;
}

QVariantMap TestScriptingInterface::acousticTest(const QVariantMap& command) {
    if (QThread::currentThread() != thread()) {
        QVariantMap result;
        QMetaObject::invokeMethod(this, [&] { result = acousticTest(command); }, Qt::BlockingQueuedConnection);
        return result;
    }
    const QString id = command.value("commandId").toString();
    QVariantMap result { { "schemaVersion", 1 }, { "commandId", id }, { "ok", false } };
#if !defined(Q_OS_IOS)
    result["error"] = "acoustic-test-requires-ios";
    return result;
#else
    if (_testResultsLocation.isEmpty() || !QCoreApplication::arguments().contains("--testScript") ||
            command.value("schemaVersion").toInt() != 1 ||
            !QRegularExpression("^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$").match(id).hasMatch()) {
        result["error"] = "acoustic-test-not-enabled";
        return result;
    }
    const QString action = command.value("action").toString();
    QStringList fields { "schemaVersion", "commandId", "action" };
    if (action == "capture-start") { fields << "seconds" << "challenge"; }
    if (action == "play") { fields << "challenge"; }
    fields.sort();
    if (command.keys() != fields) { result["error"] = "acoustic-invalid-command"; return result; }
    auto audio = DependencyManager::get<AudioClient>();
    const auto onAudio = [&](const std::function<void()>& callback) {
        if (QThread::currentThread() == audio->thread()) { callback(); }
        else { QMetaObject::invokeMethod(audio.data(), callback, Qt::BlockingQueuedConnection); }
    };
    const auto appendStatus = [&] {
        onAudio([&] {
            const auto voice = audio->voiceTestStatus();
            const auto capture = audio->acousticCaptureStatus();
            for (auto it = voice.cbegin(); it != voice.cend(); ++it) { result[it.key()] = it.value(); }
            for (auto it = capture.cbegin(); it != capture.cend(); ++it) { result[it.key()] = it.value(); }
        });
        const auto route = overteIOSAcousticTestState();
        result["builtInMicrophone"] = route.builtInMicrophone;
        result["builtInSpeaker"] = route.builtInSpeaker;
        result["measurementMode"] = route.measurementMode;
        result["outputVolume"] = route.outputVolume;
        result["physicalDevice"] = route.physicalDevice;
        result["outputRevision"] = QVariant::fromValue(overteIOSAudioOutputRevision());
        result["prepared"] = _acousticPrepared;
        result["challenge"] = _acousticChallenge;
        result["playing"] = _acousticInjector && _acousticInjector->isPlaying();
        result["captureSource"] = "physical-device-input-before-processing";
    };
    appendStatus();
    if (action == "reset") {
        if (_acousticInjector) {
            DependencyManager::get<AudioInjectorManager>()->stop(_acousticInjector);
            _acousticInjector.clear();
        }
        onAudio([&] { audio->resetAcousticCapture(); });
        const bool restored = !_acousticPrepared || overteIOSSetAcousticTestMode(false);
        // Retain ownership after a failed restore so the caller/watchdog can retry.
        _acousticPrepared = !restored;
        _acousticChallenge.clear();
        ++_acousticGeneration;
        result["ok"] = restored;
        appendStatus();
        return result;
    }
    // Read-only status must remain available while the OS dialog owns the
    // foreground, so the probe can wait without starting or changing audio.
    if (action == "status") { result["ok"] = true; return result; }
    const auto& domain = DependencyManager::get<NodeList>()->getDomainHandler();
    // A loaded serverless scene also sets isConnected(). Only an actual
    // domain-server connection can send this test's input to a remote mixer.
    if (result.value("sourceEnabled").toBool() || result.value("sourceClockActive").toBool() ||
            !result.value("iosForeground").toBool() || result.value("iosInterrupted").toBool() ||
            (domain.isConnected() && !domain.isServerless())) {
        result["error"] = "acoustic-unsafe-audio-state";
        return result;
    }
    if (action == "prepare") {
        if (_acousticPrepared || audio->getRecording() || !_voiceCapturePath.isEmpty() ||
                !result.value("iosCaptureAllowed").toBool() ||
                !result.value("physicalDevice").toBool() ||
                !result.value("builtInMicrophone").toBool() || !result.value("builtInSpeaker").toBool()) {
            result["error"] = "acoustic-prepare-unavailable";
            return result;
        }
        _acousticPrepared = true;
        if (!overteIOSSetAcousticTestMode(true)) {
            acousticTest({ { "schemaVersion", 1 }, { "commandId", "acoustic-failed-prepare" }, { "action", "reset" } });
            result["error"] = "acoustic-measurement-unavailable";
            return result;
        }
        const auto generation = ++_acousticGeneration;
        QTimer::singleShot(45000, this, [this, generation] {
            if (_acousticPrepared && generation == _acousticGeneration) {
                acousticTest({ { "schemaVersion", 1 }, { "commandId", "acoustic-watchdog" }, { "action", "reset" } });
            }
        });
    } else if (action == "capture-start") {
        const QString challenge = command.value("challenge").toString();
        if (!_acousticPrepared || !QRegularExpression("^[0-9a-f]{32}$").match(challenge).hasMatch()) {
            result["error"] = "acoustic-invalid-challenge";
            return result;
        }
        bool started = false;
        onAudio([&] { started = audio->startAcousticCapture(command.value("seconds").toInt()); });
        if (!started) { result["error"] = "acoustic-capture-unavailable"; return result; }
        _acousticChallenge = challenge;
    } else if (action == "play") {
        if (!_acousticPrepared || _acousticChallenge.isEmpty() ||
                command.value("challenge").toString() != _acousticChallenge || _acousticInjector ||
                !result.value("captureActive").toBool() || !result.value("builtInMicrophone").toBool() ||
                !result.value("builtInSpeaker").toBool() || !result.value("measurementMode").toBool() ||
                result.value("outputVolume").toFloat() <= 0.0f) {
            result["error"] = "acoustic-play-unavailable";
            return result;
        }
        const QByteArray digest = QCryptographicHash::hash("overte-voice-v1:" + _acousticChallenge.toLatin1(), QCryptographicHash::Sha256);
        std::array<int, 12> symbols;
        symbols[0] = static_cast<unsigned char>(digest[0]) % 8;
        for (int i = 1; i < 12; ++i) { symbols[i] = (symbols[i - 1] + 1 + static_cast<unsigned char>(digest[i]) % 7) % 8; }
        // Use the known waveform only as LOCAL SPEAKER OUTPUT. Never enable
        // AudioClient's synthetic input or feed this PCM into the capture.
        VoiceTestSignal output;
        static_assert(VoiceTestSignal::RATE == AudioConstants::SAMPLE_RATE, "acoustic output sample rate");
        output.send(symbols);
        std::vector<int16_t> pcm(VoiceTestSignal::FRAMES);
        output.replace(pcm.data(), VoiceTestSignal::FRAMES, 1);
        AudioInjectorOptions options;
        options.localOnly = true;
        // Non-spatial playback uses the system gain and cannot be attenuated
        // by the avatar's distance from the default world-origin position.
        options.positionSet = false;
        options.volume = 1.0f;
        _acousticInjector = DependencyManager::get<AudioInjectorManager>()->playSound(
            AudioData::make(static_cast<uint32_t>(pcm.size()), 1, pcm.data()), options);
        if (!_acousticInjector) { result["error"] = "acoustic-output-unavailable"; return result; }
    } else if (action == "capture-stop") {
        if (!_acousticPrepared) { result["error"] = "acoustic-session-unprepared"; return result; }
        QByteArray wav;
        onAudio([&] { wav = audio->takeAcousticCapture(); });
        if (wav.isEmpty()) { result["error"] = "acoustic-capture-incomplete"; return result; }
        result["wavBase64"] = QString::fromLatin1(wav.toBase64());
        result["sha256"] = QString::fromLatin1(QCryptographicHash::hash(wav, QCryptographicHash::Sha256).toHex());
        // Preserve the completed capture's status; takeAcousticCapture clears it.
        result["ok"] = true;
        return result;
    } else { result["error"] = "acoustic-invalid-action"; return result; }
    appendStatus();
    result["ok"] = true;
    return result;
#endif
}
#endif

void TestScriptingInterface::quit() {
    qApp->quit();
}

void TestScriptingInterface::waitForTextureIdle() {
    waitForCondition(0, []()->bool {
        return (0 == gpu::Context::getTexturePendingGPUTransferCount());
    });
}

void TestScriptingInterface::waitForDownloadIdle() {
    waitForCondition(0, []()->bool {
        return (0 == ResourceCache::getLoadingRequestCount()) && (0 == ResourceCache::getPendingRequestCount());
    });
}

void TestScriptingInterface::waitForProcessingIdle() {
    auto statTracker = DependencyManager::get<StatTracker>();
    waitForCondition(0, [statTracker]()->bool {
        return (0 == statTracker->getStat("Processing").toInt() && 0 == statTracker->getStat("PendingProcessing").toInt());
    });
}

void TestScriptingInterface::waitIdle() {
    // Initial wait for some incoming work
    QThread::sleep(1);
    waitForDownloadIdle();
    waitForProcessingIdle();
    waitForTextureIdle();
}

bool TestScriptingInterface::loadTestScene(QString scene) {
    if (QThread::currentThread() != thread()) {
        bool result;
        BLOCKING_INVOKE_METHOD(this, "loadTestScene", Q_RETURN_ARG(bool, result), Q_ARG(QString, scene));
        return result;
    }

    static const QString TEST_ROOT = "https://raw.githubusercontent.com/hifi-archive/hifi_tests/master/";
    static const QString TEST_BINARY_ROOT = NetworkingConstants::HF_CONTENT_CDN_URL + "test_scene_data/";
    static const QString TEST_SCRIPTS_ROOT = TEST_ROOT + "scripts/";
    static const QString TEST_SCENES_ROOT = TEST_ROOT + "scenes/";
    
    DependencyManager::get<ResourceManager>()->setUrlPrefixOverride("atp:/", TEST_BINARY_ROOT + scene + ".atp/");
    auto tree = qApp->getEntities()->getTree();
    auto treeIsClient = tree->getIsClient();
    // Force the tree to accept the load regardless of permissions
    tree->setIsClient(false);
    auto result = tree->readFromURL(TEST_SCENES_ROOT + scene + ".json");
    tree->setIsClient(treeIsClient);
    return result;
}

bool TestScriptingInterface::startTracing(QString logrules) {
    if (!logrules.isEmpty()) {
        QLoggingCategory::setFilterRules(logrules);
    }

    if (!DependencyManager::isSet<tracing::Tracer>()) {
        return false;
    }

    DependencyManager::get<tracing::Tracer>()->startTracing();
    return true;
}

bool TestScriptingInterface::stopTracing(QString filename) {
    if (!DependencyManager::isSet<tracing::Tracer>()) {
        return false;
    }

    auto tracer = DependencyManager::get<tracing::Tracer>();
    tracer->stopTracing();
    tracer->serialize(filename);
    return true;
}

void TestScriptingInterface::clear() {
    qApp->postLambdaEvent([] {
        qApp->getEntities()->clear();
    });
}

bool TestScriptingInterface::waitForConnection(qint64 maxWaitMs) {
    // Wait for any previous connection to die
    QThread::sleep(1);
    return waitForCondition(maxWaitMs, []()->bool {
        return DependencyManager::get<NodeList>()->getDomainHandler().isConnected();
    });
}

void TestScriptingInterface::wait(int milliseconds) {
    QThread::msleep(milliseconds);
}

bool TestScriptingInterface::waitForCondition(qint64 maxWaitMs, std::function<bool()> condition) {
    QElapsedTimer elapsed;
    elapsed.start();
    while (!condition()) {
        if (maxWaitMs > 0 && elapsed.elapsed() > maxWaitMs) {
            return false;
        }
        QThread::msleep(1);
    }
    return condition();
}

void TestScriptingInterface::startTraceEvent(QString name) {
    tracing::traceEvent(trace_test(), name, tracing::DurationBegin, "");
}

void TestScriptingInterface::endTraceEvent(QString name) {
    tracing::traceEvent(trace_test(), name, tracing::DurationEnd);
}

void TestScriptingInterface::savePhysicsSimulationStats(QString originalPath) {
    QString path = FileUtils::replaceDateTimeTokens(originalPath);
    path = FileUtils::computeDocumentPath(path);
    if (!FileUtils::canCreateFile(path)) {
        return;
    }
    qApp->saveNextPhysicsStats(path);
}

void TestScriptingInterface::profileRange(const QString& name, const ScriptValue& fn) {
    PROFILE_RANGE(script, name);
    fn.call();
}

void TestScriptingInterface::clearCaches() {
	qApp->reloadResourceCaches();
}

// Writes a JSON object from javascript to a file
void TestScriptingInterface::saveObject(QVariant variant, const QString& filename) {
    if (_testResultsLocation.isNull()) {
        return;
    }

    QJsonDocument jsonDocument;
    jsonDocument = QJsonDocument::fromVariant(variant);
    if (jsonDocument.isNull()) {
        return;
    }

    QByteArray jsonData = jsonDocument.toJson();

    // Append trailing slash if needed
    if (_testResultsLocation.right(1) != "/") {
        _testResultsLocation += "/";
    }

    QString filepath = QDir::cleanPath(_testResultsLocation + filename);
#if defined(Q_OS_IOS)
    // Native AFC readers may open this path between samples. Publish a whole
    // new file atomically so neither truncation nor an old size/new body pair
    // can expose incomplete test observations.
    QSaveFile file(filepath);
    file.setDirectWriteFallback(false);
    if (!file.open(QIODevice::WriteOnly) || file.write(jsonData) != jsonData.size()
            || !file.commit()) {
        qCWarning(trace_test) << "iOS test observation publication failed";
    }
#else
    QFile file(filepath);

    file.open(QFile::WriteOnly);
    file.write(jsonData);
    file.close();
#endif
}

void TestScriptingInterface::showMaximized() {
    qApp->getWindow()->showMaximized();
}

void TestScriptingInterface::setOtherAvatarsReplicaCount(int count) {
    qApp->setOtherAvatarsReplicaCount(count);
}

int TestScriptingInterface::getOtherAvatarsReplicaCount() {
    return qApp->getOtherAvatarsReplicaCount();
}

void TestScriptingInterface::setMinimumGPUTextureMemStabilityCount(int count) {
    QMetaObject::invokeMethod(qApp, "setMinimumGPUTextureMemStabilityCount", Qt::DirectConnection, Q_ARG(int, count));
}

bool TestScriptingInterface::isTextureLoadingComplete() {
    bool result;
    QMetaObject::invokeMethod(qApp, "gpuTextureMemSizeStable", Qt::DirectConnection, Q_RETURN_ARG(bool, result));
    return result;
}
