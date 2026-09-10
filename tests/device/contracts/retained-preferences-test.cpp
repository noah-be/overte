// SPDX-License-Identifier: Apache-2.0
#include <cassert>
#include <QtGui/QGuiApplication>
#include <QtQml/QQmlComponent>
#include <QtQml/QQmlContext>
#include <QtQuick/QQuickItem>
#include <QtQuick/QQuickWindow>
#include "../../../libraries/shared/src/Preferences.h"

int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    using namespace overte::ui;
    const auto product = configuredProduct();
    const bool vr = product == Product::Desktop || product == Product::Pico;
    const bool known = product != Product::Unknown;
    for (auto p : {Product::Phone, Product::Pico, Product::IOS, Product::Unknown}) {
        assert(!preferenceAllowed(p, "Unreviewed Category", "future"));
        assert(!preferenceAllowed(p, "Plugins", "Enable Oculus Platform Plugin"));
    }
    int reads = 0, writes = 0, triggers = 0;
    Preferences registry;
    auto* hidden = new CheckPreference("HMD", "VR test", [&] { ++reads; return false; },
        [&](const bool&) { ++writes; });
    registry.addPreference(hidden);
    assert(hidden->isProfileAllowed() == vr);
    assert(registry.getCategories().contains("HMD") == vr);
    assert(registry.getPreferencesByCategory().contains("HMD") == vr);
    hidden->load(); hidden->setEnabled(true); hidden->setValue(true); hidden->save();
    assert(reads == (vr ? 2 : 0));
    assert(writes == (vr ? 1 : 0));
    assert(hidden->isEnabled() == vr);
    ButtonPreference button("Controllers", "button", [&] { ++triggers; });
    button.trigger(); assert(triggers == (vr ? 1 : 0));
    FloatPreference number("HMD", "float", [&] { ++reads; return 0.0f; }, [&](const float&) { ++writes; });
    IntPreference integer("HMD", "integer", [&] { ++reads; return 0; }, [&](const int&) { ++writes; });
    StringPreference string("Avatar Tuning", "Dominant Hand", [&] { ++reads; return QString(); },
        [&](const QString&) { ++writes; });
    number.load(); number.setValue(1); number.save();
    integer.load(); integer.setValue(1); integer.save();
    string.load(); string.setValue("right"); string.save();
    assert(reads == (vr ? 8 : 0)); assert(writes == (vr ? 4 : 0));
    CheckPreference supported("Navigation", "navigation", [] { return false; }, [&](const bool&) { ++writes; });
    supported.load(); supported.setValue(true); supported.save();
    assert(supported.isProfileAllowed() == known);
    assert(writes == (vr ? 4 : 0) + (known ? 1 : 0));

    QQuickWindow window;
    window.resize(400, 200); window.show();
    QQmlEngine engine;
    engine.rootContext()->setContextProperty("candidatePreference", hidden);
    // Both original, unchanged-at-load-time production QML components. No
    // replacement policy, preference mock, or JS-only extraction is used.
    for (int index = 1; index < argc; ++index) {
        QQmlComponent component(&engine);
        auto source = QString("import QtQuick 2.5\nimport \"%1\" as Retained\n"
            "Retained.Preference { width: 400; height: 60; preference: candidatePreference; "
            "TextInput { objectName: 'focus-target'; activeFocusOnTab: true; focus: true } }")
            .arg(QUrl::fromLocalFile(QString::fromLocal8Bit(argv[index])).toString());
        component.setData(source.toUtf8(), QUrl("file:///retained-preferences-test.qml"));
        auto* object = component.create();
        if (!object) { qFatal("%s", qPrintable(component.errorString())); }
        auto* item = qobject_cast<QQuickItem*>(object); assert(item);
        item->setParentItem(window.contentItem());
        auto* child = item->findChild<QQuickItem*>("focus-target"); assert(child);
        child->forceActiveFocus(Qt::TabFocusReason);
        app.processEvents();
        assert(item->isVisible() == vr); assert(item->isEnabled() == vr);
        assert(child->isEnabled() == vr);
        if (!vr) { assert(!child->hasActiveFocus()); }
        delete item;
    }
}
