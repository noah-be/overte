#include <QGuiApplication>
#include <QQuickItem>
#include <QPointer>
#include <QSharedPointer>
#include <QCryptographicHash>
#include <QMessageBox>
#include <QUrl>
#include <QEvent>
#include <QDebug>
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
struct AddressManager {QUrl currentAddress(bool domainOnly)const{assert(domainOnly);return QUrl("https://world.invalid/world?secret=world-canary");}};
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
    // The request may be invalidated while its dialog remains alive.
    auto stale=request(app);answers.clear();app.enqueueEntityScriptConsent(stale,[&](bool value){answers.push_back(value);});
    dialog=app._entityScriptConsentDialog;app._entityScriptConsentScope->invalidate();
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
}
#include "test.moc"
