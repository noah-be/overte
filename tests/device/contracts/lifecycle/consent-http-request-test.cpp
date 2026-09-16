#include <QCoreApplication>
#include <QNetworkRequest>
#include <QNetworkReply>
#include <QTimer>
#include <QMetaEnum>
#include <QSharedPointer>
#include <QDebug>
#include <cassert>
#include <cstring>
#include <QLoggingCategory>
Q_LOGGING_CATEGORY(networking,"consent-http-fixture")
struct ByteRange { qint64 fromInclusive {0}, toExclusive {0}; bool isSet() const {return toExclusive>0;} };
class ResourceRequest : public QObject {
    Q_OBJECT
public:
    enum State { NotStarted, InProgress, Finished };
    enum Result { Success, Timeout, NotFound, InvalidURL, AccessDenied, ServerUnavailable, Error, RedirectFail };
    ResourceRequest(QUrl url,bool,qint64):_url(url){}
    void send() {_state=InProgress;doSend();}
    void setFailOnRedirect(bool value){_failOnRedirect=value;}
    bool loadedFromCache() const {return _loadedFromCache;}
    Result getResult() const {return _result;}
    QByteArray getData() const {return _data;}
    void recordBytesDownloadedInStats(const QString&,qint64){}
    QUrl _url;State _state{NotStarted};Result _result{Error};QByteArray _data;
    bool _failOnRedirect{false},_cacheEnabled{true},_loadedFromCache{false};
    ByteRange _byteRange;bool _rangeRequestSuccessful{false};uint64_t _totalSizeOfResource{0};QString _webMediaType;
protected:
    virtual void doSend()=0;
signals:
    void finished();
    void progress(qint64,qint64);
};
struct StatTracker {void incrementStat(const QString&) {}};
const QString STAT_HTTP_REQUEST_STARTED="started",STAT_HTTP_REQUEST_SUCCESS="success",STAT_HTTP_REQUEST_CACHE="cache",STAT_HTTP_REQUEST_FAILED="failed",STAT_HTTP_RESOURCE_TOTAL_BYTES="bytes";
struct DependencyManager {template<class T> static QSharedPointer<T> get(){static auto value=QSharedPointer<T>::create();return value;}};
namespace NetworkingConstants { const QByteArray OVERTE_USER_AGENT="fixture"; }
class Reply : public QNetworkReply {
public:
    QByteArray body; qint64 offset{0};int reads{0};
    explicit Reply(const QNetworkRequest& request){setRequest(request);setUrl(request.url());open(QIODevice::ReadOnly);}
    void abort() override {}
    void complete(int status,QUrl finalURL,bool cached,bool redirect,QByteArray data){
        setUrl(finalURL);setAttribute(QNetworkRequest::HttpStatusCodeAttribute,status);
        setAttribute(QNetworkRequest::SourceIsFromCacheAttribute,cached);
        if(redirect){setAttribute(QNetworkRequest::RedirectionTargetAttribute,QUrl("https://other.invalid/next.js"));}
        setRawHeader("Content-Type","application/javascript");
        setRawHeader("Content-Range","bytes 0-3/100");
        body=data;setFinished(true);emit finished();
    }
    qint64 bytesAvailable()const override{return body.size()-offset+QNetworkReply::bytesAvailable();}
protected:
    qint64 readData(char* data,qint64 maximum)override{
        ++reads;auto count=qMin(maximum,body.size()-offset);if(count==0){return -1;}
        memcpy(data,body.constData()+offset,count);offset+=count;return count;
    }
};
// Capture transport seam: real Qt request/reply objects, no HTTP backend/wire.
struct NetworkAccessManager {
    QNetworkRequest captured;Reply* reply{nullptr};
    static NetworkAccessManager& getInstance(){static NetworkAccessManager value;return value;}
    QNetworkReply* get(const QNetworkRequest& request){captured=request;reply=new Reply(request);return reply;}
};
// ACTUAL_HEADER
// ACTUAL_SOURCE
int main(int argc,char**argv){
    QCoreApplication app(argc,argv);const QUrl source("https://fixture.invalid/source.js");
    for(int scenario=0;scenario!=11;++scenario){
        HTTPResourceRequest request(source);const bool strict=scenario!=0;request.setFailOnRedirect(strict);
        if(scenario==10){request._byteRange.toExclusive=4;}
        int finished=0;QObject::connect(&request,&ResourceRequest::finished,&app,[&]{++finished;});
        request.send();auto& transport=NetworkAccessManager::getInstance();
        assert(transport.captured.attribute(QNetworkRequest::RedirectPolicyAttribute).toInt()==
            int(strict?QNetworkRequest::ManualRedirectPolicy:QNetworkRequest::NoLessSafeRedirectPolicy));
        assert(transport.captured.attribute(QNetworkRequest::CacheLoadControlAttribute).toInt()==
            int(strict?QNetworkRequest::AlwaysNetwork:QNetworkRequest::PreferCache));
        if(strict){assert(!transport.captured.attribute(QNetworkRequest::CacheSaveControlAttribute).toBool());}
        int status=200;bool cached=false,redirect=false;QUrl finalURL=source;
        if(scenario>=2&&scenario<=6){int statuses[]={301,302,303,307,308};status=statuses[scenario-2];redirect=true;}
        if(scenario==7){finalURL=QUrl("https://other.invalid/changed.js");}
        if(scenario==8){cached=true;}
        if(scenario==9){status=304;}
        if(scenario==10){status=206;}
        auto* reply=transport.reply;reply->complete(status,finalURL,cached,redirect,"body");
        const bool accepted=scenario<=1||scenario==10;
        assert(finished==1&&request._state==ResourceRequest::Finished);
        assert(request.getResult()==(accepted?ResourceRequest::Success:ResourceRequest::RedirectFail));
        assert(request.getData()==(accepted?QByteArray("body"):QByteArray()));
        if(!accepted){assert(reply->reads==0);}
        if(scenario==10){assert(request._rangeRequestSuccessful&&request._totalSizeOfResource==100);}
        QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete);
    }
}
#include "test.moc"
