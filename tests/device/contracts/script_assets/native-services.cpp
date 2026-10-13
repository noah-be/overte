// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
// Engine/network/headset boundaries only. Tree models and FileDialogHelper are production Qt.
#include <QApplication>
#include <QFileDialog>
#include <QMenu>
#include <QLineEdit>
#include <QFile>
#include <QTemporaryDir>
#include <QStandardItemModel>
#include <QSortFilterProxyModel>
#include <QQmlEngine>
#include <QQmlContext>
#include <QQuickWindow>
#include <QQuickItem>
#include <QKeyEvent>
#include <QtQuickTest/quicktest.h>
#include <QtTest/QTest>
#include <QUuid>
#include "FileDialogHelper.h"

class ScriptApi : public QObject {
    Q_OBJECT
    Q_PROPERTY(QAbstractItemModel* scriptsModelFilter READ model CONSTANT)
    Q_PROPERTY(QString defaultScriptsPath READ defaults CONSTANT)
public:
    QStandardItemModel tree; QSortFilterProxyModel proxy; QVariantList calls;
    ScriptApi() { auto* folder = new QStandardItem("examples"); auto* script = new QStandardItem("ordinary.js"); script->setData("https://example.invalid/ordinary.js", 256); folder->appendRow(script); tree.appendRow(folder); proxy.setSourceModel(&tree); }
    QAbstractItemModel* model() { return &proxy; }
    QString defaults() const { return "https://example.invalid/defaults"; }
    Q_INVOKABLE QVariantList getRunning() { return { QVariantMap{{"url","https://example.invalid/ordinary.js"},{"path","https://example.invalid/ordinary.js"}}, QVariantMap{{"url","https://example.invalid/defaultScripts.js"},{"path","https://example.invalid/defaultScripts.js"}} }; }
    Q_INVOKABLE void loadOneScript(QString url) { calls.append(QVariantMap{{"kind","load"},{"url",url}}); }
    Q_INVOKABLE bool stopScript(QString url, bool restart = false) { calls.append(QVariantMap{{"kind","stop"},{"url",url},{"restart",restart}}); return true; }
    Q_INVOKABLE void reloadAllScripts() { calls.append(QVariantMap{{"kind","reloadAll"}}); }
signals: void scriptCountChanged(); void scriptLoadError(QString url, QString error);
};
class AssetModel : public QStandardItemModel {
    Q_OBJECT
    Q_PROPERTY(bool autoRefreshEnabled MEMBER automatic)
public:
    bool automatic { false }; int refreshes { 0 };
    Q_INVOKABLE void refresh() { ++refreshes; emit updated(); }
signals: void updated(); void errorGettingMappings(QString message);
};
class AssetsApi : public QObject {
    Q_OBJECT
    Q_PROPERTY(QAbstractItemModel* proxyModel READ model CONSTANT)
    Q_PROPERTY(QObject* mappingModel READ mapping CONSTANT)
public:
    AssetModel tree; QSortFilterProxyModel proxy; QVariantList calls; QString error;
    AssetsApi() { proxy.setSourceModel(&tree); populate(); }
    void populate() {
        tree.clear();
        auto* folder = new QStandardItem("models"); folder->setData("/models/",256);folder->setData(true,257);folder->setData("--",261);
        for (const auto& name : {"scene.fbx", "picture.png"}) { auto* item = new QStandardItem(name);item->setData(QString("/models/")+name,256); item->setData(false,257);item->setData(QString("atp:/models/")+name,259);item->setData("Baked",261);item->setData("",262);folder->appendRow(item); }
        tree.appendRow(folder);
    }
    QAbstractItemModel* model() { return &proxy; } QObject* mapping() { return &tree; }
    Q_INVOKABLE bool isKnownMapping(QString path) { return path == "/exists.fbx"; }
    Q_INVOKABLE bool isKnownFolder(QString path) { return path == "/models/"; }
    void done(QJSValue callback) { callback.call({error}); }
    Q_INVOKABLE void deleteMappings(QStringList paths,QJSValue callback) { calls.append(QVariantMap{{"kind","delete"},{"paths",paths}});done(callback); }
    Q_INVOKABLE void renameMapping(QString oldPath,QString newPath,QJSValue callback) { calls.append(QVariantMap{{"kind","rename"},{"old",oldPath},{"new",newPath}});done(callback); }
    Q_INVOKABLE void setMapping(QString path,QString hash,QJSValue callback) { calls.append(QVariantMap{{"kind","mapping"},{"path",path},{"hash",hash}});done(callback); }
    Q_INVOKABLE void setBakingEnabled(QStringList paths,bool enabled,QJSValue callback) { calls.append(QVariantMap{{"kind","baking"},{"paths",paths},{"enabled",enabled}});done(callback); }
    Q_INVOKABLE void uploadFile(QString path,QString mapping,QJSValue started,QJSValue callback,bool dropping=false) { calls.append(QVariantMap{{"kind","upload"},{"path",path},{"mapping",mapping},{"dropping",dropping}});started.call();done(callback); }
};
// Explicit vector/property/session boundaries. The declaration and entire
// production addImageEntity body are compiled below, without reimplementing it.
namespace glm { struct vec3 { float x {0}, y {0}, z {0}; }; }
Q_DECLARE_METATYPE(glm::vec3)
namespace EntityTypes { enum Type { Image }; }
struct EntityItemProperties {
    QVariantMap values;
    void setType(EntityTypes::Type) { values["kind"] = "image"; }
    void setName(QString value) { values["name"] = value; }
    void setImageURL(QString value) { values["url"] = value; }
    void setKeepAspectRatio(bool value) { values["keepAspectRatio"] = value; }
    void setDynamic(bool value) { values["dynamic"] = value; }
    void setCollisionless(bool value) { values["collisionless"] = value; }
    void setUserData(QString value) { values["userData"] = value; }
    void setPosition(glm::vec3 value) { values["position"] = QVariantMap{{"x",value.x},{"y",value.y},{"z",value.z}}; }
    void setLastEditedBy(QUuid value) { values["lastEditedBy"] = value; }
};
struct NodeList : QObject {
    Q_OBJECT
public:
    bool getThisNodeCanWriteAssets() { return false; }
    QUuid getSessionUUID() { return QUuid("11111111-2222-3333-4444-555555555555"); }
    void revokeWrites() { emit canWriteAssetsChanged(false); }
    signals: void canWriteAssetsChanged(bool);
};
struct DependencyManager { template<class T> static T* get() { static T service; return &service; } };
#include "image-api-constants.inc"
class EntityScriptingInterface : public QObject {
    Q_OBJECT
public:
    bool write { false }, rez { true }, deny { false }; QVariantList calls;
    Q_INVOKABLE bool canWriteAssets() { return write; } Q_INVOKABLE bool canRez() { return rez; } Q_INVOKABLE bool canRezTmp() { return false; }
    #include "image-api-declaration.inc"
    QUuid addEntity(const EntityItemProperties& properties) { calls.append(properties.values); return deny || !rez ? QUuid() : QUuid::createUuid(); }
    Q_INVOKABLE QUuid addModelEntity(QString name,QString url,QString textures,QString shape,bool dynamic,bool collisionless,bool grabbable,const glm::vec3& position,const glm::vec3& gravity) { calls.append(QVariantMap{{"kind","model"},{"name",name},{"url",url},{"shape",shape},{"dynamic",dynamic},{"position",QVariantMap{{"x",position.x},{"y",position.y},{"z",position.z}}}});return deny?QUuid():QUuid::createUuid(); }
signals: void canWriteAssetsChanged(bool);void canRezChanged(bool);void canRezTmpChanged(bool);
};
#include "image-api-body.inc"
class NativeContext : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool active MEMBER active CONSTANT)
    Q_PROPERTY(bool pinned MEMBER pinned NOTIFY pinnedChanged)
    Q_PROPERTY(bool hmdHandMouseActive READ hmdHandMouseActive CONSTANT)
    Q_PROPERTY(int invalid_position READ invalidPosition CONSTANT)
    Q_PROPERTY(bool gradientsSupported READ gradientsSupported CONSTANT)
    Q_PROPERTY(bool use3DKeyboard MEMBER threeD NOTIFY keyboardChanged)
    Q_PROPERTY(bool raised MEMBER raised NOTIFY keyboardChanged)
    Q_PROPERTY(bool punctuationMode MEMBER punctuation NOTIFY keyboardChanged)
    Q_PROPERTY(bool password MEMBER password NOTIFY keyboardChanged)
    Q_PROPERTY(glm::vec3 position READ position CONSTANT)
    Q_PROPERTY(QVariantMap orientation READ orientation CONSTANT)
