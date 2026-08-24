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
#include <QtCore/QDateTime>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QLoggingCategory>
#include <QtCore/QThread>
#include <QtGui/QGuiApplication>
#include <QtGui/QInputMethod>
#include <QtGui/QInputMethodEvent>
#include <QtGui/QKeyEvent>
#include <QtGui/QMouseEvent>

#include <AddressManager.h>
#include <shared/FileUtils.h>
#include <shared/IOSRuntimeLogging.h>
#include <shared/QtHelpers.h>
#include <SharedUtil.h>
#include <DependencyManager.h>
#include <display-plugins/DisplayPlugin.h>
#include <gpu/Context.h>
#include <MainWindow.h>
#include <OffscreenUi.h>
#include <ResourceCache.h>
#include <ScriptValue.h>
#include <StatTracker.h>
#include <Trace.h>
#include <ui/TabletScriptingInterface.h>

#if defined(Q_OS_IOS)
#include <mach/mach.h>
#endif

#include "Application.h"
#include "avatar/MyAvatar.h"
#include "NetworkingConstants.h"
#include "scripting/HMDScriptingInterface.h"
#include "scripting/RenderScriptingInterface.h"

Q_LOGGING_CATEGORY(trace_test, "trace.test")

TestScriptingInterface* TestScriptingInterface::getInstance() {
    static TestScriptingInterface sharedInstance;
    return &sharedInstance;
}

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

QVariantMap TestScriptingInterface::getIOSAutomationPlan() const {
    return _iosAutomationPlan;
}

QVariantMap TestScriptingInterface::getIOSAutomationSnapshot() const {
    if (qApp && QThread::currentThread() != qApp->thread()) {
        QVariantMap result;
        QMetaObject::invokeMethod(qApp, [this, &result] {
            result = getIOSAutomationSnapshot();
        }, Qt::BlockingQueuedConnection);
        return result;
    }

    QVariantMap snapshot;
    snapshot["epoch_ms"] = QDateTime::currentMSecsSinceEpoch();

    if (!qApp) {
        snapshot["application_ready"] = false;
        return snapshot;
    }

    snapshot["application_ready"] = true;
    auto addressManager = DependencyManager::get<AddressManager>();
    if (addressManager) {
        snapshot["connected"] = addressManager->isConnected();
        snapshot["address"] = addressManager->currentShareableAddress().toString();
        snapshot["domain"] = addressManager->currentShareableAddress(true).toString();
    }

    auto displayPlugin = qApp->getActiveDisplayPlugin();
    snapshot["render_fps"] = qApp->getRenderLoopRate();
    snapshot["simulation_fps"] = qApp->getGameLoopRate();
    if (displayPlugin) {
        snapshot["present_fps"] = displayPlugin->presentRate();
        snapshot["new_frame_fps"] = displayPlugin->newFramePresentRate();
        snapshot["dropped_fps"] = displayPlugin->droppedFrameRate();
        snapshot["stutter_rate"] = displayPlugin->stutterRate();
    }

    const auto cameraPosition = qApp->getCamera().getPosition();
    snapshot["camera_mode"] = qApp->getCamera().getModeString();
    snapshot["camera_position"] = QVariantMap {
        { "x", cameraPosition.x }, { "y", cameraPosition.y }, { "z", cameraPosition.z }
    };

    if (auto primaryWidget = qApp->getPrimaryWidget()) {
        snapshot["viewport_width"] = primaryWidget->width();
        snapshot["viewport_height"] = primaryWidget->height();
        snapshot["viewport_input_method_enabled"] = primaryWidget->testAttribute(Qt::WA_InputMethodEnabled);
    }
    if (auto inputMethod = QGuiApplication::inputMethod()) {
        snapshot["input_method_visible"] = inputMethod->isVisible();
    }
    auto offscreenUi = DependencyManager::get<OffscreenUi>();
    if (offscreenUi && offscreenUi->getWindow()) {
        auto focusObject = offscreenUi->getWindow()->focusObject();
        if (focusObject) {
            snapshot["qml_focus_class"] = focusObject->metaObject()->className();
            snapshot["qml_focus_object"] = focusObject->objectName();
            snapshot["qml_focus_active"] = focusObject->property("activeFocus").toBool();
        }
    }

    if (auto myAvatar = qApp->getMyAvatar()) {
        const auto avatarPosition = myAvatar->getWorldPosition();
        snapshot["avatar_position"] = QVariantMap {
            { "x", avatarPosition.x }, { "y", avatarPosition.y }, { "z", avatarPosition.z }
        };
        snapshot["avatar_speed"] = glm::length(myAvatar->getWorldVelocity());
        snapshot["avatar_jumping"] = myAvatar->isJumping();
    }

    snapshot["active_downloads"] = static_cast<qulonglong>(ResourceCache::getLoadingRequestCount());
    snapshot["pending_downloads"] = static_cast<qulonglong>(ResourceCache::getPendingRequestCount());
    snapshot["pending_texture_transfers"] =
        static_cast<qulonglong>(gpu::Context::getTexturePendingGPUTransferCount());
    snapshot["gpu_memory_bytes"] = static_cast<qulonglong>(gpu::Context::getUsedGPUMemSize());

    auto statTracker = DependencyManager::get<StatTracker>();
    if (statTracker) {
        snapshot["processing_resources"] = statTracker->getStat("Processing").toInt();
        snapshot["pending_processing_resources"] = statTracker->getStat("PendingProcessing").toInt();
    }

    if (auto entityRenderer = qApp->getEntities()) {
        if (auto entityTree = entityRenderer->getTree()) {
            snapshot["entity_tree_elements"] =
                static_cast<qulonglong>(entityTree->getOctreeElementsCount());
        }
    }

    const auto evidence = iosRuntimeEntityEvidenceSnapshot();
    snapshot["entity_evidence"] = QVariantMap {
        { "armed", evidence.armed },
        { "committed", evidence.committed },
        { "expected", evidence.expected },
        { "renderables", evidence.renderables },
        { "scene", evidence.scene },
        { "drawn", evidence.drawn }
    };

    auto hmd = DependencyManager::get<HMDScriptingInterface>();
    snapshot["tablet_shown"] = hmd ? hmd->getShouldShowTablet() : false;
    auto tabletInterface = DependencyManager::get<TabletScriptingInterface>();
    if (tabletInterface) {
        auto tablet = tabletInterface->getTablet(QStringLiteral("com.highfidelity.interface.tablet.system"));
        if (tablet) {
            snapshot["tablet_home"] = tablet->onHomeScreen();
            snapshot["tablet_landscape"] = tablet->getLandscape();
        }
    }

    snapshot["render_scale"] = RenderScriptingInterface::getInstance()->getViewportResolutionScale();

#if defined(Q_OS_IOS)
    task_vm_info_data_t taskInfo {};
    mach_msg_type_number_t taskInfoCount = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO,
            reinterpret_cast<task_info_t>(&taskInfo), &taskInfoCount) == KERN_SUCCESS) {
        snapshot["process_memory_bytes"] = static_cast<qulonglong>(taskInfo.phys_footprint);
        snapshot["process_resident_memory_bytes"] = static_cast<qulonglong>(taskInfo.resident_size);
    }
