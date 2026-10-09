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

#if defined(OVERTE_E2E_VOICE_TESTS)
#include <AudioClient.h>
#include <QCryptographicHash>
#include <QRegularExpression>
#include <QTimer>
#include <QSaveFile>
#include <QDateTime>
#include <QJsonObject>
#include <QJsonArray>
#include <QAccessible>
#include <QInputMethod>
#include <QQmlProperty>
#include <QQmlEngine>
#include <functional>
#if defined(Q_OS_ANDROID)
#include <QtAndroidExtras/QAndroidJniObject>
#endif
#include <ui/PhoneTextInputFixture.h>
#include <ui/TabletScriptingInterface.h>
#endif

Q_LOGGING_CATEGORY(trace_test, "trace.test")

TestScriptingInterface* TestScriptingInterface::getInstance() {
    static TestScriptingInterface sharedInstance;
    return &sharedInstance;
}

#if defined(OVERTE_E2E_VOICE_TESTS)
bool TestScriptingInterface::uiTest(const QVariantMap& command) {
    const QString id = command.value("commandId").toString();
    const QString action = command.value("operation").toString();
    const QString outputDirectory = _testResultsLocation;
    if (outputDirectory.isEmpty() || !QCoreApplication::arguments().contains("--testScript")
            || command.size() != 4 || command.value("schemaVersion").toInt() != 1
            || command.value("action").toString() != "text-fixture"
            || !QRegularExpression("^[0-9a-f]{32}$").match(id).hasMatch()
            || (action != "focus" && action != "snapshot" && action != "dismiss")) { return false; }
    // No GUI property reads or writes happen on V8's script thread. Queue one
    // correlated result; the host waits for actual GUI execution and live state.
    return QMetaObject::invokeMethod(QCoreApplication::instance(), [id, action, outputDirectory] {
        static PhoneTextInputFixture fixture;
        const auto finish = [id, action, outputDirectory](bool ok) {
            QJsonObject result { {"schemaVersion", 1}, {"commandId", id}, {"ok", ok},
                {"sampleEpochMs", QDateTime::currentMSecsSinceEpoch()} };
            if (ok) {
                const auto tablet = DependencyManager::get<TabletScriptingInterface>();
                const auto metrics = tablet->getTouchUiRuntimeMetrics();
                if (!metrics.value("valid").toBool()) { result["ok"] = false; }
                else { result["snapshot"] = fixture.snapshot(metrics.value("keyboardVisible").toBool()); }
            }
            QSaveFile output(QDir(outputDirectory).absoluteFilePath("phone-ui-status.json"));
            if (output.open(QIODevice::WriteOnly)) {
                output.setPermissions(QFile::ReadOwner | QFile::WriteOwner);
                output.write(QJsonDocument(result).toJson(QJsonDocument::Compact));
                output.commit();
            }
            // Fixed, app-private diagnostics for this explicit test launch.
            // Preserve actual failures instead of manufacturing a snapshot.
            QJsonObject diagnostic { {"operation", action}, {"nativeOk", ok},
                {"failure", fixture.lastFailure()}, {"panelPresent", fixture.panel() != nullptr},
                {"qtAccessibilityActive", QAccessible::isActive()},
                {"qtKeyboardVisible", qGuiApp->inputMethod()->isVisible()} };
            if (DependencyManager::isSet<TabletScriptingInterface>()) {
                const auto metrics = DependencyManager::get<TabletScriptingInterface>()->getTouchUiRuntimeMetrics();
                diagnostic["runtimeMetricsValid"] = metrics.value("valid").toBool();
                diagnostic["nativeKeyboardVisible"] = metrics.value("keyboardVisible").toBool();
            }
            QJsonArray controls;
            diagnostic["touchDelivery"] = QJsonObject::fromVariantMap(
                QCoreApplication::instance()->property("phoneTouchUiMetricsDiagnostic").toMap());
#if defined(Q_OS_ANDROID)
            const auto javaDiagnostic = QAndroidJniObject::callStaticObjectMethod(
                "org/overte/phone/PhoneInterfaceActivity", "getTouchUiDeliveryDiagnostic", "()Ljava/lang/String;");
            diagnostic["androidTouchDelivery"] = QJsonDocument::fromJson(javaDiagnostic.toString().toUtf8()).object();
#endif
            if (DependencyManager::isSet<OffscreenUi>()) {
                auto root = DependencyManager::get<OffscreenUi>()->getRootItem();
                for (const auto& name : {"tablet.home", "app.settings", "nav.close", "controlled.text"}) {
                    std::function<QQuickItem*(QQuickItem*, int)> findVisual;
                    findVisual = [&](QQuickItem* candidate, int depth) -> QQuickItem* {
                        if (!candidate || depth > 128) { return nullptr; }
                        if (candidate->objectName() == name || candidate->property("semanticId").toString() == name) {
                            return candidate;
                        }
                        for (auto child : candidate->childItems()) {
                            if (auto found = findVisual(child, depth + 1)) { return found; }
                        }
                        return nullptr;
                    };
                    auto item = findVisual(root, 0);
                    QJsonObject control { {"semanticId", name}, {"present", item != nullptr} };
                    if (item) {
                        const auto context = QQmlEngine::contextForObject(item);
                        const QQmlProperty role(item, "Accessible.role", context);
                        control["declaredRoleValid"] = role.isValid();
                        control["declaredRole"] = role.read().toInt();
                        auto accessible = QAccessible::queryAccessibleInterface(item);
                        control["nativeRole"] = accessible ? int(accessible->role()) : -1;
                        control["qmlContextPresent"] = context != nullptr;
                        control["objectClass"] = item->metaObject()->className();
                        control["declaredName"] = QQmlProperty(item, "Accessible.name", context).read().toString();
                        QJsonArray attached;
                        for (auto child : item->children()) {
                            if (QString(child->metaObject()->className()).contains("Accessible")) {
                                attached.append(QJsonObject { {"class", child->metaObject()->className()},
                                    {"role", child->property("role").toInt()} });
                            }
                        }
                        control["attached"] = attached;
                    }
                    controls.append(control);
                }
            }
            diagnostic["controls"] = controls;
            QSaveFile debug(QDir(outputDirectory).absoluteFilePath("phone-ui-diagnostic.json"));
            if (debug.open(QIODevice::WriteOnly)) {
                debug.setPermissions(QFile::ReadOwner | QFile::WriteOwner);
                debug.write(QJsonDocument(diagnostic).toJson(QJsonDocument::Compact));
                debug.commit();
            }
        };
        if (!DependencyManager::isSet<OffscreenUi>() || !DependencyManager::isSet<TabletScriptingInterface>()) {
            finish(false); return;
        }
        const auto ui = DependencyManager::get<OffscreenUi>();
        if (action == "focus") {
            auto panel = ui->getRootItem() ? ui->getRootItem()->findChild<QQuickItem*>("overte-e2e-text-panel") : nullptr;
            if (panel) { finish(fixture.focus(panel)); }
            else {
                // Wait until QML creation and native parent attachment finish.
                ui->load(QUrl("qrc:/qml/hifi/ControlledTextInput.qml"),
                    [finish](QQmlContext*, QQuickItem* created) {
                        QPointer<QQuickItem> guarded(created);
                        QTimer::singleShot(0, QCoreApplication::instance(), [finish, guarded] {
                            finish(fixture.focus(guarded));
                        });
                    });
            }
        } else if (action == "dismiss") { finish(fixture.dismiss()); }
        else { finish(fixture.panel() != nullptr); }
    }, Qt::QueuedConnection);
}

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
    QFile file(filepath);

    file.open(QFile::WriteOnly);
    file.write(jsonData);
    file.close();
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
