// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQuickView>
#include <QQuickItem>
#include <QTest>
#include <QImage>
#include <cassert>
int main(int argc,char**argv){
 QGuiApplication app(argc,argv);assert(argc==3);QQuickView view;view.setColor(Qt::transparent);
 view.setSource(QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])));assert(view.status()==QQuickView::Ready);view.show();
 auto item=view.rootObject()->findChild<QQuickItem*>("gradientItem");assert(item);
 bool hidden=QString::fromLocal8Bit(argv[2])=="hidden";assert(item->isVisible()!=hidden);
 // Exercise drawing separately from the original intentionally hidden Tablet state.
 if(hidden)item->setVisible(true);
 QTest::qWait(100);auto image=view.grabWindow();assert(!image.isNull());
 auto top=image.pixelColor(20,4),bottom=image.pixelColor(20,7);
 assert(top.alpha()>0);assert(top.red()<bottom.red() || top.alpha()>bottom.alpha());
 item->setVisible(false);QTest::qWait(100);image=view.grabWindow();assert(image.pixelColor(20,4).alpha()==0);
}
