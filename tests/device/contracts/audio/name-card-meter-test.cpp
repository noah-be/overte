// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQuickView>
#include <QQuickItem>
#include <QTest>
#include <limits>
#include <cassert>
int main(int argc,char**argv){
 QGuiApplication app(argc,argv);QQuickView view;view.setColor(Qt::transparent);view.setSource(QUrl::fromLocalFile(argv[1]));QTest::qWait(80);if(view.status()!=QQuickView::Ready) {for(const auto& e:view.errors()) fprintf(stderr,"%s\n",qPrintable(e.toString()));}assert(view.status()==QQuickView::Ready);view.resize(640,32);view.show();auto root=view.rootObject();auto meter=root->findChild<QQuickItem*>("meter");assert(meter);
 auto pixels=[&]{QTest::qWait(65);auto p=view.grabWindow();assert(!p.isNull());return p;};
 auto green=[](QColor c){return c.green()>c.red()+70&&c.green()>c.blue();};
 auto red=[](QColor c){return qAbs(c.red()-234)<3&&qAbs(c.green()-76)<3&&qAbs(c.blue()-95)<3;};
 auto p=pixels();assert(green(p.pixelColor(160,20)));assert(p.pixelColor(500,20)==QColor("#c5c5c5"));
 root->setProperty("audioLevel",1);p=pixels();assert(green(p.pixelColor(560,20)));assert(red(p.pixelColor(600,20)));
 root->setProperty("gain",-20);p=pixels();assert(qAbs(meter->width()-320)<0.1);assert(green(p.pixelColor(280,20)));assert(red(p.pixelColor(305,20)));assert(p.pixelColor(400,20).alpha()==0);
 for(double level:{0.0,-1.0,std::numeric_limits<double>::quiet_NaN()}){root->setProperty("audioLevel",level);p=pixels();assert(p.pixelColor(160,20)==QColor("#c5c5c5"));}
 root->setProperty("audioLevel",2);p=pixels();assert(red(p.pixelColor(305,20)));assert(p.pixelColor(400,20).alpha()==0);
 root->setProperty("selected",false);assert(pixels().pixelColor(160,20).alpha()==0);root->setProperty("selected",true);assert(red(pixels().pixelColor(305,20)));
 root->setProperty("isMyCard",true);assert(pixels().pixelColor(160,20).alpha()==0);
}
