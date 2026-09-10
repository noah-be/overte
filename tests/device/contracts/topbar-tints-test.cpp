// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQuickView>
#include <QQuickItem>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlPropertyMap>
#include <QFile>
#include <QTest>
#include <cassert>
int main(int argc,char**argv){
 QGuiApplication app(argc,argv);assert(argc==4);QQuickView view;view.setColor(Qt::transparent);QQmlPropertyMap audio,hmd;
 for(auto key:{"avatarGain","serverInjectorGain","localInjectorGain","systemInjectorGain"})audio.insert(key,0);hmd.insert("active",false);view.rootContext()->setContextProperty("AudioScriptingInterface",&audio);view.rootContext()->setContextProperty("HMD",&hmd);
 QFile file(argv[1]);assert(file.open(QIODevice::ReadOnly));QQmlComponent c(view.engine());auto base=QUrl::fromLocalFile(argv[2]);c.setData(file.readAll(),base);assert(c.isReady());auto root=c.create();assert(root);view.setContent(base,&c,root);view.show();QTest::qWait(150);
 auto pixels=view.grabWindow();int maxAlpha=0,count=0;QColor strongest;for(int y=0;y<pixels.height();++y)for(int x=0;x<pixels.width();++x){auto p=pixels.pixelColor(x,y);if(p.alpha()>maxAlpha){maxAlpha=p.alpha();strongest=p;}if(p.alpha()>150)++count;}assert(count>5&&maxAlpha>=170);
 if(QString(argv[3])=="outputDeviceButton"){assert(strongest.red()>250&&strongest.green()<3&&strongest.blue()<3);}else if(QString(argv[3])!="statusButton"&&QString(argv[3])!="statusIcon"){assert(strongest.red()>250&&strongest.green()>250&&strongest.blue()>250);}
 assert(root->setProperty("hovered",true));QTest::qWait(100);pixels=view.grabWindow();maxAlpha=0;for(int y=0;y<pixels.height();++y)for(int x=0;x<pixels.width();++x)maxAlpha=std::max(maxAlpha,pixels.pixelColor(x,y).alpha());assert(maxAlpha>240);
 if(QString(argv[3])=="statusIcon"){bool white=false;for(int y=0;y<pixels.height();++y)for(int x=0;x<pixels.width();++x){auto p=pixels.pixelColor(x,y);white=white||(p.alpha()>240&&p.red()>250&&p.green()>250&&p.blue()>250);}assert(white);}
 auto item=root->findChild<QQuickItem*>("actualSource");assert(item);if(QString(argv[3])=="statusButton"){
  for(auto pair:{std::pair<const char*,const char*>("busy","#ff001a"),{"available","#009036"},{"away","#ffed00"},{"","#7e8c81"}}){item->setProperty("currentStatus",pair.first);QTest::qWait(60);auto actual=view.grabWindow().pixelColor(32,32);auto expected=QColor(pair.second);assert(actual.red()==expected.red()&&actual.green()==expected.green()&&actual.blue()==expected.blue());}
 }else{item->setProperty("source",QUrl());QTest::qWait(100);pixels=view.grabWindow();for(int y=0;y<pixels.height();++y)for(int x=0;x<pixels.width();++x)assert(pixels.pixelColor(x,y).alpha()==0);}
}
