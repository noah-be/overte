#include <QCoreApplication>
#include <QEventLoop>
#include <QTimer>
#include <QUrl>
#include <QMap>
#include <QHash>
#include <QVariantMap>
#include <QSharedPointer>
#include <QPointer>
#include <QFileInfo>
#include <QDateTime>
#include <QRegularExpression>
#include <QMetaEnum>
#include <QDebug>
#include <functional>
#include <vector>
#include <cmath>
#include <cassert>
#define qCDebug(...) qDebug()
#define qCWarning(...) qWarning()
struct Dependency {};
struct DependencyManager;
#define SINGLETON_DEPENDENCY friend struct DependencyManager;
// ACTUAL_HEADER
class ResourceRequest : public QObject {
    Q_OBJECT
public:
    enum Result { Success, AccessDenied, InvalidURL, NotFound, RedirectFail, Error };
    Q_ENUM(Result)
    enum State { Pending, Finished };
    QUrl url; Result result { Success }; State state { Pending }; QByteArray data;
    bool strict { false }, cacheEnabled { true }; int sends { 0 };
    explicit ResourceRequest(QUrl value) : url(value) {}
    QUrl getUrl() const { return url; }
    Result getResult() const { return result; }
    State getState() const { return state; }
    QByteArray getData() const { return data; }
    void setCacheEnabled(bool value) { cacheEnabled = value; }
    void setFailOnRedirect(bool value) { strict = value; }
    void send() { ++sends; }
    static QString toHttpDateString(qint64 value) { return QString::number(value); }
    void complete(Result value, QByteArray body) { result=value; data=body; state=Finished; emit finished(); }
signals:
    void finished();
};
class ResourceManager {
public:
    QVector<QPointer<ResourceRequest>> requests;
    QHash<QUrl,QUrl> substitutions;
    bool failNext {false}, changeNext {false};
    std::function<void()> onNormalize;
    QUrl normalizeURL(const QUrl& url) { if(onNormalize){auto cb=std::move(onNormalize);onNormalize={};cb();} return substitutions.value(url,url); }
    ResourceRequest* createResourceRequest(QObject*, QUrl url, bool, int, const char*) {
        if (failNext || url.scheme()=="unsupported") { failNext=false; return nullptr; }
        if (changeNext) { changeNext=false; url=QUrl("https://changed.invalid/resource.js"); }
        auto* request = new ResourceRequest(url); requests.push_back(request); return request;
    }
};
struct ScriptEngines { bool isStopped() const { return false; } };
static QSharedPointer<ResourceManager> resources = QSharedPointer<ResourceManager>::create();
static QSharedPointer<ScriptEngines> engines = QSharedPointer<ScriptEngines>::create();
static QSharedPointer<ScriptCache> cache;
struct DependencyManager {
    template<class T> static QSharedPointer<T> get() {
        if constexpr (std::is_same_v<T,ResourceManager>) { return resources; }
        else if constexpr (std::is_same_v<T,ScriptCache>) { return cache; }
        else { return engines; }
    }
    static ScriptCache* make() { return new ScriptCache; }
};
// ACTUAL_SOURCE
struct Outcome { int calls {0}; QString text, status, source; bool success {false}; };
static contentAvailableCallback capture(Outcome& outcome) {
    return [&outcome](const QString& source,const QString& text,bool,bool success,const QString& status) {
        ++outcome.calls; outcome.text=text; outcome.status=status; outcome.source=source; outcome.success=success;
    };
}
int main(int argc,char**argv) {
    QCoreApplication app(argc,argv);
    cache.reset(DependencyManager::make());
    const auto scope = std::make_shared<EntityScriptConsentScope>("hifi://world-a");
    const QString url="https://fixture.invalid/entity.js";
    Outcome ordinary, strict, joined, cachedOrdinary, cachedStrict;
    cache->getScriptContents(url,capture(ordinary),false,0,false);
    cache->getScriptContents(url,capture(strict),false,0,true,scope);
    assert(resources->requests.size()==2);
    assert(!resources->requests[0]->strict && resources->requests[1]->strict);
    resources->requests[0]->complete(ResourceRequest::Success,"ordinary");
    assert(ordinary.success && ordinary.text=="ordinary" && strict.calls==0);
    cache->getScriptContents(url,capture(joined),false,0,true,scope);
    cache->getScriptContents(url,capture(cachedOrdinary),false,0,false);
    assert(resources->requests.size()==2 && cachedOrdinary.text=="ordinary");
    resources->requests[1]->complete(ResourceRequest::Success,"strict");
    assert(strict.success && joined.success && strict.text=="strict" && joined.text=="strict");
    cache->getScriptContents(url,capture(cachedStrict),false,0,true,scope);
    assert(resources->requests.size()==2 && cachedStrict.text=="strict");
    cache->deleteScript(QUrl(url));
    Outcome freshOrdinary, rejected;
    cache->getScriptContents(url,capture(freshOrdinary),false,0,false);
    cache->getScriptContents(url,capture(rejected),false,5,true,scope);
    assert(resources->requests.size()==4);
    resources->requests[2]->complete(ResourceRequest::Success,"ordinary-new");
    resources->requests[3]->complete(ResourceRequest::RedirectFail,"unapproved-body");
    assert(rejected.calls==1 && !rejected.success && rejected.status=="RedirectFail" && rejected.text.isEmpty());
    const QString mapped="https://fixture.invalid/mapped.js";
    resources->substitutions[QUrl(mapped)]=QUrl("https://replacement.invalid/hidden.js");
    Outcome substituted;
    cache->getScriptContents(mapped,capture(substituted),false,0,true,scope);
    assert(substituted.calls==1 && !substituted.success && substituted.status=="InvalidURL");
    assert(resources->requests.size()==4);
    Outcome inlineCode;
    cache->getScriptContents("javascript:(function(){})",capture(inlineCode),false,0,true,scope);
    assert(inlineCode.success && inlineCode.calls==1 && resources->requests.size()==4);
    // Retry uses the same strict policy, never the ordinary request profile.
    Outcome retry;
    cache->getScriptContents("https://fixture.invalid/retry.js",capture(retry),false,1,true,scope);
    assert(resources->requests.size()==5 && resources->requests[4]->strict);
    resources->requests[4]->complete(ResourceRequest::Error,{});
    QEventLoop loop; QTimer::singleShot(700,&loop,&QEventLoop::quit); loop.exec();
    assert(resources->requests.size()==6 && resources->requests[5]->strict && !resources->requests[5]->cacheEnabled);
    resources->requests[5]->complete(ResourceRequest::Success,"retried-strict");
    assert(retry.calls==1 && retry.success && retry.text=="retried-strict");
    // Clearing ATP entries removes both profiles while keeping HTTPS entries.
    for (bool mode : {false,true}) {
        Outcome atp;
        cache->getScriptContents("atp:/fixture.js",capture(atp),false,0,mode,scope);
        resources->requests.back()->complete(ResourceRequest::Success,"atp");
        assert(atp.success);
    }
    const auto before=resources->requests.size();
    cache->clearATPScriptsFromCache();
    Outcome atpAgain;
    cache->getScriptContents("atp:/fixture.js",capture(atpAgain),false,0,true,scope);
    assert(resources->requests.size()==before+1);
    resources->requests.back()->complete(ResourceRequest::Success,"atp-new");
    Outcome retained;
    cache->getScriptContents(url,capture(retained),false,0,false);
    assert(retained.text=="ordinary-new" && resources->requests.size()==before+1);
    Outcome unsupported, changed;
    cache->getScriptContents("unsupported:/script",capture(unsupported),false,0,true,scope);
    assert(unsupported.calls==1 && !unsupported.success && unsupported.status=="InvalidURL");
    resources->changeNext=true;
    cache->getScriptContents("https://fixture.invalid/changed.js",capture(changed),false,0,true,scope);
    assert(changed.calls==1 && !changed.success && resources->requests.back()->sends==0);
    Outcome retryCreation;
    cache->getScriptContents("https://fixture.invalid/retry-creation.js",capture(retryCreation),false,1,true,scope);
    resources->failNext=true;
    resources->requests.back()->complete(ResourceRequest::Error,{});
    QEventLoop failedLoop; QTimer::singleShot(700,&failedLoop,&QEventLoop::quit); failedLoop.exec();
    assert(retryCreation.calls==1 && !retryCreation.success && retryCreation.status=="InvalidURL");
    // Same relative ATP URL belongs to different consent sessions, including
    // concurrent pending requests and a completed memory entry.
    const auto worldB = std::make_shared<EntityScriptConsentScope>("hifi://world-b");
    Outcome oldPending, newPending, oldCached, newCached, denied;
    const auto sessionStart = resources->requests.size();
    cache->getScriptContents("atp:/session.js",capture(oldPending),false,0,true,scope);
    auto oldRequest = resources->requests.back();
    cache->getScriptContents("atp:/session.js",capture(newPending),false,0,true,worldB);
    auto newRequest = resources->requests.back();
    assert(resources->requests.size()==sessionStart+2 && oldRequest!=newRequest);
    cache->getScriptContents("atp:/cached.js",capture(oldCached),false,0,true,scope);
    resources->requests.back()->complete(ResourceRequest::Success,"world-a-only");
    cache->getScriptContents("atp:/cached.js",capture(newCached),false,0,true,worldB);
    assert(!newCached.calls && resources->requests.size()==sessionStart+4);
    resources->requests.back()->complete(ResourceRequest::Success,"world-b-only");
    assert(newCached.text=="world-b-only");
    scope->invalidate();
    QCoreApplication::processEvents();
    assert(oldPending.calls==1 && !oldPending.success && oldPending.status=="Cancelled");
    oldRequest->complete(ResourceRequest::Success,"late-world-a");
    assert(oldPending.calls==1 && newPending.calls==0);
    newRequest->complete(ResourceRequest::Success,"world-b-current");
    assert(newPending.calls==1 && newPending.text=="world-b-current");
    cache->getScriptContents("atp:/cached.js",capture(denied),false,0,true,scope);
    assert(denied.calls==1 && !denied.success && denied.text.isEmpty());
    Outcome noScope;
    cache->getScriptContents("javascript:(function(){})",capture(noScope),false,0,true);
    assert(noScope.calls==1 && !noScope.success && noScope.status=="Cancelled");
    const auto reentrantScope=std::make_shared<EntityScriptConsentScope>("hifi://reentrant");
    resources->onNormalize=[&]{reentrantScope->invalidate();};
    Outcome reentrant;
    const auto beforeReentrant=resources->requests.size();
    cache->getScriptContents("atp:/reentrant.js",capture(reentrant),false,0,true,reentrantScope);
    assert(reentrant.calls==1 && !reentrant.success && reentrant.text.isEmpty());
    assert(resources->requests.size()==beforeReentrant);
    cache->clearCache();
    QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete);
}
#include "test.moc"
