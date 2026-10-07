// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "application-key-route.h"
#include <QSet>
#include <QVariant>

namespace BrowserWorldKey {
inline bool closedUi(QObject* helper, QQuickItem* owner, QObject* requested, QPointer<QQuickWindow>& window) {
    window=owner ? owner->window() : nullptr;
    auto* root=qobject_cast<QQuickItem*>(requested);
    if(!helper||!owner||!window||!root||QCoreApplication::closingDown()||
       helper->thread()!=QThread::currentThread()||owner->thread()!=QThread::currentThread()||
       window->thread()!=QThread::currentThread()||root->thread()!=QThread::currentThread()||
       root!=window->contentItem()||root->window()!=window||
       !BrowserApplicationKey::descendant(owner,root))return false;
    const QPointer<QObject> capturedHelper(helper);
    const QPointer<QQuickItem> capturedOwner(owner),capturedRoot(root);
    struct Node { QPointer<QQuickItem> item; int depth; };
    QVector<Node> pending {{root,0}};
    QSet<QQuickItem*> seen;
    int tabletRoots=0;
    while(!pending.isEmpty()) {
        const auto node=pending.takeLast();const auto item=node.item;
        if(!item||item->window()!=window||item->thread()!=QThread::currentThread()||seen.contains(item.data())||seen.size()>=4096)return false;
        seen.insert(item.data());
        if(item->objectName()==QLatin1String("tabletRoot")) {
            if(++tabletRoots!=1||item->isVisible()||item->isEnabled())return false;
            const auto shown=item->property("shown");
            if(!item||!capturedHelper||!capturedOwner||!capturedRoot||!window)return false;
            if(shown.type()!=QVariant::Bool||shown.toBool())return false;
        }
        // A hidden native branch cannot receive normal keys. Never modify it.
        if(item!=root&&!item->isVisible())continue;
        if(node.depth>24)return false;
        if(item->isVisible()&&item->isEnabled()) {
            const auto shown=item->property("shown");
            if(!item||!capturedHelper||!capturedOwner||!capturedRoot||!window)return false;
            if(shown.isValid()&&shown.type()!=QVariant::Bool)return false;
            if(shown.isValid()&&shown.toBool()&&item->objectName()!=QLatin1String("com.highfidelity.interface.toolbar.system"))return false;
            if(item->inherits("QQuickPopupItem")||item->inherits("QQuickTextInput")||
               item->inherits("QQuickTextEdit")||item->flags().testFlag(QQuickItem::ItemAcceptsInputMethod)||
               item->inherits("QtWebEngineCore::RenderWidgetHostViewQtDelegateQuick"))return false;
        }
        const auto children=item->childItems();
        if(children.size()>4096-seen.size()-pending.size())return false;
        for(auto* child:children)pending.push_back({child,node.depth+1});
    }
    // Unknown/missing/duplicate native roots never grant world-input authority.
    return tabletRoots==1&&capturedHelper&&capturedOwner&&capturedRoot&&window;
}
inline bool ready(QObject* helper,QQuickItem* owner,QObject* requested) {
    QPointer<QQuickWindow> window;
    if(!closedUi(helper,owner,requested,window))return false;
    BrowserApplicationKey::Target target;
    return BrowserApplicationKey::nativeTarget(target)&&target.main->windowHandle()&&
        QQuickRenderControl::renderWindowFor(window)==target.main->windowHandle();
}
inline bool click(QObject* helper,QQuickItem* owner,QObject* requested) {
    const QPointer<QObject> capturedHelper(helper);
    const QPointer<QQuickItem> capturedOwner(owner);
    const QPointer<QQuickItem> capturedRoot(qobject_cast<QQuickItem*>(requested));
    QPointer<QQuickWindow> window;
    if(!closedUi(helper,owner,requested,window))return false;
    BrowserApplicationKey::Target target;
    if(!BrowserApplicationKey::nativeTarget(target)||!target.main->windowHandle()||
       QQuickRenderControl::renderWindowFor(window)!=target.main->windowHandle())return false;
    // The original filter still gets first refusal. Never deliver directly to
    // Application/Controller or retry a consumed press by another route.
    QKeyEvent press(QEvent::KeyPress,Qt::Key_X,Qt::NoModifier,QStringLiteral("x"),false,1);
    press.ignore();
    const bool pressed=QCoreApplication::sendEvent(target.canvas,&press);
    if(!BrowserApplicationKey::targetCurrent(target))return false;
    QKeyEvent release(QEvent::KeyRelease,Qt::Key_X,Qt::NoModifier,QStringLiteral("x"),false,1);
    release.ignore();
    const bool released=QCoreApplication::sendEvent(target.canvas,&release);
    return pressed&&released&&capturedHelper&&capturedOwner&&capturedRoot&&window;
}
}
