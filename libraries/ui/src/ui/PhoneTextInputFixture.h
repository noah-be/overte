// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QString>
#include <QJsonObject>
#include <QPointer>
#include <QQuickItem>

class PhoneTextInputFixture {
public:
    bool focus(QQuickItem* panel);
    bool dismiss();
    QJsonObject snapshot(bool nativeKeyboardVisible) const;
    QQuickItem* panel() const { return _panel; }
    QString lastFailure() const { return _lastFailure; }
private:
    QPointer<QQuickItem> _panel;
    QPointer<QQuickItem> _field;
    QString _lastFailure;
};
