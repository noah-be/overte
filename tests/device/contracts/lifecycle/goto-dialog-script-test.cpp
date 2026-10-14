// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QFile>
#include <QJSEngine>
#include <QQmlEngine>
#include <QVariantMap>
#include <iostream>
#include <stdexcept>
#include <DependencyManager.h>
#include "ui/DialogsManager.h"
#include "DialogsManagerScriptingInterface.h"

static void require(bool value, const char* message) {
    if (!value) { throw std::runtime_error(message); }
}

class Button : public QObject {
    Q_OBJECT
public:
    bool active { false };
    int edits { 0 };
public slots:
    void editProperties(const QVariantMap& properties) {
        ++edits;
        active = properties.value("isActive").toBool();
    }
signals:
    void clicked();
};

class Host : public QObject {
    Q_OBJECT
public:
    QString removed;
public slots:
    void recordRemoval(const QString& value) { removed = value; }
signals:
    void scriptEnding();
};

static void evaluate(QJSEngine& engine, const QString& code, const QString& file = {}) {
    auto result = engine.evaluate(code, file);
    if (result.isError()) {
        throw std::runtime_error(result.toString().toStdString());
    }
}

static void expose(QJSEngine& engine, const QString& name, QObject& object) {
    QQmlEngine::setObjectOwnership(&object, QQmlEngine::CppOwnership);
    engine.globalObject().setProperty(name, engine.newQObject(&object));
}

static void apiContract() {
    auto dialogs = DependencyManager::get<DialogsManager>();
    DialogsManagerScriptingInterface api;
    QJSEngine engine;
    expose(engine, "DialogsManager", api);
    require(api.metaObject()->indexOfSlot("toggleAddressBar()") >= 0,
            "production QObject does not export toggleAddressBar()");
    require(engine.globalObject().property("DialogsManager").property("toggleAddressBar").isCallable(),
            "actual script object does not expose a callable toggleAddressBar");
    int shown = 0;
    QObject::connect(&api, &DialogsManagerScriptingInterface::addressBarShown,
                     [&shown](bool) { ++shown; });
    evaluate(engine, "DialogsManager.toggleAddressBar(); DialogsManager.toggleAddressBar();");
    require(dialogs->toggles == 0, "UI toggle was delivered synchronously");
    QCoreApplication::processEvents();
    require(dialogs->toggles == 2 && !dialogs->visible && shown == 2,
            "queued rapid toggles or forwarded visibility signal are incorrect");
    evaluate(engine, "DialogsManager.showAddressBar();");
    require(!dialogs->visible, "show was delivered synchronously");
    QCoreApplication::processEvents();
    require(dialogs->visible, "queued show did not reach the UI receiver");
    evaluate(engine, "DialogsManager.hideAddressBar();");
    require(dialogs->visible, "hide was delivered synchronously");
    QCoreApplication::processEvents();
    require(!dialogs->visible && dialogs->hides == 1 && shown == 4,
            "queued hide or visibility forwarding failed");
    std::cout << "PASS actual QObject script API and queued UI dispatch\n";
}

static void lifecycleContract(const QString& source, bool toolbar, const QString& scenario) {
    auto dialogs = DependencyManager::get<DialogsManager>();
    dialogs->visible = false;
    dialogs->toggles = dialogs->hides = 0;
    DialogsManagerScriptingInterface api;
    Button button;
    Host host;
    QJSEngine engine;
    expose(engine, "DialogsManager", api);
    expose(engine, "Button", button);
    expose(engine, "Host", host);
    evaluate(engine, QString(R"JS(
        var Settings = { getValue: function() { return %1; } };
        var controls = {
            addButton: function() { return Button; },
            removeButton: function(value) {
                Host.recordRemoval(typeof value === "string" ? value : "tablet");
            }
        };
        var Tablet = { getTablet: function() { return controls; } };
        var Toolbars = { getToolbar: function() { return controls; } };
        var Script = { scriptEnding: Host.scriptEnding, resolvePath: function(path) { return path; } };
    )JS").arg(toolbar ? "true" : "false"));
    evaluate(engine, source, "scripts/system/goto.js");

    if (scenario != "idle") {
        emit button.clicked();
        require(dialogs->toggles == 0, "GOTO click bypassed queued UI dispatch");
        QCoreApplication::processEvents();
        require(dialogs->visible && button.active, "GOTO click did not open/activate the dialog");
        if (scenario == "external-close") {
            dialogs->setVisible(false);
            require(!button.active, "external close left GOTO button active");
        } else if (scenario == "rapid-clicks") {
            emit button.clicked();
            QCoreApplication::processEvents();
            require(!dialogs->visible && !button.active, "second click did not close GOTO");
        } else if (scenario == "missed-close-signal") {
            // The production API documents that some closes omit a signal.
            // A stale observed-open state must still hide, never toggle open.
            dialogs->visible = false;
        }
    }
    const int toggles = dialogs->toggles;
    emit host.scriptEnding();
    QCoreApplication::processEvents();
    require(!dialogs->visible, "ending GOTO reopened or failed to close the dialog");
    require(dialogs->toggles == toggles, "script cleanup toggled the UI instead of hiding it");
    require(dialogs->hides == ((scenario == "open" || scenario == "missed-close-signal") ? 1 : 0),
            "cleanup did not respect observed visibility or disturbed an idle dialog");
    require(host.removed == (toolbar ? "GOTO" : "tablet"), "GOTO button was not removed");
    const int edits = button.edits;
    emit button.clicked();
    dialogs->setVisible(true);
    QCoreApplication::processEvents();
    require(button.edits == edits && dialogs->toggles == toggles,
            "GOTO signal connections survived script teardown");
    dialogs->visible = false;
    std::cout << "PASS actual goto.js " << (toolbar ? "toolbar " : "tablet ")
              << scenario.toStdString() << '\n';
}

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    try {
        require(argc == 2, "expected path to the real production goto.js");
        QFile file(QString::fromLocal8Bit(argv[1]));
        require(file.open(QIODevice::ReadOnly), "cannot read production goto.js");
        const QString source = QString::fromUtf8(file.readAll());
        apiContract();
        for (bool toolbar : { false, true }) {
            for (const auto& scenario : { "external-close", "open", "idle", "rapid-clicks", "missed-close-signal" }) {
                lifecycleContract(source, toolbar, QString::fromLatin1(scenario));
            }
        }
    } catch (const std::exception& error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
    return 0;
}

#include "goto-dialog-script-test.moc"
