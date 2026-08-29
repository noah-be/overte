// SPDX-License-Identifier: Apache-2.0

#include "PicoE2eTabletBridge.h"

#include <algorithm>
#include <cmath>
#include <functional>

#include <QCoreApplication>
#include <QDateTime>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMouseEvent>
#include <QQuickItem>
#include <QQuickWindow>
#include <QRectF>
#include <QSaveFile>
#include <QSet>
#include <QTimer>

#include <DependencyManager.h>
#include <shared/GlobalAppProperties.h>
#include <ui/TabletScriptingInterface.h>

namespace overte::pico::e2e {
namespace {

const QString SYSTEM_TABLET { QStringLiteral("com.highfidelity.interface.tablet.system") };
const QString BRIDGE_DIRECTORY { QStringLiteral("/data/user/0/org.overte.pico/files/overte-e2e") };
const QString OBSERVATION_PATH { BRIDGE_DIRECTORY + QStringLiteral("/tablet-ui-observation.json") };
const QString COMMAND_PATH { BRIDGE_DIRECTORY + QStringLiteral("/tablet-ui-command.json") };
const QString STATUS_PATH { BRIDGE_DIRECTORY + QStringLiteral("/tablet-ui-status.json") };
const QString PROBE_PATH {
    QStringLiteral("/data/user/0/org.overte.pico/files/overte-e2e/overte_e2e_probe.js")
};

const QSet<QString> SCREEN_IDS {
    QStringLiteral("settings.audio"),
    QStringLiteral("settings.controllers"),
    QStringLiteral("settings.general"),
    QStringLiteral("settings.graphics"),
    QStringLiteral("settings.home"),
    QStringLiteral("settings.security"),
    QStringLiteral("tablet.home"),
};

const QSet<QString> CONTROL_IDS {
    QStringLiteral("app.settings"),
    QStringLiteral("nav.back"),
    QStringLiteral("nav.close"),
    QStringLiteral("nav.home"),
    QStringLiteral("settings.audio"),
    QStringLiteral("settings.controllers"),
    QStringLiteral("settings.general"),
    QStringLiteral("settings.graphics"),
    QStringLiteral("settings.hmd-preferences"),
    QStringLiteral("settings.security"),
    QStringLiteral("settings.vr-render-resolution"),
};

bool bridgeEnabled() {
    const QUrl testScript = qApp->property(hifi::properties::TEST).toUrl();
    return testScript.isLocalFile()
        && QFileInfo(testScript.toLocalFile()).canonicalFilePath() == PROBE_PATH;
}

bool effectiveVisible(const QQuickItem* item) {
    if (!item || !item->isVisible() || item->opacity() <= 0.01
            || item->width() <= 0.0 || item->height() <= 0.0 || !item->window()) {
        return false;
    }
    QRectF visibleRect = item->mapRectToScene(item->boundingRect());
    visibleRect = visibleRect.intersected(
        QRectF(QPointF(0.0, 0.0), QSizeF(item->window()->size())));
    for (auto parent = item->parentItem(); parent; parent = parent->parentItem()) {
        if (!parent->isVisible() || parent->opacity() <= 0.01) {
            return false;
        }
        if (parent->clip()) {
            visibleRect = visibleRect.intersected(
                parent->mapRectToScene(parent->boundingRect()));
        }
    }
    return !visibleRect.isEmpty();
}

void walkItems(QQuickItem* item, const std::function<void(QQuickItem*, int)>& visitor,
               int depth = 0) {
    if (!item) {
        return;
    }
    visitor(item, depth);
    const auto children = item->childItems();
    for (auto child : children) {
        walkItems(child, visitor, depth + 1);
    }
}

bool writeJson(const QString& path, const QJsonObject& value) {
    QSaveFile output(path);
    if (!output.open(QIODevice::WriteOnly)) {
        return false;
    }
    output.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
    if (output.write(QJsonDocument(value).toJson(QJsonDocument::Compact)) < 0
            || output.write("\n") != 1) {
        output.cancelWriting();
        return false;
    }
    return output.commit();
}

struct Observation {
    QJsonObject snapshot;
    QHash<QString, QQuickItem*> controls;
};

Observation observeTablet() {
    Observation result;
    QString screenId { QStringLiteral("tablet.home") };
    int screenDepth { -1 };
    QSet<QString> visibleControls;

    auto tabletInterface = DependencyManager::get<TabletScriptingInterface>();
    auto tablet = tabletInterface ? tabletInterface->getTablet(SYSTEM_TABLET) : nullptr;
    auto root = tablet ? tablet->getTabletRoot() : nullptr;
    const bool open = tablet && tablet->property("tabletShown").toBool();

    walkItems(root, [&](QQuickItem* item, int depth) {
        if (!effectiveVisible(item)) {
            return;
        }
        QString candidate = item->property("semanticScreenId").toString();
        if (candidate.isEmpty()) {
            candidate = item->objectName();
        }
        if (SCREEN_IDS.contains(candidate) && depth >= screenDepth) {
            screenId = candidate;
            screenDepth = depth;
        }

        const QString controlId = item->objectName();
        if (CONTROL_IDS.contains(controlId)) {
            visibleControls.insert(controlId);
            if (item->isEnabled() && !result.controls.contains(controlId)) {
                result.controls.insert(controlId, item);
            }
        }
    });

    QStringList sortedControls = visibleControls.values();
    std::sort(sortedControls.begin(), sortedControls.end());
    QJsonArray controls;
    for (const auto& control : sortedControls) {
        controls.append(control);
    }
    result.snapshot = {
        { QStringLiteral("contractVersion"), 1 },
        { QStringLiteral("schemaVersion"), 1 },
        { QStringLiteral("screenId"), screenId },
        { QStringLiteral("ready"), open && root && screenDepth >= 0 },
        { QStringLiteral("visibleControlIds"), controls },
    };
    return result;
}

bool exactKeys(const QJsonObject& object, const QSet<QString>& expected) {
    QSet<QString> actual;
    for (const auto& key : object.keys()) {
        actual.insert(key);
    }
    return actual == expected;
}

void writeStatus(const QString& commandId, bool performed, const QString& error) {
    writeJson(STATUS_PATH, {
        { QStringLiteral("schemaVersion"), 1 },
        { QStringLiteral("commandId"), commandId },
        { QStringLiteral("performed"), performed },
        { QStringLiteral("error"), error.left(120) },
        { QStringLiteral("updatedEpochMs"),
          static_cast<double>(QDateTime::currentMSecsSinceEpoch()) },
    });
}

bool sendPointerClick(QQuickItem* item, QQuickWindow* window) {
    if (!effectiveVisible(item) || !item->isEnabled() || !window) {
        return false;
    }
    const QPointF local(item->width() / 2.0, item->height() / 2.0);
    const QPointF position = item->mapToScene(local);
    if (!std::isfinite(position.x()) || !std::isfinite(position.y())
            || position.x() < 0.0 || position.y() < 0.0
            || position.x() >= window->width() || position.y() >= window->height()) {
        return false;
    }
    QMouseEvent move(QEvent::MouseMove, position, Qt::NoButton, Qt::NoButton,
                     Qt::NoModifier);
    QMouseEvent press(QEvent::MouseButtonPress, position, Qt::LeftButton,
                      Qt::LeftButton, Qt::NoModifier);
    QMouseEvent release(QEvent::MouseButtonRelease, position, Qt::LeftButton,
                        Qt::NoButton, Qt::NoModifier);
    QCoreApplication::sendEvent(window, &move);
    QCoreApplication::sendEvent(window, &press);
    QCoreApplication::sendEvent(window, &release);
    return true;
}

class TabletBridge : public QObject {
public:
    explicit TabletBridge(QObject* owner) : QObject(owner) {
        connect(&_timer, &QTimer::timeout, this, [this] { tick(); });
        _timer.start(100);
    }

private:
    void tick() {
        if (!bridgeEnabled()) {
            return;
        }
        const Observation observation = observeTablet();
        writeJson(OBSERVATION_PATH, {
            { QStringLiteral("bridgeVersion"), 1 },
            { QStringLiteral("updatedEpochMs"),
              static_cast<double>(QDateTime::currentMSecsSinceEpoch()) },
            { QStringLiteral("snapshot"), observation.snapshot },
        });
        applyCommand(observation);
    }

