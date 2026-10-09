// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#ifndef overte_QmlPropertyThreadGate_h
#define overte_QmlPropertyThreadGate_h

#include <QMetaProperty>
#include <QPointer>
#include <QThread>
#include <QQmlEngine>

namespace overte {
// QmlFragment buttons are real QML objects, not thread-safe scripting facades.
// Keep native scripting interfaces' existing dispatch policy; only objects
// owned by a QML engine require this GUI-thread property gate.
inline bool qmlPropertyNeedsDispatch(QObject* object) {
    return object && object->thread() != QThread::currentThread() && qmlEngine(object);
}

inline QVariant readQmlProperty(QObject* object, const QMetaProperty& property) {
    if (!qmlPropertyNeedsDispatch(object)) {
        return property.read(object);
    }
    QVariant result;
    const QPointer<QObject> target(object);
    // No V8 values or script callbacks are used on the QML engine's thread.
    // An immediately following read also observes earlier queued writes.
    QMetaObject::invokeMethod(object, [&result, target, property] {
        if (target) {
            result = property.read(target.data());
        }
    }, Qt::BlockingQueuedConnection);
    return result;
}

inline void writeQmlProperty(QObject* object, const QMetaProperty& property, const QVariant& value) {
    if (!qmlPropertyNeedsDispatch(object)) {
        property.write(object, value);
        return;
    }
    const QPointer<QObject> target(object);
    // Do not wait for GUI setters: bindings and notifications can reenter the
    // application. QObject context cancellation drops writes during teardown.
    QMetaObject::invokeMethod(object, [target, property, value] {
        if (target) {
            property.write(target.data(), value);
        }
    }, Qt::QueuedConnection);
}
}

#endif
