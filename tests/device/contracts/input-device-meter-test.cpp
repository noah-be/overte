// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQuickView>
#include <QQuickItem>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlPropertyMap>
#include <QTest>
#include <limits>
#include <cmath>
#include <cassert>
#include <iostream>
int main(int argc,char**argv){
 QGuiApplication app(argc,argv);assert(argc==2);
 qmlRegisterSingletonType<QQmlPropertyMap>("TabletScriptingInterface",1,0,"TabletEnums",[](QQmlEngine*,QJSEngine*)->QObject*{auto m=new QQmlPropertyMap;m->insert("ButtonClick",1);m->insert("ButtonHover",2);return m;});
 QQuickView view;view.setColor(Qt::transparent);QQmlPropertyMap audio;audio.insert("inputLevel",0.0);audio.insert("clipping",false);audio.insert("muted",false);audio.insert("pushToTalk",false);audio.insert("pushingToTalk",false);view.rootContext()->setContextProperty("AudioScriptingInterface",&audio);
 QQmlComponent tablet(view.engine());tablet.setData("import QtQuick 2.5\nQtObject { function playSound(sound) {} }",QUrl());auto tabletObject=tablet.create();assert(tabletObject);view.rootContext()->setContextProperty("Tablet",tabletObject);
 view.setSource(QUrl::fromLocalFile(argv[1]));assert(view.status()==QQuickView::Ready);auto root=view.rootObject();root->setWidth(64);root->setHeight(64);view.resize(64,64);view.show();
 auto pixels=[&]{QTest::qWait(150);auto p=view.grabWindow();assert(!p.isNull());int visible=0;for(int y=0;y<p.height();++y)for(int x=0;x<p.width();++x)if(p.pixelColor(x,y).alpha()>150)++visible;assert(visible>5);assert(p.pixelColor(0,0).alpha()==0&&p.pixelColor(63,63).alpha()==0);return p;};auto count=[&](const QImage& im,bool green,int from,int to){int n=0;for(int y=from;y<to;++y)for(int x=0;x<64;++x){auto p=im.pixelColor(x,y);if(p.alpha()>160&&(green?(p.green()>p.red()+40):(abs(p.red()-178)<3&&abs(p.green()-178)<3&&abs(p.blue()-178)<3)))++n;}return n;};
 auto initial=pixels();audio.insert("inputLevel",0.5);auto half=pixels();assert(count(half,false,0,32)>3);assert(count(half,true,32,64)>3);
 audio.insert("inputLevel",1.0);auto full=pixels();assert(count(full,false,0,64)==0);assert(count(full,true,32,64)>3);
 for(double raw:{-1.0,2.0,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}){audio.insert("inputLevel",raw);pixels();double expected=std::isfinite(raw)?std::max(0.0,std::min(1.0,raw)):0.0;assert(root->property("level").toDouble()==expected);}
 audio.insert("inputLevel",0.5);audio.insert("muted",true);auto muted=pixels();assert(count(muted,false,0,64)==0);assert(count(muted,true,0,64)==0);audio.insert("muted",false);audio.insert("clipping",true);auto clipped=pixels();assert(count(clipped,true,0,64)==0);
 audio.insert("clipping",false);audio.insert("inputLevel",0.0);QTest::mouseClick(&view,Qt::LeftButton,Qt::NoModifier,QPoint(32,32));assert(audio.value("muted").toBool());audio.insert("muted",false);audio.insert("pushToTalk",true);QTest::mousePress(&view,Qt::LeftButton,Qt::NoModifier,QPoint(32,32));assert(audio.value("pushingToTalk").toBool());QTest::mouseRelease(&view,Qt::LeftButton,Qt::NoModifier,QPoint(32,32));assert(!audio.value("pushingToTalk").toBool());
 QTest::mousePress(&view,Qt::LeftButton,Qt::NoModifier,QPoint(32,32));assert(audio.value("pushingToTalk").toBool());
 QQuickItem* mouseArea=nullptr;for(auto item:root->findChildren<QQuickItem*>())if(item->inherits("QQuickMouseArea"))mouseArea=item;assert(mouseArea);mouseArea->ungrabMouse();assert(!audio.value("pushingToTalk").toBool());
 QTest::mouseRelease(&view,Qt::LeftButton,Qt::NoModifier,QPoint(32,32));
 QTest::mousePress(&view,Qt::LeftButton,Qt::NoModifier,QPoint(32,32));assert(audio.value("pushingToTalk").toBool());audio.insert("pushToTalk",false);assert(!audio.value("pushingToTalk").toBool());QTest::mouseRelease(&view,Qt::LeftButton,Qt::NoModifier,QPoint(32,32));
 audio.insert("pushToTalk",true);QTest::mousePress(&view,Qt::LeftButton,Qt::NoModifier,QPoint(32,32));assert(audio.value("pushingToTalk").toBool());root->setVisible(false);assert(!audio.value("pushingToTalk").toBool());
 delete tabletObject;
}
