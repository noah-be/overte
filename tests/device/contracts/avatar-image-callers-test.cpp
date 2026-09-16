// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQuickView>
#include <QQuickItem>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlPropertyMap>
#include <QQuickImageProvider>
#include <QFile>
#include <QTest>
#include <QImage>
#include <QVariantMap>
#include <cassert>
struct Images:QQuickImageProvider {
 Images():QQuickImageProvider(QQuickImageProvider::Image){}
 QImage requestImage(const QString&,QSize* size,const QSize&) override{QImage i(64,64,QImage::Format_ARGB32_Premultiplied);i.fill(Qt::cyan);*size=i.size();return i;}

};
int main(int argc,char**argv){
 QGuiApplication app(argc,argv);assert(argc==3);QQuickView view;view.setColor(Qt::transparent);
 QQmlPropertyMap account;account.insert("metaverseServerURL",QString());account.insert("loggedIn",false);view.rootContext()->setContextProperty("Account",&account);view.engine()->addImageProvider("fixture",new Images);
 QFile file(argv[1]);assert(file.open(QIODevice::ReadOnly));QQmlComponent component(view.engine());auto url=QUrl::fromLocalFile(argv[2]);component.setData(file.readAll(),url);assert(component.isReady());auto object=component.create();assert(object);view.setContent(url,&component,object);view.show();QTest::qWait(150);
 auto item=view.rootObject()->findChild<QQuickItem*>("actualImage");assert(item&&item->property("status").toInt()==1);assert(item->width()>0&&item->height()>0);
 auto pixels=view.grabWindow();assert(!pixels.isNull());auto origin=item->mapToScene(QPointF(0,0));int x=qRound(origin.x()),y=qRound(origin.y());assert(pixels.pixelColor(x,y).alpha()==0);
 int painted=0;for(int yy=y;yy<y+item->height();++yy)for(int xx=x;xx<x+item->width();++xx)if(pixels.pixelColor(xx,yy).alpha()>200)++painted;assert(painted>10);
 item->setProperty("source",QUrl());QTest::qWait(100);assert(item->property("status").toInt()==0);pixels=view.grabWindow();assert(pixels.pixelColor(x+item->width()/2,y+item->height()/2).alpha()==0);
 if(view.rootObject()->metaObject()->indexOfMethod("updatePreviewUrl()")>=0){
  assert(QMetaObject::invokeMethod(view.rootObject(),"updatePreviewUrl"));QTest::qWait(100);assert(item->property("status").toInt()==1);
  QVariant message=QVariantMap{{"source","simplifiedUI.js"},{"method","updateAvatarThumbnailURL"},{"data",QVariantMap{{"avatarThumbnailURL","image://fixture/updated"}}}};
  assert(QMetaObject::invokeMethod(view.rootObject(),"fromScript",Q_ARG(QVariant,message)));QTest::qWait(100);assert(item->property("status").toInt()==1);pixels=view.grabWindow();assert(pixels.pixelColor(x+item->width()/2,y+item->height()/2)==QColor(Qt::cyan));
  message=QVariantMap{{"source","simplifiedUI.js"},{"method","updateAvatarThumbnailURL"},{"data",QVariantMap{{"avatarThumbnailURL","defaultAvatar.svg"}}}};
  assert(QMetaObject::invokeMethod(view.rootObject(),"fromScript",Q_ARG(QVariant,message)));QTest::qWait(100);assert(item->property("status").toInt()==1);assert(item->property("source").toUrl().fileName()=="defaultAvatar.svg");
 }
}
