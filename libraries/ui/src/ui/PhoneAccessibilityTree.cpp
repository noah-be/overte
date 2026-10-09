// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include "PhoneAccessibilityTree.h"

#include <QAccessible>
#include <QAccessibleActionInterface>
#include <QAccessibleTextInterface>
#include <QDateTime>
#include <QGuiApplication>
#include <QInputMethod>
#include <QJsonArray>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQmlProperty>
#include <QThread>
#include <functional>

namespace {
QString semanticIdentifier(QQuickItem* item) {
    const auto semantic = item->property("semanticId").toString();
    return semantic.isEmpty() ? item->objectName() : semantic;
}

QString classForRole(QAccessible::Role role) {
    switch (role) {
        case QAccessible::Button: return "android.widget.Button";
        case QAccessible::CheckBox: return "android.widget.CheckBox";
        case QAccessible::RadioButton: return "android.widget.RadioButton";
        case QAccessible::EditableText: return "android.widget.EditText";
        case QAccessible::StaticText: return "android.widget.TextView";
        case QAccessible::Slider: return "android.widget.SeekBar";
        default: return "android.view.View";
    }
}
}

QJsonObject PhoneAccessibilityTree::snapshot(QQuickItem* root, const QSize& surfaceSize) {
    Q_ASSERT(QThread::currentThread() == qApp->thread());
    _items.clear();
    QJsonArray nodes;
    if (!root || root->width() <= 0 || root->height() <= 0 || surfaceSize.isEmpty()) {
        return { {"schemaVersion", 1}, {"ready", false}, {"nodes", nodes} };
    }
    const QRectF viewport(0, 0, root->width(), root->height());
    const qreal scaleX = surfaceSize.width() / root->width();
    const qreal scaleY = surfaceSize.height() / root->height();
    std::function<void(QQuickItem*, int, const QRectF&, int)> visit;
    visit = [&](QQuickItem* item, int parent, const QRectF& clip, int depth) {
        if (!item || depth > 128 || nodes.size() >= 1024 || !item->isVisible() || item->opacity() <= 0) { return; }
        const QRectF rect = item->mapRectToScene(QRectF(0, 0, item->width(), item->height()));
        const QRectF visibleRect = rect.intersected(clip);
        auto accessible = QAccessible::queryAccessibleInterface(item);
        const auto context = QQmlEngine::contextForObject(item);
        const bool ignored = QQmlProperty(item, "Accessible.ignored", context).read().toBool();
        if (accessible && accessible->isValid() && accessible->role() != QAccessible::NoRole
                && !ignored && !visibleRect.isEmpty()) {
            const int identifier = static_cast<int>(QAccessible::uniqueId(accessible));
            if (identifier != -1) {
                auto actions = accessible->actionInterface();
                const auto names = actions ? actions->actionNames() : QStringList();
                const bool editable = accessible->role() == QAccessible::EditableText
                    && accessible->textInterface() != nullptr && !item->property("readOnly").toBool();
                const auto state = accessible->state();
                const auto text = state.passwordEdit ? QString() : accessible->text(QAccessible::Value);
                QJsonObject node {
                    {"id", identifier}, {"parentId", parent},
                    {"className", classForRole(accessible->role())},
                    {"semanticId", semanticIdentifier(item)},
                    {"name", accessible->text(QAccessible::Name)},
                    {"description", accessible->text(QAccessible::Description)},
                    {"text", text}, {"enabled", item->isEnabled()},
                    {"focused", item->hasActiveFocus()},
                    {"focusable", state.focusable || editable},
                    {"editable", editable}, {"password", bool(state.passwordEdit)},
                    {"checkable", accessible->role() == QAccessible::CheckBox || accessible->role() == QAccessible::RadioButton},
                    {"checked", bool(state.checked)},
                    {"clickable", names.contains(QAccessibleActionInterface::pressAction())},
                    {"left", visibleRect.left() * scaleX}, {"top", visibleRect.top() * scaleY},
                    {"right", visibleRect.right() * scaleX}, {"bottom", visibleRect.bottom() * scaleY}
                };
                nodes.append(node);
                _items.insert(identifier, item);
                parent = identifier;
            }
        }
        const auto childClip = item->clip() ? clip.intersected(rect) : clip;
        for (auto child : item->childItems()) { visit(child, parent, childClip, depth + 1); }
    };
    visit(root, -1, viewport, 0);
    return { {"schemaVersion", 1}, {"ready", true},
             {"sampleEpochMs", QDateTime::currentMSecsSinceEpoch()},
             {"surfaceWidth", surfaceSize.width()}, {"surfaceHeight", surfaceSize.height()},
             {"nodes", nodes} };
}

bool PhoneAccessibilityTree::action(int identifier, const QString& action, const QString& text) {
    Q_ASSERT(QThread::currentThread() == qApp->thread());
    auto item = _items.value(identifier);
    if (!item || !item->isVisible() || !item->isEnabled()) { return false; }
    auto accessible = QAccessible::queryAccessibleInterface(item);
    if (!accessible || !accessible->isValid()) { return false; }
    if (action == "set-text") {
        auto content = accessible->textInterface();
        if (accessible->role() != QAccessible::EditableText || !content
                || item->property("readOnly").toBool() || text.size() > 4096) { return false; }
        // Qt 5 and Qt 6 Quick both implement this native value-editing API.
        // Qt 5 does not expose an EditableTextInterface for Quick items.
        accessible->setText(QAccessible::Value, text);
        content->setCursorPosition(content->characterCount());
        return accessible->text(QAccessible::Value) == text;
    }
    auto actions = accessible->actionInterface();
    const auto name = action == "press" ? QAccessibleActionInterface::pressAction()
        : action == "focus" ? QAccessibleActionInterface::setFocusAction() : QString();
    if (name.isEmpty() || !actions || !actions->actionNames().contains(name)) { return false; }
    actions->doAction(name);
    if (action == "focus" && accessible->role() == QAccessible::EditableText
            && !item->property("readOnly").toBool()) { qApp->inputMethod()->show(); }
    return true;
}