public:
    bool pinned {false};
    bool hmdHandMouseActive() { return false; }
    int invalidPosition() { return -9999; } bool gradientsSupported() { return false; }
    Q_INVOKABLE void raise(QObject*) {}
    Q_INVOKABLE void centerOnVisible(QObject*) {}
    Q_INVOKABLE void repositionOnVisible(QObject*) {}
    bool active {true}, threeD {true}, raised {false}, punctuation {false}, password {false}, developer {false}; int fileDialogs {0}, urlDialogs {0};
    QPointer<QQuickWindow> inputWindow;
    glm::vec3 position() { return {1,2,3}; }
    QVariantMap orientation() { return {}; }
    Q_INVOKABLE bool isOptionChecked(QString name) {return name=="Developer Menu"&&developer;}
    Q_INVOKABLE void loadDialog() {++fileDialogs;}
    Q_INVOKABLE void loadScriptURLDialog() {++urlDialogs;}
    Q_INVOKABLE void playSound(int) {}
    Q_INVOKABLE void copyToClipboard(QString) {}
    Q_INVOKABLE glm::vec3 sum(const glm::vec3& a,const glm::vec3& b) {return {a.x+b.x,a.y+b.y,a.z+b.z};}
    Q_INVOKABLE glm::vec3 multiply(double value,const glm::vec3& a) {return {float(value*a.x),float(value*a.y),float(value*a.z)};}
    Q_INVOKABLE glm::vec3 multiply(const glm::vec3& a,double value) {return multiply(value,a);}
    Q_INVOKABLE glm::vec3 fromPolar(double,double) {return {0,-1,0};}
    Q_INVOKABLE glm::vec3 getForward(QVariantMap) {return {0,0,-1};}
    Q_INVOKABLE int deviceIdByTouchPoint(double,double) {return 0;}
    Q_INVOKABLE bool isLeftHand(int) {return false;}
    Q_INVOKABLE bool isRightHand(int) {return false;}
    Q_INVOKABLE void triggerHapticPulse(double,double,int) {}
    Q_INVOKABLE void synthesizeKeyPress(QString key,QObject* target=nullptr) {
        if (key.size() != 1) return;
        if (target) {
            QKeyEvent pressed(QEvent::KeyPress, key[0].toUpper().toLatin1(), Qt::NoModifier, key);
            QCoreApplication::sendEvent(target, &pressed);
        } else if (inputWindow) {
            QKeyEvent pressed(QEvent::KeyPress, key[0].toUpper().toLatin1(), Qt::NoModifier, key);
            QKeyEvent released(QEvent::KeyRelease, key[0].toUpper().toLatin1(), Qt::NoModifier, key);
            QCoreApplication::sendEvent(inputWindow, &pressed);
            QCoreApplication::sendEvent(inputWindow, &released);
        }
    }
