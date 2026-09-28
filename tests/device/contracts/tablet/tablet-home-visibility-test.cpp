// SPDX-License-Identifier: Apache-2.0
// Real Qt meta-object calls at the tablet window/service boundary.
#include <QCoreApplication>
#include <QThread>
#include <QVariant>

static const char* TABLET_HOME_SOURCE_URL = "hifi/tablet/TabletHome.qml";

class WindowRoot : public QObject {
    Q_OBJECT
public:
    bool shown { false };
    QString source;
    Q_INVOKABLE void setShown(const QVariant& value) { shown = value.toBool(); }
    Q_INVOKABLE void loadSource(const QVariant& value) { source = value.toString(); }
};

struct DesktopWindow {
    WindowRoot root;
    QObject* asQuickItem() { return &root; }
};

class TabletProxy : public QObject {
public:
    enum class State { Home, Uninitialized, QML };
    State _state { State::QML };
    bool _toolbarMode { true };
    bool _screenSpaceMode { true };
    QObject* _qmlTabletRoot { nullptr };
    DesktopWindow window;
    DesktopWindow* _desktopWindow { &window };
    QString _currentPathLoaded { "hifi/Pal.qml" };
    bool stopped { false };
    void stopQMLSource() { stopped = true; }
    void loadHomeScreen(bool forceOntoHomeScreen);
};

#include "tablet-home-visibility-test.moc"
#include "production.inc"

int main(int argc, char** argv) {
    QCoreApplication application(argc, argv);
    for (bool shown : { false, true }) {
        for (bool force : { false, true }) {
            TabletProxy tablet;
            tablet.window.root.shown = shown;
            // People resets to Home from its tabletShownChanged(false)
            // handler. Cleanup must not reopen the just-dismissed tablet.
            tablet.loadHomeScreen(force);
            if (tablet.window.root.shown != shown) return 1;
            if (tablet.window.root.source != TABLET_HOME_SOURCE_URL) return 2;
            if (tablet._state != TabletProxy::State::Home) return 3;
            if (tablet._currentPathLoaded != TABLET_HOME_SOURCE_URL) return 4;
        }
    }
    TabletProxy desktop;
    desktop._screenSpaceMode = false;
    desktop.window.root.shown = true;
    desktop.loadHomeScreen(false);
    if (desktop.window.root.shown || !desktop.stopped) return 5;
}
