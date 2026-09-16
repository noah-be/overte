// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQuickView>
#include <QQuickItem>
#include <QPointer>
#include <QTest>
#include <QQmlEngine>
#include <cassert>

int main(int argc,char**argv){
 QGuiApplication app(argc,argv);assert(argc==4);qmlRegisterModule("Hifi",1,0);QQuickView view;view.setColor(Qt::transparent);view.setSource(QUrl::fromLocalFile(argv[1]));assert(view.status()==QQuickView::Ready);auto root=view.rootObject();
 auto update=[&](const QVariantMap& m){assert(QMetaObject::invokeMethod(root,"updatePropertiesFromScript",Q_ARG(QVariant,QVariant(m))));};
 update({{"width",64},{"height",64},{"imageURL",QUrl::fromLocalFile(argv[2]).toString()},{"color",QVariantMap{{"red",0},{"green",0},{"blue",255}}}});view.resize(64,64);view.show();QTest::qWait(200);
 QQuickItem* image=nullptr;for(auto i:root->findChildren<QQuickItem*>())if(i->inherits("QQuickAnimatedImage"))image=i;assert(image);image->setProperty("playing",false);assert(image->property("frameCount").toInt()==2);
 auto pixels=[&]{QTest::qWait(130);auto p=view.grabWindow();assert(!p.isNull());return p;};
 for(int frame:{0,1,0,1}){image->setProperty("currentFrame",frame);auto p=pixels();assert(p.pixelColor(frame?48:16,32)==QColor(Qt::blue));assert(p.pixelColor(frame?16:48,32).alpha()==0);}
 image->setProperty("playing",true);bool left=false,right=false;
 for(int i=0;i<12;++i){QTest::qWait(60);auto p=view.grabWindow();left=left||p.pixelColor(16,32)==QColor(Qt::blue);right=right||p.pixelColor(48,32)==QColor(Qt::blue);}assert(left&&right);image->setProperty("playing",false);image->setProperty("currentFrame",1);pixels();
 update({{"subImage",QVariantMap{{"x",16},{"y",0},{"width",16},{"height",32}}}});auto cropped=pixels();assert(cropped.pixelColor(16,32)==QColor(Qt::blue)&&cropped.pixelColor(48,32)==QColor(Qt::blue));
 // Explicit crop scales with the overlay after it has loaded.
 update({{"width",96},{"height",96}});view.resize(96,96);pixels();
 assert(qAbs(image->width()-192)<0.1 && qAbs(image->x()+96)<0.1 && qAbs(image->height()-96)<0.1);
 update({{"width",64},{"height",64}});view.resize(64,64);pixels();
 // Qt propagates parent opacity to each child: red alpha .5, blue alpha .25.
 // Source-over therefore gives alpha .625 and unpremultiplied RGB (.6,0,.4).
 update({{"alpha",0.5},{"color",QVariantMap{{"red",0},{"green",0},{"blue",255}}}});auto blend=pixels().pixelColor(32,32);assert(abs(blend.red()-153)<4&&blend.green()<3&&abs(blend.blue()-102)<4&&abs(blend.alpha()-159)<4);
 update({{"alpha",1.0},{"color",QVariantMap{{"red",0},{"green",0},{"blue",255}}},{"imageURL",QUrl::fromLocalFile(argv[3]).toString()}});auto replaced=pixels();assert(replaced.pixelColor(16,32)==QColor(Qt::blue)&&replaced.pixelColor(48,32)==QColor(Qt::blue));
 // Zero means the remaining source extent, and stays automatic across sources.
 update({{"subImage",QVariantMap{{"x",0},{"y",0},{"width",0},{"height",0}}}});pixels();
 update({{"imageURL",QUrl::fromLocalFile(argv[2]).toString()}});pixels();
 assert(qAbs(image->width()-64)<0.1 && qAbs(image->height()-64)<0.1);
 update({{"imageURL",QUrl::fromLocalFile(argv[3]).toString()}});pixels();
 assert(qAbs(image->width()-64)<0.1 && qAbs(image->height()-64)<0.1);
 assert(image->property("xSize").toDouble()==0 && image->property("ySize").toDouble()==0);
 update({{"visible",false}});assert(pixels().pixelColor(16,32).alpha()==0);update({{"visible",true}});assert(pixels().pixelColor(16,32)==QColor(Qt::blue));
 update({{"imageURL",""}});auto empty=pixels();assert(empty.pixelColor(16,32).alpha()==0&&empty.pixelColor(48,32).alpha()==0);
 update({{"imageURL",QUrl::fromLocalFile(argv[2]).toString()}});QPointer<QQuickItem> observed=root;view.setSource(QUrl());QTest::qWait(150);assert(observed.isNull());
}
