// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Genuine compiled QML NativeInput + QtWebEngine. Authored native-filter scaffold,
// not installed Interface or native Controller/Emote proof.
#include <QApplication>
#include <QMainWindow>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QSet>
#include <QPointer>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQuickWindow>
#include <QQuickItem>
#include <QQuickRenderControl>
#include <QOpenGLContext>
#include <QOffscreenSurface>
#include <QOpenGLFramebufferObject>
#include <QOpenGLFunctions>
#include <QTimer>
#include <QThread>
#include <QLibraryInfo>
#include <QDir>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <cstdio>
namespace QtWebEngine { void initialize(); }
class Application : public QApplication {
 Q_OBJECT
public:
 using QApplication::QApplication;
 int presses{0},releases{0};
 bool event(QEvent* event) override {
  if(event->type()==QEvent::KeyPress&&static_cast<QKeyEvent*>(event)->key()==Qt::Key_X){++presses;return true;}
  if(event->type()==QEvent::KeyRelease&&static_cast<QKeyEvent*>(event)->key()==Qt::Key_X){++releases;return true;}
  return QApplication::event(event);
 }
};
class MainWindow : public QMainWindow {Q_OBJECT public:using QMainWindow::QMainWindow;};
class GLCanvas : public QWidget {
 Q_OBJECT
public:
 using QWidget::QWidget;
 int forwardedPresses{0},forwardedReleases{0},applicationAcceptedPresses{0},applicationAcceptedReleases{0};
 bool event(QEvent* event) override {
  // Exact native f91 GLWidget keyboard branch; no direct fallback in NativeInput.
  if(event->type()==QEvent::KeyPress||event->type()==QEvent::KeyRelease) {
   const bool observed=static_cast<QKeyEvent*>(event)->key()==Qt::Key_X;
   if(observed){if(event->type()==QEvent::KeyPress)++forwardedPresses;else ++forwardedReleases;}
   const bool accepted=QCoreApplication::sendEvent(QCoreApplication::instance(),event);
   if(observed&&accepted){if(event->type()==QEvent::KeyPress)++applicationAcceptedPresses;else ++applicationAcceptedReleases;}
   if(accepted)return true;
  }
  return QWidget::event(event);
 }
};
class OwnedRenderControl : public QQuickRenderControl {
public:
 QWindow* proxy{nullptr};
 QWindow* renderWindow(QPoint* offset) override {if(offset)*offset=QPoint();return proxy;}
};
class NativeUiFilter : public QObject {
public:
 QQuickWindow* window;QSet<int> consumed;int presses{0},releases{0};int windowReturnedPresses{0},windowReturnedReleases{0},windowAcceptedPresses{0},windowAcceptedReleases{0},filteredPresses{0},filteredReleases{0},consumedReleaseCount{0};QPointer<QObject> destroyNext;
 explicit NativeUiFilter(QQuickWindow* value):window(value){}
 bool eventFilter(QObject*,QEvent* event) override {
  if(event->type()!=QEvent::KeyPress&&event->type()!=QEvent::KeyRelease)return false;
  auto* key=static_cast<QKeyEvent*>(event);
  if(key->key()==Qt::Key_X){if(event->type()==QEvent::KeyPress)++presses;else ++releases;}
  if(event->type()==QEvent::KeyPress&&destroyNext){auto* doomed=destroyNext.data();destroyNext=nullptr;delete doomed;}
  // Native OffscreenSurface first offers the original event to private QML.
  event->ignore();
  const bool delivered=QCoreApplication::sendEvent(window,event);
  const bool accepted=delivered&&event->isAccepted();
  if(key->key()==Qt::Key_X){
   if(delivered){if(event->type()==QEvent::KeyPress)++windowReturnedPresses;else ++windowReturnedReleases;}
   if(accepted){if(event->type()==QEvent::KeyPress)++windowAcceptedPresses;else ++windowAcceptedReleases;}
  }
  // Native OffscreenUi remembers a consumed press and suppresses its release.
  if(accepted&&event->type()==QEvent::KeyPress)consumed.insert(key->key());
  if(event->type()==QEvent::KeyRelease&&consumed.remove(key->key())){
   if(key->key()==Qt::Key_X){++consumedReleaseCount;++filteredReleases;}return true;
  }
  if(accepted&&key->key()==Qt::Key_X){if(event->type()==QEvent::KeyPress)++filteredPresses;else ++filteredReleases;}
  return accepted;
 }
};
class ParentKeyObservation : public QObject {
public:
 int presses{0},releases{0};
 bool eventFilter(QObject*,QEvent* event) override {
  if((event->type()==QEvent::KeyPress||event->type()==QEvent::KeyRelease)&&static_cast<QKeyEvent*>(event)->key()==Qt::Key_X){
   if(event->type()==QEvent::KeyPress)++presses;else ++releases;
  }
  return false; // passive: never accepts, edits or forwards an event
 }
};
class FixtureHost : public QObject {
 Q_OBJECT
public:
 Application* app;QQuickWindow* window;OwnedRenderControl* control;NativeUiFilter* filter;GLCanvas* canvas;ParentKeyObservation parentKeys;QQuickItem* root{nullptr};QJsonArray refusals;int renderedFrames{0};bool refusalComplete{false};
 FixtureHost(Application* a,QQuickWindow* w,OwnedRenderControl* c,NativeUiFilter* f,GLCanvas* g):app(a),window(w),control(c),filter(f),canvas(g){}
 bool invoke(QObject* plugin,QObject* surface,const QString& key="x",int modifiers=0){bool result=false;return QMetaObject::invokeMethod(plugin,"clickApplicationKey",Q_RETURN_ARG(bool,result),Q_ARG(QObject*,surface),Q_ARG(QString,key),Q_ARG(int,modifiers))&&result;}
 void row(const char* kind,bool passed){refusals.append(QJsonObject{{"kind",kind},{"passed",passed}});}
 void pointer(const QPointF& point){
  QMouseEvent press(QEvent::MouseButtonPress,point,point,Qt::LeftButton,Qt::LeftButton,Qt::NoModifier);
  QCoreApplication::sendEvent(window,&press);
  QMouseEvent release(QEvent::MouseButtonRelease,point,point,Qt::LeftButton,Qt::NoButton,Qt::NoModifier);
  QCoreApplication::sendEvent(window,&release);
 }
 Q_INVOKABLE QVariantMap statistics()const{return {{"filterPresses",filter->presses},{"filterReleases",filter->releases},{"applicationPresses",app->presses},{"applicationReleases",app->releases},{"consumedKeys",filter->consumed.size()},{"windowReturnedPresses",filter->windowReturnedPresses},{"windowReturnedReleases",filter->windowReturnedReleases},{"windowAcceptedPresses",filter->windowAcceptedPresses},{"windowAcceptedReleases",filter->windowAcceptedReleases},{"filteredPresses",filter->filteredPresses},{"filteredReleases",filter->filteredReleases},{"consumedReleaseCount",filter->consumedReleaseCount},{"parentKeyPresses",parentKeys.presses},{"parentKeyReleases",parentKeys.releases},{"canvasForwardedPresses",canvas->forwardedPresses},{"canvasForwardedReleases",canvas->forwardedReleases},{"canvasApplicationAcceptedPresses",canvas->applicationAcceptedPresses},{"canvasApplicationAcceptedReleases",canvas->applicationAcceptedReleases}};}
 Q_INVOKABLE bool attachParentObservation(QObject* object){
  auto* item=qobject_cast<QQuickItem*>(object);
  if(!item||item->window()!=window||item->thread()!=QThread::currentThread())return false;
  // Authored helper passes the exact immediate WebEngine parent once on setup.
  item->installEventFilter(&parentKeys);return true;
 }
 Q_INVOKABLE bool focusBelongsTo(QObject* object)const{
  auto* surface=qobject_cast<QQuickItem*>(object);auto* focus=window->activeFocusItem();
  for(int depth=0;focus&&depth<24;++depth,focus=focus->parentItem())if(focus==surface)return true;
  return false;
 }
 Q_INVOKABLE void finishRefusals(QObject* plugin,QObject* object,QObject* foreignObject){
  auto* surface=qobject_cast<QQuickItem*>(object);auto* foreign=qobject_cast<QQuickItem*>(foreignObject);
  if(!surface||!foreign||!plugin||!focusBelongsTo(surface)){row("refusal-setup",false);refusalComplete=true;return;}
  const auto before=statistics();
  row("invalid-key",!invoke(plugin,surface,"\n"));
  row("invalid-modifier",!invoke(plugin,surface,"x",Qt::KeypadModifier));
  row("foreign-surface",!invoke(plugin,foreign));
  auto* proxy=control->proxy;control->proxy=nullptr;row("wrong-proxy",!invoke(plugin,surface));control->proxy=proxy;
  surface->setVisible(false);row("hidden-surface",!invoke(plugin,surface));surface->setVisible(true);
  pointer(foreign->mapToScene(QPointF(foreign->width()-4,foreign->height()/2)));
  row("foreign-focus",window->activeFocusItem()==foreign&&!invoke(plugin,surface));
  pointer(QPointF(366,41));
  row("native-pointer-refocus",focusBelongsTo(surface));
  const auto after=statistics();row("refusals-no-delivery",before==after);
  if(focusBelongsTo(surface)){
   QQuickItem stale;stale.setWidth(100);stale.setHeight(100);row("stale-detached-surface",!invoke(plugin,&stale));
   const int presses=filter->presses,releases=filter->releases,globalPress=app->presses,globalRelease=app->releases;
   QPointer<QObject> lifetime(plugin);filter->destroyNext=plugin;const bool accepted=invoke(plugin,surface);
   row("reentrant-receiver-destruction",!accepted&&!lifetime&&filter->presses==presses+1&&filter->releases==releases+1&&app->presses==globalPress+1&&app->releases==globalRelease+1&&filter->consumed.isEmpty());
  }else row("reentrant-receiver-destruction",false);
  refusalComplete=true;
 }
};
int main(int argc,char** argv){
 QCoreApplication::setAttribute(Qt::AA_ShareOpenGLContexts);QtWebEngine::initialize();Application app(argc,argv);
 if(argc!=5)return 2;
 const auto package=QDir::cleanPath(QString::fromLocal8Bit(argv[4]));
 if(QDir::cleanPath(QLibraryInfo::location(QLibraryInfo::DataPath))!=package||QDir::cleanPath(QLibraryInfo::location(QLibraryInfo::TranslationsPath))!=package+"/translations"||QDir::cleanPath(QLibraryInfo::location(QLibraryInfo::LibraryExecutablesPath))!=package+"/libexec")return 6;
 MainWindow main;auto* canvas=new GLCanvas;main.setCentralWidget(canvas);main.resize(600,600);main.show();main.activateWindow();
 OwnedRenderControl control;control.proxy=main.windowHandle();QQuickWindow window(&control);window.setGeometry(0,0,600,600);
 NativeUiFilter filter(&window);canvas->installEventFilter(&filter);FixtureHost host(&app,&window,&control,&filter,canvas);
 QQmlEngine engine;engine.addImportPath(QString::fromLocal8Bit(argv[1]));engine.rootContext()->setContextProperty("fixtureHost",&host);engine.rootContext()->setContextProperty("fixtureURL",QUrl::fromLocalFile(QString::fromLocal8Bit(argv[3])));engine.rootContext()->setContextProperty("fixtureStorage",qEnvironmentVariable("XDG_DATA_HOME")+"/authored-keys");
 QQmlComponent component(&engine,QUrl::fromLocalFile(QString::fromLocal8Bit(argv[2])));auto* root=qobject_cast<QQuickItem*>(component.create());
 if(!root){std::puts("{\"completed\":false,\"failureCategory\":\"qml-component-refused\"}");return 3;}
 host.root=root;root->setParent(window.contentItem());root->setParentItem(window.contentItem());window.contentItem()->setWidth(600);window.contentItem()->setHeight(600);
 auto* webParent=root->findChild<QQuickItem*>(QStringLiteral("actualKeyWebParent"));
 if(!host.attachParentObservation(webParent)){std::puts("{\"completed\":false,\"failureCategory\":\"parent-observation-refused\"}");delete root;return 10;}
 QOpenGLContext context;context.setFormat(QSurfaceFormat::defaultFormat());context.setShareContext(QOpenGLContext::globalShareContext());
 if(!context.create())return 7;
 QOffscreenSurface output;output.setFormat(context.format());output.create();
 if(!context.makeCurrent(&output))return 8;
 control.initialize(&context);QOpenGLFramebufferObjectFormat format;format.setAttachment(QOpenGLFramebufferObject::CombinedDepthStencil);QOpenGLFramebufferObject framebuffer(QSize(600,600),format);
 if(!framebuffer.isValid())return 9;
 window.setRenderTarget(framebuffer.handle(),QSize(600,600));
 QTimer render;QObject::connect(&render,&QTimer::timeout,&app,[&]{
  if(!context.makeCurrent(&output)){app.exit(8);return;}
  control.polishItems();control.sync();control.render();context.functions()->glFlush();++host.renderedFrames;
  if(!root->property("completed").toBool())return;
  const auto source=QJsonDocument::fromJson(root->property("evidence").toString().toUtf8()).object();auto cases=source.value("cases").toArray();
  bool passed=root->property("passed").toBool()&&host.refusalComplete;for(const auto value:host.refusals)passed=passed&&value.toObject().value("passed").toBool();
  const QJsonObject report{{"completed",true},{"passed",passed},{"nativeInterfaceProof",false},{"actualCompiledNativeInput",true},{"actualQtWebEngine",true},{"originalFilterScaffold",true},{"renderedFrames",host.renderedFrames},{"cases",cases},{"refusals",host.refusals}};
  std::puts(QJsonDocument(report).toJson(QJsonDocument::Compact).constData());app.exit(passed?0:1);
 });render.start(20);
 QTimer::singleShot(90000,&app,[&]{std::puts("{\"completed\":false,\"failureCategory\":\"owned-key-fixture-deadline\"}");app.exit(5);});
 const int result=app.exec();render.stop();context.makeCurrent(&output);control.invalidate();delete root;return result;
}
#include "key-fixture.moc"
