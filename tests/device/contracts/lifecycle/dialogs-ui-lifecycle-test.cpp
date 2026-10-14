// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QObject>
#include <QVariant>
#include <iostream>
#include <stdexcept>
#include <DependencyManager.h>

static void require(bool value, const char* message) {
    if (!value) { throw std::runtime_error(message); }
}

class TabletProxy : public QObject {
public:
    bool loaded { false };
    bool isPathLoaded(const QVariant&) { return loaded; }
    void loadQMLSource(const QVariant&) { loaded = true; }
    void gotoHomeScreen() { loaded = false; }
};
class TabletScriptingInterface {
public:
    TabletProxy tablet;
    QObject* getTablet(const char*) { return &tablet; }
};
class HMDScriptingInterface {
public:
    bool open { false };
    bool getShouldShowTablet() { return open; }
    void openTablet() { open = true; }
    void closeTablet() { open = false; }
    int getCurrentTabletScreenID() { return 7; }
};
class OffscreenUi {
public:
    bool visible { false };
    bool isVisible(const char*) { return visible; }
};
class AddressBarDialog {
public:
    static void show() { DependencyManager::get<OffscreenUi>()->visible = true; }
    static void hide() { DependencyManager::get<OffscreenUi>()->visible = false; }
};
class ApplicationBoundary {
public:
    int focus { 99 };
    void setKeyboardFocusEntity(int value) { focus = value; }
};
static ApplicationBoundary applicationBoundary;
#undef qApp
#define qApp (&applicationBoundary)
static const int UNKNOWN_ENTITY_ID = 0;
static const QVariant TABLET_ADDRESS_DIALOG = "hifi/tablet/TabletAddressDialog.qml";

class DialogsManager : public QObject {
    Q_OBJECT
public:
    bool _addressBarVisible { false };
    void showAddressBar();
    void hideAddressBar();
    void toggleAddressBar();
    void setAddressBarVisible(bool visible);
#include "production-dialogs-observer.inc"
signals:
    void addressBarShown(bool visible);
};

// Unchanged production method bodies; only rendering, HMD and focus boundaries
// above are replaced. Both actual Phone and tablet preprocessor paths execute.
#include "production-dialogs-lifecycle.inc"

static bool visible() {
#if defined(ANDROID_APP_PHONE_INTERFACE)
    return DependencyManager::get<OffscreenUi>()->visible;
#else
    return DependencyManager::get<TabletScriptingInterface>()->tablet.loaded;
#endif
}
static void externalClose() {
    DependencyManager::get<OffscreenUi>()->visible = false;
    DependencyManager::get<TabletScriptingInterface>()->tablet.loaded = false;
}

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    try {
        DialogsManager dialogs;
        dialogs.showAddressBar();
        require(visible() && dialogs._addressBarVisible, "native show failed");
        dialogs.hideAddressBar();
        require(!visible() && !dialogs._addressBarVisible, "native hide failed");
        applicationBoundary.focus = 99;
        dialogs.hideAddressBar();
        require(applicationBoundary.focus == 99, "hiding closed GOTO cleared another app's focus");
        dialogs.showAddressBar();
        externalClose();
        dialogs.emitAddressBarShown(false);
        require(!dialogs._addressBarVisible, "native external-close observer left visibility stale");
        dialogs.toggleAddressBar();
        require(visible(), "GOTO did not reopen after external close");
        externalClose();
        applicationBoundary.focus = 99;
        dialogs.hideAddressBar();
        require(!visible() && !dialogs._addressBarVisible && applicationBoundary.focus == 99,
                "missing close notification disturbed another app during hide");
        std::cout << "PASS actual native show/hide/toggle/visibility observer and idle focus\n";
    } catch (const std::exception& error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
    return 0;
}

#include "dialogs-ui-lifecycle-test.moc"
