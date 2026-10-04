// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Owned CPU-only Qt event-routing scaffold, not a native Interface proof.
#include "world-key-route.h"
#include <QMainWindow>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickRenderControl>
#include <QTextStream>
#include <QEventLoop>
#include <QTimer>
#include <cassert>
class Application : public QApplication {
    Q_OBJECT
public:
    using QApplication::QApplication;
    int presses { 0 }, releases { 0 };
    bool event(QEvent* event) override {
        if(event->type()==QEvent::KeyPress){ ++presses; return true; }
        if(event->type()==QEvent::KeyRelease){ ++releases; return true; }
        return QApplication::event(event);
    }
};
class MainWindow : public QMainWindow { Q_OBJECT public: using QMainWindow::QMainWindow; };
class GLCanvas : public QWidget {
    Q_OBJECT
public:
    using QWidget::QWidget;
    // Exact f91 GLWidget keyboard branch: no custom Controller/Emote behavior.
    bool event(QEvent* event) override {
        if(event->type()==QEvent::KeyPress || event->type()==QEvent::KeyRelease)
            if(QCoreApplication::sendEvent(QCoreApplication::instance(),event))return true;
        return QWidget::event(event);
    }
};
class OwnedRenderControl : public QQuickRenderControl {
public:
    QWindow* proxy {nullptr};
    QWindow* renderWindow(QPoint* offset) override {if(offset)*offset=QPoint();return proxy;}
};
class NativeUiFilter : public QObject {
public:
    QQuickWindow* window; QSet<int> consumed;
    explicit NativeUiFilter(QQuickWindow* value):window(value){}
    bool eventFilter(QObject*,QEvent* event) override {
        if(event->type()!=QEvent::KeyPress && event->type()!=QEvent::KeyRelease)return false;
        auto* key=static_cast<QKeyEvent*>(event);
        event->ignore();
        bool accepted=QCoreApplication::sendEvent(window,event) && event->isAccepted();
        // f91 OffscreenUi suppresses releases belonging to consumed presses.
        if(accepted && event->type()==QEvent::KeyPress)consumed.insert(key->key());
        if(event->type()==QEvent::KeyRelease && consumed.remove(key->key()))return true;
        return accepted;
    }
};
class Body : public QQuickItem {
public:
    bool destroyHelper {false}; QObject* helper {nullptr};
    void keyPressEvent(QKeyEvent* event) override { if(destroyHelper){delete helper;helper=nullptr;} event->ignore(); }
    void keyReleaseEvent(QKeyEvent* event) override {event->ignore();}
};
int main(int argc,char** argv) {
    Application app(argc,argv);
    MainWindow main; auto* canvas=new GLCanvas;main.setCentralWidget(canvas);main.resize(600,600);main.show();
    OwnedRenderControl control;control.proxy=main.windowHandle();QQuickWindow window(&control);
    window.setGeometry(0,0,600,600);window.contentItem()->setWidth(600);window.contentItem()->setHeight(600);
    // Observe real own proxy activation before the original focus assertions.
    // Do not send a synthetic focus event or alter any activeFocus flag.
    {
        QEventLoop readiness;QTimer deadline;deadline.setSingleShot(true);
        auto ownProxyActive=[&](){return main.windowHandle()&&
            QGuiApplication::focusWindow()==main.windowHandle()&&
            main.isActiveWindow()&&main.isVisible()&&main.isEnabled();};
        QObject::connect(&app,&QGuiApplication::focusWindowChanged,&readiness,[&](QWindow*){
            if(ownProxyActive())readiness.quit();
        });
        QObject::connect(&deadline,&QTimer::timeout,&readiness,&QEventLoop::quit);
        main.activateWindow();
        if(!ownProxyActive()){deadline.start(2000);readiness.exec();}
        assert(ownProxyActive());
    }
    QQuickItem owner;owner.setParentItem(window.contentItem());QObject helper(&owner);
    QQuickItem tablet;tablet.setParentItem(window.contentItem());tablet.setObjectName("tabletRoot");
    tablet.setProperty("shown",false);tablet.setVisible(false);tablet.setEnabled(false);
    Body body;body.setParentItem(window.contentItem());body.forceActiveFocus();
    NativeUiFilter filter(&window);canvas->installEventFilter(&filter);
    assert(BrowserWorldKey::ready(&helper,&owner,window.contentItem()));
    assert(BrowserWorldKey::click(&helper,&owner,window.contentItem()));
    assert(app.presses==1&&app.releases==1);
    // Original native UI keeps first refusal, with no direct Application fallback.
    QQmlEngine engine;
    QQmlComponent component(&engine);
    component.setData("import QtQuick 2.7; Item { focus:true; Keys.onPressed:event.accepted=true }",QUrl());
    auto* consuming=qobject_cast<QQuickItem*>(component.create());assert(consuming);
    consuming->setParentItem(window.contentItem());consuming->forceActiveFocus();
    assert(BrowserWorldKey::click(&helper,&owner,window.contentItem()));
    assert(app.presses==1&&app.releases==1);delete consuming;body.forceActiveFocus();
    tablet.setVisible(true);assert(!BrowserWorldKey::ready(&helper,&owner,window.contentItem()));
    assert(!BrowserWorldKey::click(&helper,&owner,window.contentItem()));tablet.setVisible(false);
    tablet.setEnabled(true);assert(!BrowserWorldKey::ready(&helper,&owner,window.contentItem()));tablet.setEnabled(false);
    tablet.setProperty("shown",true);assert(!BrowserWorldKey::ready(&helper,&owner,window.contentItem()));tablet.setProperty("shown",false);
    QQuickItem dialog;dialog.setParentItem(window.contentItem());dialog.setProperty("shown",true);
    assert(!BrowserWorldKey::ready(&helper,&owner,window.contentItem()));dialog.setVisible(false);
    component.setData("import QtQuick 2.7; TextInput { width:200; height:50; text:'seed'; readOnly:true }",QUrl());
    auto* editor=qobject_cast<QQuickItem*>(component.create());assert(editor);editor->setParentItem(window.contentItem());
    assert(!BrowserWorldKey::ready(&helper,&owner,window.contentItem()));editor->setVisible(false);
    assert(BrowserWorldKey::ready(&helper,&owner,window.contentItem()));
    // Readonly fields still consume selection/copy keys even when Qt disables IME.
    assert(editor->inherits("QQuickTextInput"));
    assert(!editor->flags().testFlag(QQuickItem::ItemAcceptsInputMethod));
    editor->setVisible(true);editor->setEnabled(false);
    assert(BrowserWorldKey::ready(&helper,&owner,window.contentItem()));
    editor->setEnabled(true);
    assert(!BrowserWorldKey::ready(&helper,&owner,window.contentItem()));
    assert(!BrowserWorldKey::click(&helper,&owner,window.contentItem()));
    editor->setVisible(false);
    const QByteArray controls[] = {
        "import QtQuick 2.7; TextEdit { width:200; height:50; text:'seed'; readOnly:true }",
        "import QtQuick 2.7; TextInput { property int authoredSubclass:1; width:200; height:50; text:'seed'; readOnly:true }",
        "import QtQuick 2.7; TextEdit { property int authoredSubclass:1; width:200; height:50; text:'seed'; readOnly:true }"
    };
    for(const auto& source:controls) {
        component.setData(source,QUrl());
        auto* readonly=qobject_cast<QQuickItem*>(component.create());assert(readonly);
        readonly->setParentItem(window.contentItem());
        assert(readonly->inherits("QQuickTextInput")||readonly->inherits("QQuickTextEdit"));
        assert(readonly->property("readOnly").toBool());
        assert(!BrowserWorldKey::ready(&helper,&owner,window.contentItem()));
        assert(!BrowserWorldKey::click(&helper,&owner,window.contentItem()));
        assert(app.presses==1&&app.releases==1);
        readonly->setVisible(false);
        assert(BrowserWorldKey::ready(&helper,&owner,window.contentItem()));
        readonly->setVisible(true);readonly->setEnabled(false);
        assert(BrowserWorldKey::ready(&helper,&owner,window.contentItem()));
        readonly->setEnabled(true);
        assert(!BrowserWorldKey::ready(&helper,&owner,window.contentItem()));
        delete readonly;
        assert(BrowserWorldKey::ready(&helper,&owner,window.contentItem()));
    }
    QQuickItem foreign;assert(!BrowserWorldKey::ready(&helper,&owner,&foreign));
    control.proxy=nullptr;assert(!BrowserWorldKey::ready(&helper,&owner,window.contentItem()));
    assert(app.presses==1&&app.releases==1);delete editor;
    QTextStream(stdout)<<"OWNED_WORLD_KEY_CONTRACTS=passed\n";
    return 0;
}
#include "world-key-route-test.moc"