signals: void pinnedChanged(); void hmdHandMouseActiveChanged(); void uploadRequest(QString path);void keyboardChanged();
};
class DesktopBoundary : public QQuickItem {
    Q_OBJECT
    Q_PROPERTY(bool pinned MEMBER pinned NOTIFY pinnedChanged)
    Q_PROPERTY(int invalid_position READ invalidPosition CONSTANT)
    Q_PROPERTY(bool gradientsSupported READ gradientsSupported CONSTANT)
    Q_PROPERTY(bool hmdHandMouseActive READ handMouse CONSTANT)
public:
    bool pinned {false};
    int invalidPosition() { return -9999; }
    bool gradientsSupported() { return false; }
    bool handMouse() { return false; }
    Q_INVOKABLE void raise(QObject*) {}
    Q_INVOKABLE void centerOnVisible(QObject*) {}
    Q_INVOKABLE void repositionOnVisible(QObject*) {}
signals:
    void pinnedChanged();
    void hmdHandMouseActiveChanged();
};
// The application/menu method bodies below are production source. Tablet,
// offscreen surface creation and login/HMD state are the host boundaries.
class TabletProxy : public QObject {
public:
    bool toolbar {false}, loaded {false};
    QList<QUrl> paths;
    bool getToolbarMode() { return toolbar; }
    bool isPathLoaded(QUrl) { return loaded; }
    void pushOntoStack(QUrl url) { loaded = true; paths.append(url); }
};
struct TabletScriptingInterface {
    TabletProxy tablet;
    QObject* getTablet(QString) { return &tablet; }
};
struct HMDScriptingInterface { bool show {false}; bool getShouldShowTablet() { return show; } };
constexpr const char* SYSTEM_TABLET = "com.highfidelity.interface.tablet.system";
struct OffscreenBoundary {
    QList<QUrl> paths;
    template<class F> void show(QUrl url, QString, F callback) { paths.append(url); callback(nullptr, nullptr); }
};
class Application : public QObject {
    Q_OBJECT
public:
    bool login {false}, hmd {false};
    OffscreenBoundary ui;
    bool getLoginDialogPoppedUp() { return login; }
    bool isHMDMode() { return hmd; }
    OffscreenBoundary* getOffscreenUI() { return &ui; }
public slots:
    void showAssetServerWidget(QString filePath = {});
signals:
    void uploadRequest(QString file);
};
#include "asset-route.inc"
namespace MenuOption { const QString AssetServer = "Asset Browser"; }
#undef qApp
#define qApp routeApplication
class MenuBoundary {
public:
    Application* routeApplication;
    QMenu menu;
    QAction* addActionToQMenuAndActionHash(QMenu* owner, QString text, int shortcut, QObject* receiver, const char* slot) {
        auto* action = owner->addAction(text);
        action->setShortcut(QKeySequence(shortcut));
        QObject::connect(action, SIGNAL(triggered()), receiver, slot);
        return action;
    }
    QAction* create() {
        auto* editMenu = &menu;
        #include "asset-menu.inc"
        return menu.actions().first();
    }
};
#undef qApp
class Services : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantList scriptCalls READ scriptCalls)
    Q_PROPERTY(QVariantList assetCalls READ assetCalls)
    Q_PROPERTY(QVariantList entityCalls READ entityCalls)
    Q_PROPERTY(QString fixtureFile READ fixtureFile CONSTANT)
    Q_PROPERTY(QString fixtureDirectory READ fixtureDirectory CONSTANT)
    Q_PROPERTY(bool keyboardRaised READ keyboardRaised)
    Q_PROPERTY(bool pickerCanceled READ pickerCanceled)
    Q_PROPERTY(int fileDialogCount READ fileDialogCount)
    Q_PROPERTY(int urlDialogCount READ urlDialogCount)
