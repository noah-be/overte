// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQuickView>
#include <QQuickItem>
#include <QQmlProperty>
#include <QQmlEngine>
#include <QQuickImageProvider>
#include <QTest>
#include <QImage>
#include <cassert>
#include <iostream>
struct CountedImages : QQuickImageProvider {
 int requests {0};
 CountedImages():QQuickImageProvider(QQuickImageProvider::Image){}
 QImage requestImage(const QString& id,QSize* size,const QSize&) override {
  ++requests;
  if(id=="missing"){*size=QSize();return {};}
  QImage image(24,16,QImage::Format_ARGB32_Premultiplied);image.fill(Qt::cyan);*size=image.size();return image;
 }
};
int main(int argc,char**argv){
 QGuiApplication app(argc,argv);assert(argc==4);
 QQuickView rounded,reference;rounded.setColor(Qt::transparent);reference.setColor(Qt::transparent);
 rounded.setSource(QUrl::fromLocalFile(argv[1]));reference.setSource(QUrl::fromLocalFile(argv[2]));
 assert(rounded.status()==QQuickView::Ready&&reference.status()==QQuickView::Ready);
 auto r=rounded.rootObject();auto ref=reference.rootObject();r->setWidth(64);r->setHeight(64);rounded.resize(64,64);reference.resize(64,64);
 assert(QQmlProperty(r,"border.width").write(0));r->setProperty("radius",0);
 auto source=QUrl::fromLocalFile(argv[3]);r->setProperty("source",source);ref->setProperty("source",source);rounded.show();reference.show();
 for(int mode=0;mode<=6;++mode){
  r->setProperty("fillMode",mode);ref->setProperty("fillMode",mode);QTest::qWait(100);
  assert(r->property("status").toInt()==1);assert(r->property("progress").toReal()==1);
  auto actual=rounded.grabWindow(),expected=reference.grabWindow();assert(!actual.isNull()&&!expected.isNull());
  // Compare interior color regions; Qt Image and Canvas filtering at source
  // color discontinuities differs and is not asserted pixel-identical.
  for(int y:{6,18,26,42,54})for(int x:{6,18,26,42,54}){auto a=actual.pixelColor(x,y),b=expected.pixelColor(x,y);if(abs(a.red()-b.red())>4||abs(a.green()-b.green())>4||abs(a.blue()-b.blue())>4||abs(a.alpha()-b.alpha())>4){std::cerr<<"mode="<<mode<<" x="<<x<<" y="<<y<<" actual="<<a.name(QColor::HexArgb).toStdString()<<" expected="<<b.name(QColor::HexArgb).toStdString()<<std::endl;return 2;}}
 }
 r->setProperty("fillMode",0);r->setProperty("radius",24);QTest::qWait(100);auto image=rounded.grabWindow();assert(image.pixelColor(0,0).alpha()==0);assert(image.pixelColor(32,32).alpha()>240);
 assert(QQmlProperty(r,"border.width").write(3));assert(QQmlProperty(r,"border.color").write(QColor("magenta")));QTest::qWait(100);image=rounded.grabWindow();assert(image.pixelColor(32,1).red()>240&&image.pixelColor(32,1).blue()>240);
 auto provider=new CountedImages;rounded.engine()->addImageProvider("counted",provider);
 r->setProperty("source",QUrl("image://counted/one"));QTest::qWait(100);
 assert(provider->requests==1&&r->property("status").toInt()==1);
 r->setProperty("radius",20);QTest::qWait(100);image=rounded.grabWindow();assert(image.pixelColor(32,32)==QColor(Qt::cyan));assert(provider->requests==1);
 r->setProperty("source",QUrl("image://counted/missing"));QTest::qWait(100);assert(provider->requests==2&&r->property("status").toInt()==3);image=rounded.grabWindow();assert(image.pixelColor(32,32).alpha()==0);
 r->setProperty("source",QUrl());QTest::qWait(100);assert(r->property("status").toInt()==0);image=rounded.grabWindow();assert(image.pixelColor(32,32).alpha()==0);
}
