// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QPointer>
#include <QJsonDocument>
#include <QJsonObject>
#include <QVariantMap>
#include <QStack>
#include <QUrl>
#include <QUrlQuery>
#include <QRegularExpression>
#include <functional>
#include <QUuid>
#include <QLoggingCategory>
#include <cassert>
#include <cstring>
#include "libraries/networking/src/RequestCancellation.h"
#include "security/redaction/SafeDiagnostics.h"
Q_LOGGING_CATEGORY(networking,"address-lifetime-test")
Q_LOGGING_CATEGORY(networking_ice,"address-lifetime-ice-test")
const QString URL_SCHEME_OVERTE="hifi",DATA_OBJECT_DOMAIN_KEY="domain",INDEX_PATH="/";
const char OVERRIDE_PATH_KEY[]="override_path",LOOKUP_TRIGGER_KEY[]="lookup_trigger";
constexpr quint16 DEFAULT_DOMAIN_SERVER_PORT=40102;
struct LimitedNodeList {enum class ConnectionStep {HandleAddress,LookupAddress};};
struct DomainHandler {bool isInErrorState()const{return false;}};
struct NodeList {void flagTimeForConnectionStep(LimitedNodeList::ConnectionStep){} DomainHandler& getDomainHandler(){static DomainHandler d;return d;}};
struct DependencyManager {template<class T>static T* get(){static T t;return &t;}};
#ifdef OVERTE_ADDRESS_QREGEXP_ADAPTER
// Test-only Qt6 adapter for unchanged Main QRegExp parsing. Apple compiles its
// actual QRegularExpression path. This is not native Qt5 regex acceptance.
class QRegExp:public QRegularExpression {
 mutable QRegularExpressionMatch last;
public:
 QRegExp(const QString& p,Qt::CaseSensitivity cs=Qt::CaseSensitive):QRegularExpression(p,cs==Qt::CaseInsensitive?CaseInsensitiveOption:NoPatternOption){}
 bool exactMatch(const QString& s)const{return QRegularExpression(anchoredPattern(pattern()),patternOptions()).match(s).hasMatch();}
 int indexIn(const QString& s)const{last=match(s);return last.hasMatch()?last.capturedStart():-1;}
 QString cap(int n)const{return last.captured(n);}
};
#endif
const QString HIFI_URL_SCHEME_FILE="file",HIFI_URL_SCHEME_HTTPS="https",HIFI_URL_SCHEME_HTTP="http",DOMAIN_SPAWNING_POINT="/spawn",DEFAULT_NAMED_PATH="/";
struct UserActivityLogger {
 std::function<void()> hook;
 static UserActivityLogger& getInstance(){static UserActivityLogger logger;return logger;}
 void wentTo(int,const QString&,const QString&){if(hook){auto f=std::move(hook);hook={};f();}}
};
class Reply:public QNetworkReply {
 QByteArray bytes;
public:
 Reply(QByteArray payload={},bool missing=false):bytes(payload){open(QIODevice::ReadOnly);if(missing)setError(ContentNotFoundError,"missing");}
 void abort()override{}
 qint64 readData(char* out,qint64 max)override{auto n=qMin<qint64>(max,bytes.size());std::memcpy(out,bytes.data(),n);bytes.remove(0,n);return n;}
};
class AddressManager:public QObject {
 Q_OBJECT
public:
 enum LookupTrigger {UserInput,Internal,AttemptedRefresh,VisitUserFromPAL,StartupFromSettings,DomainPathResponse,Back,Forward,Suggestions};
 overte::network::RequestScope _lookupRequests;
 QUrl _domainURL{"hifi://original.test"},_previousAPILookup{"hifi://pending.test"};
 bool _clientLookupPolicy=false,_lookupForeground=true,_lookupNeedsExplicitIntent=false;
 QUrl _lastVisitedURL;
 std::function<void()> userHook,pathHook;
 int users=0,places=0,domains=0;
 bool handleUrl(const QUrl&,LookupTrigger,const QString& =QString());
 bool handleNetworkAddress(const QString&,LookupTrigger,bool&);
 bool handleUsername(const QString&,const QUrl&,LookupTrigger);
 bool handleDomainID(const QString& s){return !QUuid(s).isNull();}
 void goToUser(const QString&){++users;_lookupRequests.next();if(userHook){auto f=std::move(userHook);userHook={};f();}}
 void attemptDomainIDLookup(const QString&,const QString&,LookupTrigger){++domains;_lookupRequests.next();}
 void attemptPlaceNameLookup(const QString&,const QString&,LookupTrigger){++places;_lookupRequests.next();}
 QString _shareablePlaceName,_newHostLookupPath;QUuid _rootPlaceID;QStack<QUrl> _backStack,_forwardStack;int paths=0;
 QUrl currentAddress()const{return _domainURL;}
 void handleAPIResponse(QNetworkReply*);void goToAddressFromObject(const QVariantMap&,const QNetworkReply*);void handleAPIError(QNetworkReply*);
 bool setHost(const QString&,LookupTrigger,quint16=0);bool setDomainInfo(const QUrl&,LookupTrigger);void addCurrentAddressToHistory(LookupTrigger);
 void handlePath(const QString&,LookupTrigger,bool=false){++paths;if(pathHook){auto f=std::move(pathHook);pathHook={};f();}}
 bool handleViewpoint(const QString&,bool,LookupTrigger){++paths;return true;}
signals:
 void possibleDomainChangeRequired(const QUrl&,const QUuid&);
 void possibleDomainChangeRequiredViaICEForID(const QString&,const QUuid&);
 void hostChanged(const QString&);void lookupResultsFinished();void lookupResultIsOffline();void lookupResultIsNotFound();void pathChangeRequired(const QString&);void goForwardPossible(bool);void goBackPossible(bool);
};
#include "address-reentrancy-test.moc"
#include "production.inc"
QByteArray payload(bool ice=false){QJsonObject domain{{"id","11111111-1111-1111-1111-111111111111"}};domain.insert(ice?"ice_server_address":"network_address","server.test");return QJsonDocument(QJsonObject{{"data",QJsonObject{{"place",QJsonObject{{"id","22222222-2222-2222-2222-222222222222"},{"name","oldplace"},{"domain",domain},{"path","/position"}}}}}}).toJson();}
int main(int argc,char**argv){
 QCoreApplication app(argc,argv);
 for(bool ice:{false,true}){
  AddressManager m;Reply r(payload(ice));int finish=0;QObject::connect(&m,&AddressManager::lookupResultsFinished,[&]{++finish;});auto supersede=[&]{m._lookupRequests.next();m._domainURL=QUrl("hifi://newplace.test");};
  if(ice)QObject::connect(&m,&AddressManager::possibleDomainChangeRequiredViaICEForID,supersede);else QObject::connect(&m,&AddressManager::possibleDomainChangeRequired,supersede);
  m.handleAPIResponse(&r);assert(m._domainURL.host()=="newplace.test"&&m._rootPlaceID.isNull()&&m.paths==0&&finish==0);
 }
 {AddressManager m;auto r=new Reply(payload());QObject::connect(&m,&AddressManager::possibleDomainChangeRequired,[&]{delete r;r=nullptr;});m.handleAPIResponse(r);assert(!r&&m._rootPlaceID.isNull()&&m.paths==0);}
 {AddressManager m;Reply r(payload());int finish=0;QObject::connect(&m,&AddressManager::hostChanged,[&]{m._lookupRequests.next();m._domainURL=QUrl("hifi://newplace.test");});QObject::connect(&m,&AddressManager::lookupResultsFinished,[&]{++finish;});m.handleAPIResponse(&r);assert(m.paths==0&&finish==0&&m._domainURL.host()=="newplace.test");}
 {AddressManager m;Reply r({},true);int finish=0;QObject::connect(&m,&AddressManager::lookupResultIsNotFound,[&]{m._lookupRequests.next();m._previousAPILookup=QUrl("hifi://newplace.test");});QObject::connect(&m,&AddressManager::lookupResultsFinished,[&]{++finish;});m.handleAPIError(&r);assert(finish==0&&!m._previousAPILookup.isEmpty());}
 for(bool direct:{false,true}){AddressManager m;QObject::connect(&m,&AddressManager::goForwardPossible,[&]{m._lookupRequests.next();m._domainURL=QUrl("hifi://newplace.test");});bool changed=direct?m.setDomainInfo(QUrl("hifi://oldplace.test"),AddressManager::UserInput):m.setHost("oldplace.test",AddressManager::UserInput);assert(!changed&&m._domainURL.host()=="newplace.test"&&m._backStack.isEmpty());}
 {AddressManager m;int domains=0;QObject::connect(&m,&AddressManager::hostChanged,[&]{m._lookupRequests.next();});QObject::connect(&m,&AddressManager::possibleDomainChangeRequired,[&]{++domains;});assert(!m.setDomainInfo(QUrl("hifi://oldplace.test"),AddressManager::UserInput));assert(domains==0);}
 {AddressManager m;Reply r(payload());int finish=0;QObject::connect(&m,&AddressManager::lookupResultsFinished,[&]{++finish;});m.handleAPIResponse(&r);assert(finish==1&&m.paths==1&&m._domainURL.host()=="oldplace"&&!m._rootPlaceID.isNull()&&m._backStack.size()==1);}
 {AddressManager m;Reply r(payload());auto ticket=m._lookupRequests.next();r.setProperty("_overte_request_ticket",QVariant::fromValue(ticket));m._lookupRequests.next();m.handleAPIResponse(&r);assert(m.paths==0&&m._rootPlaceID.isNull());}
#ifdef OVERTE_ADDRESS_ENTRY_TEST
 for(auto signal:{0,1}){AddressManager m;int finish=0;auto jump=[&]{m._lookupRequests.next();m._domainURL=QUrl("hifi://newplace.test");};if(signal==0)QObject::connect(&m,&AddressManager::hostChanged,jump);else QObject::connect(&m,&AddressManager::lookupResultsFinished,jump);QObject::connect(&m,&AddressManager::lookupResultsFinished,[&]{++finish;});assert(m.handleUrl(QUrl("https://old.test/world?location=/old"),AddressManager::UserInput));assert(m.paths==0&&m._domainURL.host()=="newplace.test");assert(finish==(signal==0?0:1));}
 {AddressManager m;int finish=0;m.pathHook=[&]{m._lookupRequests.next();};QObject::connect(&m,&AddressManager::lookupResultsFinished,[&]{++finish;});assert(m.handleUrl(QUrl("/old/path"),AddressManager::UserInput));assert(m.paths==1&&finish==0);}
 for(QString host:{"127.0.0.1","old.test"}){AddressManager m;QObject::connect(&m,&AddressManager::lookupResultsFinished,[&]{m._lookupRequests.next();m._domainURL=QUrl("hifi://newplace.test");});assert(m.handleUrl(QUrl("hifi://"+host+"/old"),AddressManager::UserInput));assert(m.paths==0&&m._domainURL.host()=="newplace.test"&&m._lastVisitedURL.isEmpty());}
 {AddressManager m;m.userHook=[&]{m._lookupRequests.next();m._lastVisitedURL=QUrl("hifi://newplace.test");m._previousAPILookup=m._lastVisitedURL;};assert(m.handleUrl(QUrl("hifi://@someone"),AddressManager::UserInput));assert(m.users==1&&m._lastVisitedURL.host()=="newplace.test"&&m._previousAPILookup==m._lastVisitedURL);}
 {AddressManager m;UserActivityLogger::getInstance().hook=[&]{m._lookupRequests.next();m._lastVisitedURL=QUrl("hifi://newplace.test");};assert(m.handleUrl(QUrl("hifi://placename"),AddressManager::UserInput));assert(m.places==0&&m._lastVisitedURL.host()=="newplace.test");}
 for(auto input:{"hifi://127.0.0.1/normal","hifi://normal.test/normal","https://normal.test/world","file:///normal/world","/normal"}){AddressManager m;assert(m.handleUrl(QUrl(input),AddressManager::UserInput));assert(m.paths==1);}
 {AddressManager m;assert(m.handleUrl(QUrl("hifi://@someone"),AddressManager::UserInput));assert(m.users==1&&m._lastVisitedURL==QUrl("hifi://@someone"));}
 {AddressManager m;assert(m.handleUrl(QUrl("hifi://11111111-1111-1111-1111-111111111111"),AddressManager::UserInput));assert(m.domains==1);}
 {AddressManager m;assert(m.handleUrl(QUrl("hifi://placename"),AddressManager::UserInput));assert(m.places==1);}
 {AddressManager m;m._clientLookupPolicy=true;m._lookupForeground=false;assert(!m.handleUrl(QUrl("https://normal.test/world"),AddressManager::UserInput));m._lookupForeground=true;m._lookupNeedsExplicitIntent=true;assert(!m.handleUrl(QUrl("https://normal.test/world"),AddressManager::AttemptedRefresh));assert(m.handleUrl(QUrl("https://normal.test/world"),AddressManager::UserInput));assert(!m._lookupNeedsExplicitIntent&&m.paths==1);}
#endif

}
