// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include "PhoneTextInputFixture.h"
#include <QGuiApplication>
#include <QInputMethod>
#include <QThread>

bool PhoneTextInputFixture::focus(QQuickItem* panel) {
    Q_ASSERT(QThread::currentThread() == qApp->thread());
    _lastFailure.clear();
    if (!panel) { _lastFailure = "panel-missing"; return false; }
    auto field = panel->findChild<QQuickItem*>("controlled.text");
    if (!field) { _lastFailure = "field-missing"; return false; }
    if (panel->metaObject()->indexOfProperty("submittedCount") < 0) {
        _lastFailure = "submitted-property-missing"; return false;
    }
    _panel = panel;
    _field = field;
    _panel->setVisible(true);
    if (!_field->setProperty("text", QString())) { _lastFailure = "text-write-rejected"; return false; }
    _field->forceActiveFocus(Qt::OtherFocusReason);
    qApp->inputMethod()->show();
    return true;
}

bool PhoneTextInputFixture::dismiss() {
    Q_ASSERT(QThread::currentThread() == qApp->thread());
    if (!_panel || !_field) { return false; }
    _field->setFocus(false);
    _panel->setFocus(false);
    _panel->setVisible(false);
    qApp->inputMethod()->hide();
    return true;
}

QJsonObject PhoneTextInputFixture::snapshot(bool nativeKeyboardVisible) const {
    Q_ASSERT(QThread::currentThread() == qApp->thread());
    if (!_panel || !_field) { return {}; }
    return { {"schemaVersion", 1}, {"value", _field->property("text").toString()},
        {"focused", _field->hasActiveFocus()}, {"keyboardVisible", nativeKeyboardVisible},
        {"submittedCount", _panel->property("submittedCount").toInt()} };
}
