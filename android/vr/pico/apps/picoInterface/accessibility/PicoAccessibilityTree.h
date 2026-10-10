// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <QHash>
#include <QJsonObject>
#include <QPointer>
#include <QQuickItem>
#include <QSize>

// Pico renders Qt Quick into an Android surface, so its offscreen
// QQuickWindow is not itself an Android accessibility window. This tree binds
// actual rendered items and their Qt accessibility actions to that surface.
class PicoAccessibilityTree {
public:
    QJsonObject snapshot(QQuickItem* root, const QSize& surfaceSize);
    bool action(int identifier, const QString& action, const QString& text = QString());

private:
    QHash<int, QPointer<QQuickItem>> _items;
};
