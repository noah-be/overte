// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QObject>

// Only the application/UI dependency is substituted. The script-facing
// production QObject, its moc metadata and queued dispatch are compiled intact.
class DialogsManager : public QObject {
    Q_OBJECT
public:
    bool visible { false };
    int toggles { 0 };
    int hides { 0 };
    void setVisible(bool value) { visible = value; emit addressBarShown(value); }
public slots:
    void showAddressBar() { setVisible(true); }
    void hideAddressBar() { ++hides; setVisible(false); }
    void toggleAddressBar() { ++toggles; setVisible(!visible); }
    void showLoginDialog() {}
    void showFeed() {}
signals:
    void addressBarShown(bool visible);
};
