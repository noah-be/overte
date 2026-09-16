// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQuickView>
#include <QQuickItem>
#include <QQmlEngine>
#include <QQmlContext>
#include <QTemporaryDir>
#include <QTest>
#include <QElapsedTimer>
#include <QImage>
#include <cassert>
#include <functional>
#include <iostream>
static int shadowPixels(const QImage& image,QRect area) {
 int total=0;for(int y=area.top();y<=area.bottom();++y)for(int x=area.left();x<=area.right();++x){auto p=image.pixelColor(x,y);if(p.alpha()>0&&p.red()==0&&p.green()==0&&p.blue()==0)++total;}return total;
}
static int alphaSum(const QImage& image,QRect area) {
 int total=0;for(int y=area.top();y<=area.bottom();++y)for(int x=area.left();x<=area.right();++x)total+=image.pixelColor(x,y).alpha();return total;
}
int main(int argc,char**argv) {
 QGuiApplication app(argc,argv);assert(argc==3);QTemporaryDir files;assert(files.isValid());
 QImage red(32,32,QImage::Format_ARGB32);red.fill(Qt::red);assert(red.save(files.filePath("red.png")));
 QImage blue(32,32,QImage::Format_ARGB32);blue.fill(Qt::blue);assert(blue.save(files.filePath("blue.png")));
 QQuickView view;view.setColor(Qt::transparent);view.engine()->addImportPath(argv[2]);
 view.rootContext()->setContextProperty("fixtureRed",QUrl::fromLocalFile(files.filePath("red.png")));
 QObject::connect(view.engine(),&QQmlEngine::warnings,[](const QList<QQmlError>& errors){for(auto error:errors)std::cerr<<error.toString().toStdString()<<std::endl;});
 view.setSource(QUrl::fromLocalFile(argv[1]));QTest::qWait(50);assert(view.status()==QQuickView::Ready);view.show();
 auto root=view.rootObject();auto rectangle=root->findChild<QQuickItem*>("rectangle");auto glyph=root->findChild<QQuickItem*>("glyph");auto image=root->findChild<QQuickItem*>("image");assert(rectangle&&glyph&&image);
 int step=0;
 auto wait=[&](std::function<bool(const QImage&)> predicate){++step;QElapsedTimer timer;timer.start();for(int i=0;i<100;++i){QTest::qWait(20);auto pixels=view.grabWindow();if(!pixels.isNull()&&predicate(pixels)){std::cout<<"step "<<step<<" "<<timer.elapsed()<<"ms\n";return;}}std::cerr<<"failed pixel step "<<step<<std::endl;
 assert(false);};
 auto initial=[](const QImage& p){return p.pixelColor(44,44)==QColor(Qt::red)&&p.pixelColor(44,70).alpha()>0&&p.pixelColor(234,44)==QColor(Qt::red)&&p.pixelColor(234,70).alpha()>0&&shadowPixels(p,QRect(100,10,80,80))>0;};
 wait(initial);
 rectangle->setProperty("color",QColor(Qt::blue));wait([](const QImage&p){return p.pixelColor(44,44)==QColor(Qt::blue);});
 glyph->setProperty("text",QString());wait([](const QImage&p){return alphaSum(p,QRect(100,10,80,80))==0;});
 glyph->setProperty("text",QStringLiteral("W"));wait([](const QImage&p){return alphaSum(p,QRect(100,10,80,80))>0;});
 image->setProperty("source",QUrl::fromLocalFile(files.filePath("blue.png")));wait([](const QImage&p){return p.pixelColor(234,44)==QColor(Qt::blue)&&p.pixelColor(234,70).alpha()>0;});
 image->setProperty("source",QUrl());wait([](const QImage&p){return alphaSum(p,QRect(200,10,80,80))==0;});
 image->setProperty("source",QUrl::fromLocalFile(files.filePath("red.png")));wait([](const QImage&p){return p.pixelColor(234,44)==QColor(Qt::red)&&p.pixelColor(234,70).alpha()>0;});
 rectangle->setHeight(24);wait([](const QImage&p){return p.pixelColor(44,43)==QColor(Qt::blue)&&p.pixelColor(44,46).alpha()>0&&p.pixelColor(44,70).alpha()==0;});
 image->setVisible(false);wait([](const QImage&p){return alphaSum(p,QRect(200,10,80,80))==0;});image->setVisible(true);wait([](const QImage&p){return p.pixelColor(234,44)==QColor(Qt::red)&&p.pixelColor(234,70).alpha()>0;});
 view.hide();QTest::qWait(30);view.show();wait([](const QImage&p){return p.pixelColor(234,44)==QColor(Qt::red)&&p.pixelColor(234,70).alpha()>0;});
 assert(QMetaObject::invokeMethod(root,"activateGradient"));QTest::qWait(100);
 root->setProperty("gradientColor",QColor(Qt::transparent));wait([](const QImage&p){return alphaSum(p,QRect(10,10,80,80))==0;});
 root->setProperty("gradientColor",QColor(Qt::blue));wait([](const QImage&p){return p.pixelColor(44,30)==QColor(Qt::blue)&&p.pixelColor(44,46).alpha()>0;});
 root->setProperty("motionRunning",true);int activeFrames=0;int foregroundMismatches=0;auto motion=root->findChild<QQuickItem*>("motion");assert(motion);for(int i=0;i<25;++i){QTest::qWait(20);auto pixels=view.grabWindow();if(pixels.pixelColor(36,174).alpha()>0)++activeFrames;int expected=qRound(255.0*(motion->property("paintedPhase").toInt()%200)/200.0);if(qAbs(pixels.pixelColor(36,156).red()-expected)>1)++foregroundMismatches;}root->setProperty("motionRunning",false);assert(activeFrames>=15 && "continuously painted source must not starve capture");assert(foregroundMismatches==0 && "capture must not paint an older foreground over the live source");
 std::cout<<"live shadow frames "<<activeFrames<<"/25\n";
 std::cout<<"PASS actual ShadowRectangle/ShadowGlyph/ShadowImage and RoundImage source transitions\n";
}