public:
    ScriptApi scripts; AssetsApi assets; EntityScriptingInterface entities; NativeContext context;FileDialogHelper files;QTemporaryDir temporary;
    DesktopBoundary desktop;
    FileDialogHelper::DocumentSelection pending;QString pendingId;bool canceled{false};
    Services(){qRegisterMetaType<glm::vec3>("glm::vec3");QFile file(fixtureFile());file.open(QFile::WriteOnly);file.write("print('fixture');");file.close();QDir(temporary.path()).mkdir("nested");}
    QVariantList scriptCalls(){return scripts.calls;}QVariantList assetCalls(){return assets.calls;}QVariantList entityCalls(){return entities.calls;}
    QString fixtureFile(){return temporary.path()+"/ordinary.js";}QString fixtureDirectory(){return temporary.path();}bool keyboardRaised(){return context.raised;}bool pickerCanceled(){return canceled;}int fileDialogCount(){return context.fileDialogs;}int urlDialogCount(){return context.urlDialogs;}
    Q_INVOKABLE void reset(){scripts.calls.clear();assets.calls.clear();assets.error.clear();assets.populate();entities.calls.clear();entities.write=false;entities.rez=true;entities.deny=false;context.developer=false;context.threeD=true;context.raised=false;context.punctuation=false;context.fileDialogs=context.urlDialogs=0;canceled=false;emit context.keyboardChanged();}
    Q_INVOKABLE void permissions(bool write,bool rez){entities.write=write;entities.rez=rez;emit entities.canWriteAssetsChanged(write);emit entities.canRezChanged(rez);}
    Q_INVOKABLE void developer(bool value){context.developer=value;}
    Q_INVOKABLE void denyImport(bool value){entities.deny=value;}
    Q_INVOKABLE void backendError(QString message){assets.error=message;}
    Q_INVOKABLE void assetBakingState(QString state) { assets.tree.item(0)->child(0)->setData(state,261); }
    Q_INVOKABLE void resetAssetModel() { assets.tree.clear(); }
    Q_INVOKABLE bool assetRefreshEnabled() { return assets.tree.automatic; }
    Q_INVOKABLE void loadError(){emit scripts.scriptLoadError("https://example.invalid/fail.js","");}
    Q_INVOKABLE void keyboard3D(bool value){context.threeD=value;emit context.keyboardChanged();}
    Q_INVOKABLE void bindSurface(QObject* item) {
        auto* surface = qobject_cast<QQuickItem*>(item);
        if (surface) { desktop.setParentItem(surface); context.inputWindow = surface->window(); }
    }
    Q_INVOKABLE void installPicker(){FileDialogHelper::setDocumentPickerOperator([this](const QString&id,const QString&,const QString&,bool,FileDialogHelper::DocumentSelection callback){pendingId=id;pending=callback;return true;},[this](const QString&id){if(id==pendingId)canceled=true;});}
    Q_INVOKABLE void completePicker(bool fail=false){if(pending)pending(fail?QList<QUrl>{QUrl("content://not-materialized")}:QList<QUrl>{QUrl::fromLocalFile(fixtureFile())},{});}
    Q_INVOKABLE void removePicker(){FileDialogHelper::setDocumentPickerOperator({},{});}
    Q_INVOKABLE QVariantMap exerciseAssetMenuRoutes() {
        Application app;
        MenuBoundary menu; menu.routeApplication = &app;
        auto* action = menu.create();
        const bool readable = action->isEnabled();
        DependencyManager::get<NodeList>()->revokeWrites();
        action->trigger();
        auto* tablet = &DependencyManager::get<TabletScriptingInterface>()->tablet;
        tablet->paths.clear(); tablet->loaded = false; tablet->toolbar = false;
        app.hmd = true; action->trigger(); action->trigger();
        const bool tabletOnce = tablet->paths.size() == 1 && tablet->paths[0] == QUrl("qrc:///qml/hifi/dialogs/TabletAssetServer.qml");
        tablet->toolbar = true; action->trigger();
        app.login = true; action->trigger();
        tablet->toolbar = false;
        return {{"readable",readable && action->isEnabled()}, {"tabletOnce",tabletOnce},
            {"desktop",app.ui.paths.size() == 2 && app.ui.paths[0] == QUrl("hifi/AssetServer.qml")}};
    }
    Q_INVOKABLE QVariantMap exerciseDocumentBoundaries() {
        FileDialogHelper helper;
        QList<FileDialogHelper::DocumentSelection> callbacks;
        int selected = 0, failed = 0, canceledRequests = 0, canceledLeases = 0;
        QObject::connect(&helper, &FileDialogHelper::documentsSelected, [&](const QString&, const QList<QUrl>&) { ++selected; });
        QObject::connect(&helper, &FileDialogHelper::documentSelectionFailed, [&](const QString&, const QString&) { ++failed; });
        QObject::connect(&helper, &FileDialogHelper::documentSelectionCanceled, [&](const QString&) { ++canceledRequests; });
        FileDialogHelper::setDocumentPickerOperator(
            [&](const QString&, const QString&, const QString&, bool, FileDialogHelper::DocumentSelection callback) {
                callbacks.append(callback);
                return true;
            }, [&](const QString&) { ++canceledLeases; });
        const auto file = QUrl::fromLocalFile(fixtureFile());
        const QString first = helper.openDocuments("single", "*", false);
        const bool busy = helper.openDocuments("busy", "*", false).isEmpty();
        callbacks[0]({file, file}, {});
        QCoreApplication::processEvents();
        const QString next = helper.openDocuments("multiple", "*", true);
        callbacks[0]({file}, {}); // Completion from an earlier lease cannot claim the new request.
        QCoreApplication::processEvents();
        const bool staleIgnored = selected == 0 && !next.isEmpty();
        helper.cancelDocuments(next);
        callbacks[1]({file}, {});
        QCoreApplication::processEvents();
        helper.openDocuments("bounded", "*", true);
        QList<QUrl> tooMany;
        for (int i = 0; i <= FileDialogHelper::MAX_DOCUMENT_COUNT; ++i) tooMany.append(file);
        callbacks[2](tooMany, {});
        QCoreApplication::processEvents();
        QFile oversized(temporary.path() + "/oversized.bin");
        oversized.open(QFile::WriteOnly);
        oversized.resize(FileDialogHelper::MAX_DOCUMENT_BYTES + 1);
        oversized.close();
        helper.openDocuments("bounded bytes", "*", false);
        callbacks[3]({QUrl::fromLocalFile(oversized.fileName())}, {});
        QCoreApplication::processEvents();
        oversized.remove();
        helper.openDocuments("success", "*", true);
        callbacks[4]({file}, {});
        QCoreApplication::processEvents();
        auto* deletedOwner = new FileDialogHelper;
        deletedOwner->openDocuments("deleted owner", "*", true);
        FileDialogHelper::setDocumentPickerOperator({}, {});
        delete deletedOwner;
        callbacks[5]({file}, {});
        QCoreApplication::processEvents();
        FileDialogHelper::setDocumentPickerOperator({}, {});
        QFile retained(fixtureFile());
        const bool readableAfterCompletion = retained.open(QFile::ReadOnly) && retained.readAll() == "print('fixture');";
        return {{"busy", busy}, {"staleIgnored", staleIgnored}, {"selected", selected},
            {"failed", failed}, {"canceledRequests", canceledRequests}, {"canceledLeases", canceledLeases},
            {"retained", readableAfterCompletion}, {"distinctIds", first != next}};
    }
    Q_INVOKABLE bool selectDesktopFile(){for(auto* widget:QApplication::topLevelWidgets())if(auto* dialog=qobject_cast<QFileDialog*>(widget)){dialog->setDirectory(temporary.path());QTest::qWait(120);dialog->selectFile(fixtureFile());QTest::qWait(20);auto* input=dialog->findChild<QLineEdit*>("fileNameEdit");if(!input)return false;input->setFocus();input->clear();QTest::keyClicks(input,fixtureFile());QTest::keyClick(input,Qt::Key_Return);return dialog->result()==QDialog::Accepted;}return false;}
};
class Setup : public QObject {
    Q_OBJECT
public: Services service;
public slots:
    void qmlEngineAvailable(QQmlEngine* engine){
        auto* context=engine->rootContext();context->setContextProperty("TestServices",&service);
        context->setContextProperty("ProductionRoot",QUrl::fromLocalFile(qEnvironmentVariable("OVERTE_QML_SOURCE_ROOT")+"/"));
        context->setContextProperty("ScriptDiscoveryService",&service.scripts);context->setContextProperty("Assets",&service.assets);context->setContextProperty("Entities",&service.entities);context->setContextProperty("fileDialogHelper",&service.files);
        context->setContextProperty("desktop", &service.desktop);
        for(auto* name:{"ApplicationInterface","HMD","MenuInterface","Tablet","KeyboardScriptingInterface","MyAvatar","Vec3","Quat","Window","webEntity","QmlSurface","Pointers","Controller","Reticle"})context->setContextProperty(name,&service.context);
    }
};
int main(int argc,char**argv){QApplication app(argc,argv);Setup setup;return quick_test_main_with_setup(argc,argv,"NativeScriptsAssets",nullptr,&setup);}
#include "native-services.moc"
