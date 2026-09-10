// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQuickView>
#include <QQuickItem>
#include <QQmlContext>
#include <QQmlEngine>
#include <QTest>
#include <QJSValue>
#include <cassert>
class Context:public QObject {
 Q_OBJECT
 Q_PROPERTY(bool ignoreRadiusEnabled READ enabled WRITE setEnabled NOTIFY ignoreRadiusEnabledChanged)
 Q_PROPERTY(int ButtonClick READ click CONSTANT)
 Q_PROPERTY(int ButtonHover READ hover CONSTANT)
public:
 bool state=false;int toggles=0,sounds=0;
 bool enabled()const{return state;}int click()const{return 1;}int hover()const{return 2;}
 void setEnabled(bool v){if(v!=state){state=v;emit ignoreRadiusEnabledChanged();}}
 Q_INVOKABLE void toggleIgnoreRadius(){++toggles;setEnabled(!state);}
 Q_INVOKABLE void playSound(int){++sounds;}
signals:void ignoreRadiusEnabledChanged();
};
#include "image-tint-callers-test.moc"
int main(int argc,char**argv){
 qInstallMessageHandler([](QtMsgType,const QMessageLogContext&,const QString& s){fprintf(stderr,"QT: %s\n",qPrintable(s));}); QGuiApplication app(argc,argv);qmlRegisterModule("Hifi",1,0);qmlRegisterModule("TabletScriptingInterface",1,0);Context context;QQuickView view;view.setColor(Qt::transparent);for(auto name:{"AvatarInputs","Users","Tablet","TabletEnums"})view.rootContext()->setContextProperty(name,&context);view.setSource(QUrl::fromLocalFile(argv[1]));QTest::qWait(80);if(view.status()!=QQuickView::Ready){for(auto e:view.errors())fprintf(stderr,"%s\n",qPrintable(e.toString()));}assert(view.status()==QQuickView::Ready);auto root=view.rootObject();bool bubble=QString(argv[2])=="bubble";view.resize(bubble?42:64,bubble?42:40);view.show();
 auto pixels=[&]{QTest::qWait(120);auto p=view.grabWindow();assert(!p.isNull());return p;};
 auto count=[&](QImage p,bool white){int n=0;for(int y=0;y<p.height();++y)for(int x=0;x<p.width();++x){auto c=p.pixelColor(x,y);if(white?(c.red()>245&&c.green()>245&&c.blue()>245&&c.alpha()>245):(c.green()>245&&c.red()<10&&c.blue()<10&&c.alpha()>245))++n;}return n;};
 if(bubble){
  pixels();context.setEnabled(true);assert(count(pixels(),true)>30);assert(root->opacity()==1);
  QQuickItem* tint=nullptr;for(auto i:root->findChildren<QQuickItem*>())if(i->property("captured").isValid())tint=i;assert(tint);tint->setProperty("color",QColor(Qt::green));assert(count(pixels(),false)>30);tint->setProperty("color",QColor(Qt::white));assert(count(pixels(),true)>30);
  QTest::mouseClick(&view,Qt::LeftButton,Qt::NoModifier,QPoint(20,20));pixels();assert(context.toggles==1&&!context.state&&context.sounds>0);
  context.setEnabled(true);assert(count(pixels(),true)>30);root->setVisible(false);assert(count(pixels(),true)==0);root->setVisible(true);assert(count(pixels(),true)>30);
 }else{
  auto green=[&](const char* stage){int n=count(pixels(),false);fprintf(stderr,"%s green=%d\n",stage,n);return n;};
  assert(green("initial")>20);
  root->setProperty("standaloneOptimized",false);assert(green("disabled")==0);
  root->setProperty("standaloneOptimized",true);assert(green("enabled")>20);
  root->setProperty("isConcurrency",false);assert(green("not concurrency")==0);
  root->setProperty("isConcurrency",true);assert(green("concurrency")>20);
  view.hide();pixels();view.show();assert(green("window shown")>20);
 }
}