#else
    MemoryInfo memoryInfo;
    if (getMemoryInfo(memoryInfo)) {
        snapshot["process_memory_bytes"] = static_cast<qulonglong>(memoryInfo.processUsedMemoryBytes);
        snapshot["process_peak_memory_bytes"] = static_cast<qulonglong>(memoryInfo.processPeakUsedMemoryBytes);
        snapshot["system_memory_used_bytes"] = static_cast<qulonglong>(memoryInfo.usedMemoryBytes);
    }
#endif

    return snapshot;
}

void TestScriptingInterface::logIOSAutomationEvent(const QString& stage, const QVariantMap& fields) {
    QJsonObject event = QJsonObject::fromVariantMap(fields);
    event["stage"] = stage.left(64);
    event["epoch_ms"] = QDateTime::currentMSecsSinceEpoch();
    const auto json = QJsonDocument(event).toJson(QJsonDocument::Compact);
    logIOSRuntimeMarker("OVERTE_IOS_AUTOMATION", QString::fromUtf8(json));
}

bool TestScriptingInterface::executeIOSAutomationCommand(
        const QString& command, const QVariantMap& arguments) {
    if (qApp && QThread::currentThread() != qApp->thread()) {
        bool result { false };
        QMetaObject::invokeMethod(qApp, [this, &result, command, arguments] {
            result = executeIOSAutomationCommand(command, arguments);
        }, Qt::BlockingQueuedConnection);
        return result;
    }

    if (!qApp) {
        return false;
    }

    if (command == QStringLiteral("jump")) {
        if (auto myAvatar = qApp->getMyAvatar()) {
            myAvatar->getCharacterController()->jump();
            return true;
        }
        return false;
    }
    if (command == QStringLiteral("clear_caches")) {
        qApp->reloadResourceCaches();
        return true;
    }
    if (command == QStringLiteral("set_camera_mode")) {
        const auto mode = arguments.value(QStringLiteral("mode")).toString();
        if (mode.isEmpty()) {
            return false;
        }
        qApp->getCamera().setModeString(mode);
        return qApp->getCamera().getModeString() == mode;
    }
    if (command == QStringLiteral("set_render_scale")) {
        bool valid { false };
        const auto scale = arguments.value(QStringLiteral("scale")).toFloat(&valid);
        if (!valid || scale < 0.25f || scale > 2.0f) {
            return false;
        }
        RenderScriptingInterface::getInstance()->setViewportResolutionScale(scale);
        return true;
    }
    if (command == QStringLiteral("tap") || command == QStringLiteral("swipe")) {
        auto widget = qApp->getPrimaryWidget();
        if (!widget || widget->width() <= 0 || widget->height() <= 0) {
            return false;
        }
        const bool normalized = arguments.value(QStringLiteral("normalized"), true).toBool();
        auto readPoint = [widget, normalized, &arguments](
                const QString& xName, const QString& yName, QPointF& point) -> bool {
            bool xValid { false };
            bool yValid { false };
            auto x = arguments.value(xName).toDouble(&xValid);
            auto y = arguments.value(yName).toDouble(&yValid);
            if (!xValid || !yValid) {
                return false;
            }
            if (normalized) {
                if (x < 0.0 || x > 1.0 || y < 0.0 || y > 1.0) {
                    return false;
                }
                x *= widget->width();
                y *= widget->height();
            }
            if (x < 0.0 || x >= widget->width() || y < 0.0 || y >= widget->height()) {
                return false;
            }
            point = QPointF(x, y);
            return true;
        };

        QPointF start;
        const auto startX = command == QStringLiteral("tap") ? QStringLiteral("x") : QStringLiteral("start_x");
        const auto startY = command == QStringLiteral("tap") ? QStringLiteral("y") : QStringLiteral("start_y");
        if (!readPoint(startX, startY, start)) {
            return false;
        }

        QMouseEvent press(
            QEvent::MouseButtonPress, start, Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
        QCoreApplication::sendEvent(widget, &press);
        if (command == QStringLiteral("swipe")) {
            QPointF end;
            if (!readPoint(QStringLiteral("end_x"), QStringLiteral("end_y"), end)) {
                QMouseEvent release(
                    QEvent::MouseButtonRelease, start, Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
                QCoreApplication::sendEvent(widget, &release);
                return false;
            }
            constexpr int SWIPE_STEPS = 12;
            for (int step = 1; step <= SWIPE_STEPS; ++step) {
                const auto position = start + (end - start) * (static_cast<qreal>(step) / SWIPE_STEPS);
                QMouseEvent move(
                    QEvent::MouseMove, position, Qt::NoButton, Qt::LeftButton, Qt::NoModifier);
                QCoreApplication::sendEvent(widget, &move);
            }
            start = end;
        }
        QMouseEvent release(
            QEvent::MouseButtonRelease, start, Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
        QCoreApplication::sendEvent(widget, &release);
        return true;
    }
    if (command == QStringLiteral("type_text")) {
        const auto text = arguments.value(QStringLiteral("text")).toString();
        if (text.isEmpty() || text.size() > 4096) {
            return false;
        }
        QInputMethodEvent inputMethodEvent;
        inputMethodEvent.setCommitString(text);
        return QCoreApplication::sendEvent(qApp->getPrimaryWidget(), &inputMethodEvent);
    }
    if (command == QStringLiteral("key")) {
        static const QHash<QString, int> KEY_NAMES {
            { QStringLiteral("enter"), Qt::Key_Return },
            { QStringLiteral("backspace"), Qt::Key_Backspace },
            { QStringLiteral("delete"), Qt::Key_Delete },
            { QStringLiteral("escape"), Qt::Key_Escape },
            { QStringLiteral("tab"), Qt::Key_Tab },
            { QStringLiteral("left"), Qt::Key_Left },
            { QStringLiteral("right"), Qt::Key_Right },
            { QStringLiteral("up"), Qt::Key_Up },
            { QStringLiteral("down"), Qt::Key_Down }
        };
        const auto name = arguments.value(QStringLiteral("name")).toString().toLower();
        if (!KEY_NAMES.contains(name)) {
            return false;
        }
        const auto key = KEY_NAMES.value(name);
        const auto text = key == Qt::Key_Return ? QStringLiteral("\r") : QString();
        QKeyEvent press(QEvent::KeyPress, key, Qt::NoModifier, text);
        QKeyEvent release(QEvent::KeyRelease, key, Qt::NoModifier, text);
        const bool pressDelivered = QCoreApplication::sendEvent(qApp->getPrimaryWidget(), &press);
        const bool releaseDelivered = QCoreApplication::sendEvent(qApp->getPrimaryWidget(), &release);
        return pressDelivered || releaseDelivered;
    }

    return false;
}
