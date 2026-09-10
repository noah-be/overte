// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQuickView>
#include <QQuickItem>
#include <QQmlEngine>
#include <QTest>
#include <cassert>
#include <iostream>
#include <functional>
int main(int argc,char**argv){
 QGuiApplication app(argc,argv);assert(argc==3);QQuickView view;view.setColor(Qt::transparent);
 view.setSource(QUrl::fromLocalFile(argv[1]));QTest::qWait(50);assert(view.status()==QQuickView::Ready);view.show();
 auto root=view.rootObject();auto window=root->findChild<QQuickItem*>("window");auto effect=root->findChild<QQuickItem*>("effectUnderTest");assert(window&&effect);
 bool initiallyHidden=QString::fromLocal8Bit(argv[2])=="tablet";assert(effect->isVisible()!=initiallyHidden);if(initiallyHidden)effect->setVisible(true);
 auto wait=[&](std::function<bool(const QImage&)> predicate){for(int i=0;i<75;++i){QTest::qWait(20);auto image=view.grabWindow();if(!image.isNull()&&predicate(image))return;}assert(false&&"retained shadow pixels did not update");};
 wait([](const QImage&i){return i.pixelColor(64,64)==QColor(Qt::red)&&i.pixelColor(64,90).alpha()>0;});
 // Repaint the same captured source when spread changes: no new source event.
 effect->setProperty("spread",0.0);QTest::qWait(80);
 int baseAlpha=view.grabWindow().pixelColor(64,90).alpha();assert(baseAlpha>0&&baseAlpha<255);
 effect->setProperty("spread",0.5);
 wait([&](const QImage&i){return i.pixelColor(64,90).alpha()>baseAlpha;});
 effect->setProperty("spread",1.0);
 int fullAlpha=effect->property("color").value<QColor>().alpha();
 wait([&](const QImage&i){return i.pixelColor(64,90).alpha()==fullAlpha&&i.pixelColor(2,2).alpha()==0;});
 effect->setProperty("spread",0.0);
 wait([&](const QImage&i){return i.pixelColor(64,90).alpha()==baseAlpha;});
 auto source=effect->property("source").value<QQuickItem*>();assert(source);
 source->setVisible(false);wait([](const QImage&i){return i.pixelColor(64,64).alpha()==0&&i.pixelColor(64,90).alpha()==0;});source->setVisible(true);
 wait([](const QImage&i){return i.pixelColor(64,90).alpha()>0;});
 window->setWidth(80);window->setHeight(40);wait([](const QImage&i){return i.pixelColor(64,62)==QColor(Qt::red)&&i.pixelColor(64,66).alpha()>0;});
 effect->setVisible(false);wait([](const QImage&i){return i.pixelColor(64,62)==QColor(Qt::red)&&i.pixelColor(64,66).alpha()==0;});
 std::cout<<"PASS actual retained effect binding, source visibility, resize and effect visibility\n";
}
