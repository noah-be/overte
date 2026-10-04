// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Owned CPU-only Qt event-routing scaffold, not a native Interface proof.
#include "application-key-route.h"
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
    window.setGeometry(0,0,600,600);
    window.contentItem()->setWidth(600);window.contentItem()->setHeight(600);
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
    QQuickItem surface;surface.setParentItem(window.contentItem());surface.setWidth(200);surface.setHeight(80);
    QQuickItem owner;owner.setParentItem(window.contentItem());QObject helper(&owner);
    NativeUiFilter filter(&window);canvas->installEventFilter(&filter);
    Body body;body.setParentItem(&surface);body.forceActiveFocus();
    assert(body.hasActiveFocus());
    assert(BrowserApplicationKey::click(&helper,&owner,&surface,"x",0));
    assert(app.presses==1&&app.releases==1);
    QQmlEngine engine;
    for(const auto& mode: {QString("Normal"),QString("Password")}) {
        QQmlComponent component(&engine);
        component.setData(("import QtQuick 2.7; TextInput { width:200; height:50; focus:true; text: \"seed\"; echoMode: TextInput."+mode+" }").toUtf8(),QUrl());
        assert(!component.isError());
        auto* item=qobject_cast<QQuickItem*>(component.create());assert(item);
        item->setParentItem(&surface);item->forceActiveFocus();
        assert(item->hasActiveFocus());const auto presses=app.presses,releases=app.releases;
        assert(BrowserApplicationKey::click(&helper,&owner,&surface,"x",0));
        assert(item->property("text").toString().count('x')==1 && item->property("text").toString().size()==5);
        assert(app.presses==presses&&app.releases==releases);
        assert(filter.consumed.isEmpty());delete item;
    }
    body.forceActiveFocus();
    assert(!BrowserApplicationKey::click(&helper,&owner,&surface,"\n",0));
    assert(!BrowserApplicationKey::click(&helper,&owner,&surface,"x",Qt::KeypadModifier));
    QQuickItem foreign;foreign.setParentItem(window.contentItem());foreign.forceActiveFocus();
    assert(!BrowserApplicationKey::click(&helper,&owner,&surface,"x",0));
    body.forceActiveFocus();
    control.proxy=nullptr;assert(!BrowserApplicationKey::click(&helper,&owner,&surface,"x",0));control.proxy=main.windowHandle();
    surface.setVisible(false);
    assert(!BrowserApplicationKey::click(&helper,&owner,&surface,"x",0));surface.setVisible(true);
    {MainWindow duplicate;duplicate.show();assert(!BrowserApplicationKey::click(&helper,&owner,&surface,"x",0));}
    {auto* duplicate=new GLCanvas(canvas);duplicate->show();assert(!BrowserApplicationKey::click(&helper,&owner,&surface,"x",0));delete duplicate;}
    const auto presses=app.presses,releases=app.releases;
    body.destroyHelper=true;body.helper=new QObject(&owner);
    assert(!BrowserApplicationKey::click(body.helper,&owner,&surface,"x",0));
    assert(app.presses==presses+1&&app.releases==releases+1);
    QTextStream(stdout)<<"{\"completed\":true,\"nativeInterfaceProof\":false,\"originalFallbackPairs\":2,\"actualEditorVariants\":2,\"protectedGlobalKeyPairs\":0,\"refusalCases\":7}\n";
    return 0;
}
#include "application-key-route-test.moc"
