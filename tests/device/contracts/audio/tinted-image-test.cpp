// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQuickView>
#include <QQuickItem>
#include <QTest>
#include <QImage>
#include <cassert>
int main(int argc,char**argv){
 QGuiApplication app(argc,argv);assert(argc==3);QQuickView view;
 view.setColor(Qt::transparent);
 view.setSource(QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])));assert(view.status()==QQuickView::Ready);
 auto item=view.rootObject();item->setWidth(40);item->setHeight(40);view.resize(40,40);view.show();
 auto image=[&]{QTest::qWait(200);auto img=view.grabWindow();assert(!img.isNull());return img;};
 auto check=[&](const QImage& img,const QColor& color){int opaque=0,transparent=0;for(int y=0;y<img.height();++y)for(int x=0;x<img.width();++x){auto p=img.pixelColor(x,y);if(p.alpha()>240){++opaque;assert(abs(p.red()-color.red())<3&&abs(p.green()-color.green())<3&&abs(p.blue()-color.blue())<3);}if(p.alpha()==0)++transparent;}assert(opaque>10&&transparent>10);};
 item->setProperty("source",QUrl::fromLocalFile(QString::fromLocal8Bit(argv[2])));
 item->setProperty("color",QColor("#E2334D"));check(image(),QColor("#E2334D"));
 item->setProperty("color",QColor("#00BDFF"));check(image(),QColor("#00BDFF"));
 item->setProperty("source",QUrl());auto empty=image();for(int y=0;y<empty.height();++y)for(int x=0;x<empty.width();++x)assert(empty.pixelColor(x,y).alpha()==0);
}
