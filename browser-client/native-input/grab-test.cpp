// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QQuickWindow>
#include <QTimer>
#include <QPointer>
#include <limits>
#include <cstdio>

class GrabAssertions : public QObject {
    Q_OBJECT
public:
    QObject* plugin { nullptr };
    QQuickWindow* window { nullptr };
    QQuickWindow* foreign { nullptr };
    QQuickItem* owner { nullptr };
    int received { 0 };
    bool capture(QObject* target, double token) {
        bool accepted = false;
        if (!QMetaObject::invokeMethod(plugin, "grabPrivateGui", Q_RETURN_ARG(bool, accepted),
                Q_ARG(QObject*, target), Q_ARG(double, token))) fail("Missing private GUI capture API");
        return accepted;
    }
    void fail(const char* message) {
        std::fprintf(stderr, "Private GUI capture assertion failed: %s\n", message);
        QCoreApplication::exit(1);
    }
public slots:
    void ready(double token, QObject* object) {
        if(token==9 && received==1){
            if(object){fail("Reparented owner cannot receive prior-window pixels");return;}
            received++;
            QTimer::singleShot(0,this,[this]{
                owner->setParentItem(window->contentItem());
                if(!capture(window->contentItem(),11)){fail("Completed revoked grab still holds allocation");return;}
                // Destroying the receiver during a pending GPU operation must
                // disconnect its callback; no raw this/item pointer may escape.
                delete plugin;plugin=nullptr;
                QTimer::singleShot(100,this,[this]{
                    if(received!=2){fail("Destroyed receiver emitted a late callback");return;}
                    std::puts("Engine-free Qt GUI root: exact pixels, bounded token/size, foreign/descendant refusal, single pending, reparent revocation, receiver destruction and result release passed");
                    QCoreApplication::exit(0);
                });
            });
            return;
        }
        auto* result = qobject_cast<QQuickItemGrabResult*>(object);
        if (token != 7 || !result || received++ != 0) { fail("Uncorrelated or duplicate callback"); return; }
        const auto image = result->image();
        if (image.size() != QSize(64,64)) { fail("Actual root capture dimensions"); return; }
        const auto pixel = image.pixelColor(32,32);
        if (qAbs(pixel.red()-32)>1 || qAbs(pixel.green()-192)>1 || qAbs(pixel.blue()-64)>1) {
            fail("Actual engine-free GUI root pixels"); return;
        }
        if (capture(window->contentItem(),8)) { fail("Reentrant callback cannot allocate a second GPU grab"); return; }
        // The signal result must be released once delivery completes, without a
        // shared-pointer cycle retained by the ready lambda.
        QPointer<QObject> lifetime(result);
        QTimer::singleShot(0, this, [this,lifetime] {
            if (lifetime) { fail("Completed capture result was retained"); return; }
            if(!capture(window->contentItem(),9)){fail("Completed capture still holds allocation");return;}
            owner->setParentItem(foreign->contentItem());
        });
    }
};

int main(int argc,char** argv) {
    QGuiApplication application(argc,argv);
    if(argc!=2)return 2;
    QQmlEngine engine;
    engine.addImportPath(QString::fromLocal8Bit(argv[1]));
    QQuickWindow window, foreign;
    window.resize(64,64);foreign.resize(64,64);
    QQmlComponent component(&engine);
    component.setData("import QtQuick 2.7\nimport BrowserNativeInput 1.0\nRectangle { width:64; height:64; color: '#20c040'; NativeInput { objectName: 'capturePlugin' } }",QUrl());
    auto* owner=qobject_cast<QQuickItem*>(component.create());
    if(!owner){std::fprintf(stderr,"%s\n",qPrintable(component.errorString()));return 3;}
    owner->setParent(window.contentItem());owner->setParentItem(window.contentItem());
    auto* plugin=owner->findChild<QObject*>(QStringLiteral("capturePlugin"));
    if(!plugin || qmlEngine(window.contentItem())!=nullptr || qmlEngine(owner)==nullptr)return 4;
    GrabAssertions assertions;assertions.plugin=plugin;assertions.window=&window;assertions.foreign=&foreign;assertions.owner=owner;
    if(!QObject::connect(plugin,SIGNAL(privateGuiReady(double,QObject*)),&assertions,SLOT(ready(double,QObject*))))return 5;
    window.show();
    QTimer::singleShot(100,&assertions,[&] {
        for(double token:{0.0,-1.0,1.5,std::numeric_limits<double>::infinity(),9007199254740992.0})
            if(assertions.capture(window.contentItem(),token)){assertions.fail("Invalid token accepted");return;}
        if(assertions.capture(foreign.contentItem(),1) || assertions.capture(owner,2) || assertions.capture(nullptr,3)){
            assertions.fail("Foreign window, descendant or null target accepted");return;
        }
        window.contentItem()->setWidth(2049);
        if(assertions.capture(window.contentItem(),4)){assertions.fail("Oversized root accepted");return;}
        window.contentItem()->setWidth(64);
        if(!assertions.capture(window.contentItem(),7)){assertions.fail("Engine-free own root refused");return;}
        if(assertions.capture(window.contentItem(),8)){assertions.fail("Concurrent root grab accepted");return;}
    });
    QTimer::singleShot(10000,&application,[&]{assertions.fail("Actual GUI capture deadline");});
    return application.exec();
}
#include "grab-test.moc"
