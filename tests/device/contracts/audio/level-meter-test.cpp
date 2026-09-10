// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQuickView>
#include <QQuickItem>
#include <QQmlContext>
#include <QQmlPropertyMap>
#include <QTest>
#include <QImage>
#include <cassert>
#include <limits>
int main(int argc,char**argv){
 QGuiApplication app(argc,argv);assert(argc==3);
 QQmlPropertyMap audio;audio.insert("muted",false);
 QQuickView view;view.rootContext()->setContextProperty("AudioScriptingInterface",&audio);
 view.setSource(QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])+"/InputPeak.qml"));
 assert(view.status()==QQuickView::Ready);view.show();
 auto image=[&]{QTest::qWait(100);auto img=view.grabWindow();assert(!img.isNull());return img;};
 auto item=view.rootObject();assert(item);
 item->setProperty("peak",0.5);auto half=image();
 assert(half.pixelColor(10,4).green()>half.pixelColor(10,4).red());
 assert(half.pixelColor(10,4).green()>half.pixelColor(10,4).blue());
 assert(half.pixelColor(60,4)==QColor("#575757"));
 item->setProperty("peak",0.0);auto zero=image();assert(zero.pixelColor(10,4)==QColor("#575757"));
 item->setProperty("peak",1.0);auto full=image();assert(full.pixelColor(60,4)!=QColor("#575757"));
 item->setProperty("peak",std::numeric_limits<double>::quiet_NaN());auto invalid=image();assert(invalid.pixelColor(10,4)==QColor("#575757"));
 audio.insert("muted",true);
 if(item->metaObject()->indexOfProperty("showMuted")>=0)item->setProperty("showMuted",true);
 auto muted=image();assert(muted!=full);
 view.setSource(QUrl::fromLocalFile(QString::fromLocal8Bit(argv[2])+"/LevelMeter.qml"));assert(view.status()==QQuickView::Ready);
 item=view.rootObject();item->setWidth(8);item->setHeight(32);view.resize(8,32);item->setProperty("vertical",true);item->setProperty("level",0.5);
 auto vertical=image();assert(vertical.pixelColor(4,4)==QColor("#575757"));assert(vertical.pixelColor(4,26)!=QColor("#575757"));
}
