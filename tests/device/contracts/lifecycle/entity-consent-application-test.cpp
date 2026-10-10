#include <QGuiApplication>
#include <QQuickItem>
#include <QPointer>
#include <QSharedPointer>
#include <QCryptographicHash>
#include <QMessageBox>
#include <QUrl>
#include <QEvent>
#include <QDebug>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickWindow>
#include <QDateTime>
#include <QRegularExpression>
#include <QTimer>
#include <QEventLoop>
#include "EntityScriptConsentUiTest.h"
#include <deque>
#include <thread>
#include <cassert>
#include "EntityScriptConsent.h"
#define qCInfo(...) qInfo()
#define qCWarning(...) qWarning()
static const QString URL_SCHEME_OVERTE="hifi";
struct PathUtils { static QUrl expandToLocalDataAbsolutePath(const QUrl& url){return url;} };
struct OctreeProcessor { std::atomic<int> counter{0}; std::atomic<int>& getFullSceneReceivedCounter(){return counter;} };
using EntityItemID=QString;
class ModalDialogListener:public QObject {
    Q_OBJECT
public:
    QPointer<QQuickItem> item;
    QString text;
    ModalDialogListener(){item=new QQuickItem;item->setParent(this);}
    QQuickItem* getDialogItem(){return item;}
public slots:
    void selectButton(int button){emit response(button);}
signals:
    void response(const QVariant&);
};
struct OffscreenUi {
    static inline QVector<QPointer<ModalDialogListener>> dialogs;
    static inline std::function<void()> onCreate;
    static ModalDialogListener* asyncInformation(const QString&,const QString&){return nullptr;}
    static ModalDialogListener* asyncQuestion(const QString&,const QString& text,QMessageBox::StandardButtons,QMessageBox::StandardButton button){
        assert(button==QMessageBox::No);
        auto* dialog=new ModalDialogListener;dialog->text=text;dialogs.push_back(dialog);
        if(onCreate){auto callback=std::move(onCreate);onCreate={};callback();}
        return dialog;
    }
};
struct Domain {bool isConnected()const{return true;}};
struct NodeList {Domain domain;Domain& getDomainHandler(){return domain;}};
struct AddressManager {
    static inline QUrl address=QUrl("https://world.invalid/world?secret=world-canary");
    QUrl currentAddress(bool domainOnly)const{assert(domainOnly);return address;}
};
struct DependencyManager {template<class T>static QSharedPointer<T>get(){static auto value=QSharedPointer<T>::create();return value;}};
class EntityTreeRenderer:public QObject {
public:
    using Prompt=std::function<void(const EntityItemID&,const std::shared_ptr<EntityScriptConsentRequest>&,std::function<void(bool)>)>;
    std::shared_ptr<EntityScriptConsentScope> _entityScriptConsentScope;
    Prompt prompt;
    void beginEntityScriptConsent(std::shared_ptr<EntityScriptConsentScope> scope,Prompt value){_entityScriptConsentScope=scope;prompt=value;}
    void endEntityScriptConsent(){if(_entityScriptConsentScope){_entityScriptConsentScope->invalidate();}_entityScriptConsentScope.reset();prompt={};}
};
class Application:public QObject {
    Q_OBJECT
public:
    bool _aboutToQuit{false},_startUpFinished{true},_isForeground{true};
    QSharedPointer<EntityTreeRenderer> renderer=QSharedPointer<EntityTreeRenderer>::create();
    QSharedPointer<EntityTreeRenderer>getEntities(){return renderer;}
    bool serverless{false};
    bool isServerlessMode()const{return serverless;}
    void setIsServerlessMode(bool value){serverless=value;}
    void updateWindowTitle(){}
    void loadServerlessDomain(QUrl){assert(!_entityScriptConsentScope);++loads;}
    void clearDomainOctreeDetails(bool){assert(!_entityScriptConsentScope);++clears;}
    void domainURLChanged(QUrl);
    void resettingDomain();
    int loads{0},clears{0};
    quint64 _serverlessDomainRequestGeneration{0};
    bool _picoServerlessLoadFailed{false}, _picoServerlessSceneImportInProgress{false};
    bool _picoServerlessSceneImportCommitted{false},_picoInitialServerlessHandoffComplete{true};
    bool _notifiedPacketVersionMismatchThisDomain{false};
    QUrl _picoServerlessSceneURL,_picoDeferredServerlessSceneURL;
    QSharedPointer<OctreeProcessor> _octreeProcessor=QSharedPointer<OctreeProcessor>::create();
    void beginEntityScriptConsentReview();
    void invalidateEntityScriptConsent();
    void enqueueEntityScriptConsent(const std::shared_ptr<EntityScriptConsentRequest>&,std::function<void(bool)>);
    void showNextEntityScriptConsent();
    struct PendingEntityScriptConsent {std::shared_ptr<EntityScriptConsentRequest>request;std::function<void(bool)>decide;};
    std::shared_ptr<EntityScriptConsentScope> _entityScriptConsentScope;
    QSharedPointer<QObject> _entityScriptConsentDispatch;
    std::deque<PendingEntityScriptConsent> _pendingEntityScriptConsents;
    QPointer<ModalDialogListener> _entityScriptConsentDialog;
    std::function<void(bool)> _activeEntityScriptConsentDecision;
    std::shared_ptr<EntityScriptConsentRequest> _activeEntityScriptConsentRequest;
    quint64 _entityScriptConsentUiGeneration{0};
};
// ACTUAL_SOURCE
static Application* testedApplication=nullptr;
#undef qApp
#define qApp testedApplication
class TestScriptingInterface:public QObject {
public:
    QString _testResultsLocation="owned-test-output";
    QVariantMap receipt;
    bool iosEntityScriptConsentTest(const QVariantMap&);
    void saveObject(QVariant object,const QString& name){assert(name=="ios-entity-consent-result.json");receipt=object.toMap();}
};
// ACTUAL_IOS_CONSENT_SOURCE
static void deliver(){for(int i=0;i!=6;++i){QCoreApplication::sendPostedEvents(nullptr,QEvent::MetaCall);}}
static void cleanup(){QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete);}
static std::shared_ptr<EntityScriptConsentRequest> request(Application& application){
    return std::make_shared<EntityScriptConsentRequest>(application._entityScriptConsentScope,
        "https://user:credential-canary@source.invalid/%3Cscript%3E?token=query-canary#fragment-canary",false);
}
int main(int argc,char**argv){
    QGuiApplication qt(argc,argv);
    Application app;
    app.beginEntityScriptConsentReview();deliver();assert(app.renderer->prompt);
    auto first=request(app);QVector<bool> answers;
    std::thread producer([&]{app.renderer->prompt("entity",first,[&](bool value){answers.push_back(value);});});producer.join();
    deliver();assert(app._entityScriptConsentDialog);
    auto dialog=app._entityScriptConsentDialog;
    assert(!dialog->text.contains("credential-canary")&&!dialog->text.contains("query-canary")&&!dialog->text.contains("fragment-canary")&&!dialog->text.contains("world-canary"));
    assert(!dialog->text.contains("<script>"));
    emit dialog->response(int(QMessageBox::Yes));emit dialog->response(int(QMessageBox::Yes));deliver();
    assert(answers==QVector<bool>{true});dialog->deleteLater();cleanup();
    // Drive the real QML click function through the native UI binding, while
    // preserving the actual Application listener and source/origin scope.
    app.beginEntityScriptConsentReview();deliver();answers.clear();
    auto reviewed=request(app);
    app.enqueueEntityScriptConsent(reviewed,[&](bool value){answers.push_back(value);});
    dialog=app._entityScriptConsentDialog;
    QQmlEngine engine;QQmlComponent component(&engine);
    QQuickWindow window;window.resize(400,300);window.show();
    component.setData(R"qml(import QtQuick 2.5
Item {
    width: 400; height: 300; visible: true
    property int buttons: 81920
    property int defaultButton: 65536
    property int clickedButton: 0
    signal selected(int button)
    // PRODUCTION_DIALOG_CLICK
})qml",QUrl());
    auto* actualDialog=qobject_cast<QQuickItem*>(component.create());
    assert(actualDialog && component.errors().isEmpty());
    actualDialog->setParentItem(window.contentItem());
    QQmlEngine::setObjectOwnership(actualDialog,QQmlEngine::JavaScriptOwnership);
    dialog->item->deleteLater();dialog->item=actualDialog;actualDialog->setParent(dialog);
    QObject::connect(actualDialog,SIGNAL(selected(int)),dialog,SLOT(selectButton(int)));
    const auto scope=app._entityScriptConsentScope;
    assert(!pressEntityScriptConsentDialog(actualDialog,reviewed,scope,"wrong-source",reviewed->origin()));
    assert(!pressEntityScriptConsentDialog(actualDialog,reviewed,scope,reviewed->source(),"wrong-world"));
    actualDialog->setVisible(false);
    assert(!pressEntityScriptConsentDialog(actualDialog,reviewed,scope,reviewed->source(),reviewed->origin()));
    actualDialog->setVisible(true);
    assert(answers.isEmpty());
    assert(pressEntityScriptConsentDialog(actualDialog,reviewed,scope,reviewed->source(),reviewed->origin()));
    deliver();assert(answers==QVector<bool>{true});
    assert(!app._activeEntityScriptConsentRequest);dialog->deleteLater();cleanup();
    // The request may be invalidated while its dialog remains alive.
    auto stale=request(app);answers.clear();app.enqueueEntityScriptConsent(stale,[&](bool value){answers.push_back(value);});
    dialog=app._entityScriptConsentDialog;app._entityScriptConsentScope->invalidate();
    assert(!pressEntityScriptConsentDialog(dialog->item,stale,app._entityScriptConsentScope,stale->source(),stale->origin()));
    emit dialog->response(int(QMessageBox::Yes));deliver();assert(answers==QVector<bool>{false});dialog->deleteLater();cleanup();
    // Session invalidation closes the active decision; a late Yes is ignored.
    app.beginEntityScriptConsentReview();deliver();answers.clear();app.enqueueEntityScriptConsent(request(app),[&](bool value){answers.push_back(value);});
    dialog=app._entityScriptConsentDialog;app.invalidateEntityScriptConsent();
    emit dialog->response(int(QMessageBox::Yes));deliver();assert(answers==QVector<bool>{false});cleanup();
    // A queued producer from the old scope cannot create a new dialog.
    app.beginEntityScriptConsentReview();deliver();answers.clear();auto queued=request(app);
    app.renderer->prompt("entity",queued,[&](bool value){answers.push_back(value);});app.invalidateEntityScriptConsent();deliver();cleanup();
    assert(!app._entityScriptConsentDialog&&!app._entityScriptConsentScope);
    // Dialog creation can itself reenter session replacement.
    app.beginEntityScriptConsentReview();deliver();auto oldScope=app._entityScriptConsentScope;answers.clear();
    OffscreenUi::onCreate=[&]{app.beginEntityScriptConsentReview();};
    app.enqueueEntityScriptConsent(request(app),[&](bool value){answers.push_back(value);});deliver();cleanup();
    assert(answers==QVector<bool>{false}&&app._entityScriptConsentScope!=oldScope&&app._entityScriptConsentScope->active());
    assert(!app._entityScriptConsentDialog&&!app._activeEntityScriptConsentRequest);
    // Complete real domain/reset functions with world mutation seams: redundant
    // Pico messages preserve consent; accepted changes revoke before tree clear.
    app._picoServerlessSceneURL=QUrl("file:///fixture.json");
    app._picoServerlessSceneImportCommitted=true;
    auto current=app._entityScriptConsentScope;
    app.domainURLChanged(app._picoServerlessSceneURL);
    app.domainURLChanged(QUrl());app.resettingDomain();
    assert(current->active() && app._entityScriptConsentScope==current && app.clears==0 && app.loads==0);
    app._picoInitialServerlessHandoffComplete=false;
    app.domainURLChanged(QUrl("hifi://ignored-startup"));assert(current->active());
    app._picoInitialServerlessHandoffComplete=true;
    app.domainURLChanged(QUrl("hifi://new-world"));
    assert(!current->active() && !app._entityScriptConsentScope && app.clears==1);
    app.beginEntityScriptConsentReview();deliver();current=app._entityScriptConsentScope;
    app.resettingDomain();assert(!current->active() && app.clears==2);
    app.beginEntityScriptConsentReview();deliver();current=app._entityScriptConsentScope;
    app._picoServerlessSceneImportInProgress=true;
    app._picoServerlessSceneURL=QUrl("file:///active-import.json");
    app.domainURLChanged(app._picoServerlessSceneURL);app.domainURLChanged(QUrl());
    assert(current->active());
    app.domainURLChanged(QUrl("file:///new-import.json"));
    assert(!current->active() && app._picoDeferredServerlessSceneURL==QUrl("file:///new-import.json"));
    app._isForeground=false;app.beginEntityScriptConsentReview();deliver();cleanup();assert(!app._entityScriptConsentScope);
    // Compile and execute the actual E2E hook with UI dispatch, the production
    // dialog click and listener, and only the world/renderer/file boundaries held.
    testedApplication=&app;app._isForeground=true;
    AddressManager::address=QUrl("http://fixture.invalid:49121/scene.json");
    TestScriptingInterface test;
    QVariantMap command{{"schemaVersion",1},{"commandId","ios-cccccccccccccccccccccccccccccccc"},
        {"action","entity-script-consent"},{"operation","review"},
        {"source","http://fixture.invalid:49121/scripted_interactable.js"}};
    auto foreign=command;foreign["source"]="http://fixture.invalid:49121/foreign.js";
    assert(!test.iosEntityScriptConsentTest(foreign));
    assert(test.iosEntityScriptConsentTest(command));deliver();
    auto controlled=std::make_shared<EntityScriptConsentRequest>(app._entityScriptConsentScope,
        command["source"].toString(),false);
    answers.clear();app.enqueueEntityScriptConsent(controlled,[&](bool value){answers.push_back(value);});
    dialog=app._entityScriptConsentDialog;
    auto* controlledDialog=qobject_cast<QQuickItem*>(component.create());
    assert(controlledDialog);controlledDialog->setParentItem(window.contentItem());
    QQmlEngine::setObjectOwnership(controlledDialog,QQmlEngine::JavaScriptOwnership);
    dialog->item->deleteLater();dialog->item=controlledDialog;controlledDialog->setParent(dialog);
    QObject::connect(controlledDialog,SIGNAL(selected(int)),dialog,SLOT(selectButton(int)));
    QEventLoop events;QTimer::singleShot(400,&events,&QEventLoop::quit);events.exec();
    assert(test.receipt["ok"].toBool() && test.receipt["visible"].toBool());
    assert(test.receipt["source"]==command["source"] && test.receipt["origin"]==AddressManager::address.toString());
    assert(answers.isEmpty());
    test.receipt.clear();command["operation"]="allow";
    assert(test.iosEntityScriptConsentTest(command));deliver();
    assert(test.receipt["ok"].toBool() && answers==QVector<bool>{true});
    assert(!app._activeEntityScriptConsentRequest);dialog->deleteLater();cleanup();
    test.receipt.clear();assert(test.iosEntityScriptConsentTest(command));deliver();
    assert(!test.receipt["ok"].toBool());
}
#include "test.moc"
