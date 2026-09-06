// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QObject>
#include <QThread>
#include <QHash>
#include <QSharedPointer>
#include <QDebug>
#include <memory>
#include <functional>
#include <cassert>
#include <atomic>
#include <thread>
#define PROFILE_RANGE(...)
#define qCDebug(...) qDebug()
#define qCWarning(...) qWarning()
using EntityItemID=QString;
#include "structs.inc"
struct ScriptEngines { bool isStopped() const {return false;} };
struct EntityScriptDetails {QString scriptText,definingSandboxURL;int status;};
struct EntityScriptStatus {enum {PENDING,LOADING};};
struct ScriptCache {
 using Callback=std::function<void(const QString&,const QString&,bool,bool,const QString&)>;
 QVector<Callback> pending;
 void getScriptContents(const QString&,Callback cb,bool){pending.push_back(cb);}
 void deliver(int n,QString text){pending[n]("resolved-url",text,true,true,"OK");}
};
static QSharedPointer<ScriptCache> cache=QSharedPointer<ScriptCache>::create();
struct DependencyManager {template<class T>static QSharedPointer<T> get(){return cache;}};
struct ScriptManager:QObject,std::enable_shared_from_this<ScriptManager>{
 QSharedPointer<ScriptEngines> _scriptEngines=QSharedPointer<ScriptEngines>::create();
 bool _isFinished=false,stopping=false,deny=false;QString currentSandboxURL;
 EntityScriptContentAvailableMap _contentAvailableQueue;
 QHash<EntityItemID,QHash<QString,std::shared_ptr<EntityScriptLoadRequest>>> _entityScriptLoads;
 QStringList consumed;std::function<void()> onDetails,onConsume;
 bool isStopping()const{return stopping;}
 bool hasEntityScriptDetails(const EntityItemID&,const QString&)const{return false;}
 bool rejectEntityScriptWithoutConsent(const EntityItemID&,const QString&){return deny;}
 void updateEntityScriptStatus(const EntityItemID&,const QString&,int,const QString&){if(onDetails){auto f=std::move(onDetails);onDetails={};f();}}
 void setEntityScriptDetails(const EntityItemID&,const QString&,const EntityScriptDetails&){}
 void entityScriptContentAvailable(const EntityItemID&,const QString&,const QString& contents,bool,bool,const QString&){consumed<<contents;if(onConsume){auto f=std::move(onConsume);onConsume={};f();}}
 bool isCurrentEntityScriptLoad(const EntityItemID&,const QString&,const std::shared_ptr<EntityScriptLoadRequest>&)const;
 void cancelEntityScriptLoad(const EntityItemID&,const QString&);
 void processEntityScriptContents();
 void loadEntityScript(const EntityItemID&,const QString&,bool=false);
 void executeOnScriptThread(std::function<void()>,const Qt::ConnectionType& =Qt::AutoConnection);
 void unloadEntityScript(const EntityItemID&,const QString&,bool=false);
 void unloadAllEntityScriptsForEntity(const EntityItemID&,bool=false);
 void unloadAllEntityScripts(bool=false);
};
#include "production.inc"
int main(int argc,char**argv){
 QCoreApplication app(argc,argv);auto m=std::make_shared<ScriptManager>();
 auto deliver=[&](int n,const char* text){cache->deliver(n,text);};
 m->loadEntityScript("entity","one");m->loadEntityScript("entity","one");
 deliver(1,"new");deliver(0,"stale");deliver(1,"duplicate");m->processEntityScriptContents();assert(m->consumed==QStringList{"new"});
 m->loadEntityScript("entity","one");m->unloadEntityScript("entity","one");deliver(2,"unloaded");m->processEntityScriptContents();assert(m->consumed.size()==1);
 m->loadEntityScript("entity","one");m->loadEntityScript("entity","two");deliver(3,"one");deliver(4,"two");m->processEntityScriptContents();assert(m->consumed.contains("one")&&m->consumed.contains("two")&&m->consumed.size()==3);
 m->loadEntityScript("entity","one");deliver(5,"queued-before-unload");m->unloadAllEntityScriptsForEntity("entity");m->processEntityScriptContents();assert(m->consumed.size()==3);
 m->loadEntityScript("entity","one");m->loadEntityScript("other","two");deliver(6,"pending-one");deliver(7,"pending-two");m->onConsume=[&]{m->unloadAllEntityScripts();};m->processEntityScriptContents();assert(m->consumed.size()==4); // other swapped-out response must be invalidated
 m->onDetails=[&]{m->loadEntityScript("entity","one");};int before=cache->pending.size();m->loadEntityScript("entity","one");assert(cache->pending.size()==before+1);deliver(before,"reentrant-new");m->processEntityScriptContents();assert(m->consumed.last()=="reentrant-new");
 m->loadEntityScript("entity","one");int held=cache->pending.size()-1;std::thread worker([&]{deliver(held,"cross-thread-stale");});worker.join();m->unloadEntityScript("entity","one");QCoreApplication::processEvents();m->processEntityScriptContents();assert(m->consumed.last()=="reentrant-new");
 m->loadEntityScript("entity","one");deliver(cache->pending.size()-1,"stopping");m->stopping=true;m->processEntityScriptContents();assert(m->consumed.last()=="reentrant-new");
 m->stopping=false;m->deny=true;before=cache->pending.size();m->loadEntityScript("entity","one");assert(cache->pending.size()==before);
 m->deny=false;m->loadEntityScript("entity","one");held=cache->pending.size()-1;m.reset();deliver(held,"destroyed");
}