    void applyCommand(const Observation& observation) {
        QFile input(COMMAND_PATH);
        if (!input.exists() || QFileInfo(COMMAND_PATH).isSymLink()
                || input.size() > 16 * 1024
                || !input.open(QIODevice::ReadOnly)) {
            return;
        }
        QJsonParseError parseError;
        const auto document = QJsonDocument::fromJson(input.readAll(), &parseError);
        if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
            return;
        }
        const auto command = document.object();
        const QString commandId = command.value(QStringLiteral("commandId")).toString();
        if (commandId.isEmpty() || commandId.size() > 128 || commandId == _lastCommandId) {
            return;
        }
        _lastCommandId = commandId;
        if (!exactKeys(command, {
                QStringLiteral("schemaVersion"), QStringLiteral("commandId"),
                QStringLiteral("contractVersion"), QStringLiteral("controlId") })
                || command.value(QStringLiteral("schemaVersion")).toInt(-1) != 1
                || command.value(QStringLiteral("contractVersion")).toInt(-1) != 1) {
            writeStatus(commandId, false, QStringLiteral("malformed-command"));
            return;
        }
        const QString controlId = command.value(QStringLiteral("controlId")).toString();
        if (!observation.snapshot.value(QStringLiteral("ready")).toBool()
                || !CONTROL_IDS.contains(controlId)
                || !observation.controls.contains(controlId)) {
            writeStatus(commandId, false, QStringLiteral("control-not-visible"));
            return;
        }
        auto tabletInterface = DependencyManager::get<TabletScriptingInterface>();
        auto window = tabletInterface ? tabletInterface->getTabletWindow() : nullptr;
        if (!sendPointerClick(observation.controls.value(controlId), window)) {
            writeStatus(commandId, false, QStringLiteral("pointer-activation-failed"));
            return;
        }
        writeStatus(commandId, true, QString());
    }

    QTimer _timer;
    QString _lastCommandId;
};

}  // namespace

void installTabletBridge(QObject* owner) {
    if (owner) {
        new TabletBridge(owner);
    }
}

}  // namespace overte::pico::e2e
