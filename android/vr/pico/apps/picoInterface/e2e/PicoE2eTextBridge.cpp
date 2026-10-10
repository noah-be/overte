// SPDX-License-Identifier: Apache-2.0
#include "PicoE2eTabletBridge.h"

#include <QCoreApplication>
#include <QDateTime>
#include <QFile>
#include <QFileInfo>
#include <QGuiApplication>
#include <QInputMethod>
#include <QInputMethodEvent>
#include <QJsonDocument>
#include <QJsonObject>
#include <QKeyEvent>
#include <QPointer>
#include <QQuickItem>
#include <QQuickWindow>
#include <QSaveFile>
#include <QSet>
#include <QTimer>
#include <DependencyManager.h>
#include <OffscreenUi.h>
#include <shared/GlobalAppProperties.h>

namespace overte::pico::e2e {
namespace {
const QString DIRECTORY { "/data/user/0/org.overte.pico/files/overte-e2e/" };

bool activeProbe() {
    const auto script = qApp->property(hifi::properties::TEST).toUrl();
    const auto expected = QFileInfo(DIRECTORY + "overte_e2e_probe.js").canonicalFilePath();
    return script.isLocalFile() && !expected.isEmpty()
        && QFileInfo(script.toLocalFile()).canonicalFilePath() == expected;
}

bool write(const QString& name, const QJsonObject& value) {
    QSaveFile output(DIRECTORY + name);
    if (!output.open(QIODevice::WriteOnly)) { return false; }
    output.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
    const auto bytes = QJsonDocument(value).toJson(QJsonDocument::Compact);
    if (output.write(bytes) != bytes.size()) { output.cancelWriting(); return false; }
    return output.commit();
}

class TextBridge final : public QObject {
public:
    explicit TextBridge(QObject* owner) : QObject(owner) {
        _timer.setInterval(100);
        connect(&_timer, &QTimer::timeout, this, [this] { tick(); });
        _timer.start();
    }
private:
    QJsonObject snapshot() const {
        if (!_panel || !_field) { return {}; }
        return { {"schemaVersion", 1}, {"value", _field->property("text").toString()},
            {"focused", _field->hasActiveFocus()},
            {"keyboardVisible", qGuiApp->inputMethod()->isVisible()},
            {"submittedCount", _panel->property("submittedCount").toInt()} };
    }

    void finish(const QString& id, bool ok, const QString& error = {}) {
        write("text-input-status.json", {
            {"schemaVersion", 1}, {"commandId", id}, {"performed", ok},
            {"error", error}, {"updatedEpochMs", static_cast<double>(QDateTime::currentMSecsSinceEpoch())},
            {"snapshot", snapshot()},
        });
        _pending = false;
    }

    void focus(const QString& id, QQuickItem* panel) {
        auto field = panel ? panel->findChild<QQuickItem*>("controlled.text") : nullptr;
        if (!panel || !field || !panel->window()) { finish(id, false, "field-unavailable"); return; }
        _panel = panel;
        _field = field;
        panel->setVisible(true);
        if (!field->setProperty("text", QString())) { finish(id, false, "clear-rejected"); return; }
        field->forceActiveFocus(Qt::OtherFocusReason);
        qGuiApp->inputMethod()->show();
        finish(id, field->hasActiveFocus(), "");
    }

    bool key(int key) {
        if (!_field || !_field->window() || !_field->hasActiveFocus()) { return false; }
        QKeyEvent down(QEvent::KeyPress, key, Qt::NoModifier);
        QKeyEvent up(QEvent::KeyRelease, key, Qt::NoModifier);
        const bool pressed = QCoreApplication::sendEvent(_field->window(), &down);
        const bool released = QCoreApplication::sendEvent(_field->window(), &up);
        return pressed && released;
    }

    void tick() {
        if (!activeProbe()) { return; }
        if (_panel && _field) {
            write("text-input-observation.json", {
                {"schemaVersion", 1}, {"updatedEpochMs", static_cast<double>(QDateTime::currentMSecsSinceEpoch())},
                {"snapshot", snapshot()},
            });
        }
        if (_pending) { return; }
        QFile input(DIRECTORY + "text-input-command.json");
        if (!input.open(QIODevice::ReadOnly) || input.size() > 16384) { return; }
        const auto document = QJsonDocument::fromJson(input.readAll());
        if (!document.isObject()) { return; }
        const auto command = document.object();
        const auto id = command.value("commandId").toString();
        if (id.isEmpty() || id.size() > 128 || id == _lastId) { return; }
        _lastId = id;
        _pending = true;
        const auto action = command.value("action").toString();
        QSet<QString> expected { "schemaVersion", "commandId", "action" };
        if (action == "type") { expected.unite({ "text", "backspaceCount", "submit" }); }
        const auto keys = command.keys();
        const QSet<QString> actual(keys.begin(), keys.end());
        if (actual != expected || command.value("schemaVersion").toInt(-1) != 1) {
            finish(id, false, "malformed-command"); return;
        }
        if (action == "focus") {
            if (!DependencyManager::isSet<OffscreenUi>()) { finish(id, false, "ui-unavailable"); return; }
            auto ui = DependencyManager::get<OffscreenUi>();
            auto root = ui->getRootItem();
            auto panel = root ? root->findChild<QQuickItem*>("overte-e2e-text-panel") : nullptr;
            if (panel) { focus(id, panel); return; }
            QPointer<TextBridge> self(this);
            ui->load(QUrl::fromLocalFile(DIRECTORY + "ControlledTextInput.qml"),
                [self, id](QQmlContext*, QQuickItem* created) {
                    QPointer<QQuickItem> panel(created);
                    if (self) {
                        QTimer::singleShot(0, self, [self, id, panel] {
                            if (self) { self->focus(id, panel); }
                        });
                    }
                });
            return;
        }
        if (!_panel || !_field) { finish(id, false, "field-unavailable"); return; }
        if (action == "snapshot") { finish(id, true); return; }
        if (action == "dismiss") {
            _field->setFocus(false);
            _panel->setFocus(false);
            _panel->setVisible(false);
            qGuiApp->inputMethod()->hide();
            finish(id, !_field->hasActiveFocus()); return;
        }
        if (action == "type") {
            const auto text = command.value("text").toString();
            const double count = command.value("backspaceCount").toDouble(-1);
            if (!command.value("text").isString() || text.toUcs4().size() > 128
                    || count < 0 || count > 32 || count != static_cast<int>(count)
                    || !command.value("submit").isBool() || !_field->hasActiveFocus()
                    || !_field->window()) { finish(id, false, "invalid-edit"); return; }
            // Deliver actual Qt editor events, never an expected-value snapshot.
            QInputMethodEvent commit;
            commit.setCommitString(text);
            bool ok = QCoreApplication::sendEvent(_field->window(), &commit);
            for (int i = 0; i < static_cast<int>(count); ++i) { ok = key(Qt::Key_Backspace) && ok; }
            if (command.value("submit").toBool()) { ok = key(Qt::Key_Return) && ok; }
            finish(id, ok, ok ? QString() : QStringLiteral("native-edit-rejected")); return;
        }
        finish(id, false, "unsupported-action");
    }
    QTimer _timer;
    QPointer<QQuickItem> _panel;
    QPointer<QQuickItem> _field;
    QString _lastId;
    bool _pending { false };
};
}

void installTextBridge(QObject* owner) {
    if (owner) { new TextBridge(owner); }
}
}
