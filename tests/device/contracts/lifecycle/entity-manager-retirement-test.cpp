// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QThread>
#include <QPointer>
#include <QSharedPointer>
#include <QElapsedTimer>
#include <QtConcurrent>
#include <atomic>
#include <cassert>
#include <memory>
#include <string>
struct Observations {
 std::atomic<bool> entered{false},stopped{false},done{false},unloaded{false},removed{false};
 std::atomic<int> disconnects{0};
};
struct ScriptManager;
struct ScriptEngines {
 Observations& o;
 explicit ScriptEngines(Observations& state):o(state){}
 void removeScriptEngine(const std::shared_ptr<ScriptManager>&){assert(o.unloaded&&o.disconnects==1);o.removed=true;}
};
// Explicit engine/registry seam; cross-thread blocking cleanup and ownership are real Qt.
struct ScriptManager:QObject, std::enable_shared_from_this<ScriptManager> {
 QWeakPointer<ScriptEngines> _scriptEngines;
 Observations& o;
 explicit ScriptManager(Observations& state):o(state){}
 void stop(){o.stopped=true;}
 void waitTillDoneRunning(){stop();while(!o.done)QThread::msleep(1);}
 void unloadAllEntityScripts(bool blocking){assert(blocking);QMetaObject::invokeMethod(this,[this]{assert(o.done);o.unloaded=true;},Qt::BlockingQueuedConnection);}
 void disconnectNonEssentialSignals(){assert(o.unloaded);++o.disconnects;}
 void removeFromScriptEngines();
};
using ScriptManagerPointer=std::shared_ptr<ScriptManager>;
struct EntityTreeRenderer {
 ScriptManagerPointer _persistentEntitiesScriptManager,_nonPersistentEntitiesScriptManager;
 void resetPersistentEntitiesScriptEngine();void resetNonPersistentEntitiesScriptEngine();void shutdownManagers();
};
#include "retirement.inc"
int main(int argc,char**argv){
 QCoreApplication app(argc,argv);assert(argc==2);std::string mode=argv[1];EntityTreeRenderer renderer;
 if(mode=="empty"){renderer.resetPersistentEntitiesScriptEngine();renderer.resetNonPersistentEntitiesScriptEngine();renderer.shutdownManagers();return 0;}
 Observations state;QThread worker;auto manager=ScriptManagerPointer(new ScriptManager(state),[](ScriptManager* p){p->deleteLater();});QPointer<ScriptManager> observed(manager.get());manager->moveToThread(&worker);
 auto registry=QSharedPointer<ScriptEngines>::create(state);manager->_scriptEngines=registry;if(mode=="registry-expired")registry.reset();
 QObject::connect(manager.get(),&QObject::destroyed,&worker,&QThread::quit,Qt::DirectConnection);
 auto raw=manager.get();QMetaObject::invokeMethod(raw,[raw,&state,mode]{state.entered=true;if(mode!="already-done")while(!state.stopped)QThread::msleep(1);state.done=true;},Qt::QueuedConnection);worker.start();
 QElapsedTimer deadline;deadline.start();while(!state.entered&&deadline.elapsed()<1000)QThread::msleep(1);assert(state.entered);
 if(mode=="nonpersistent"||mode=="shutdown-nonpersistent")renderer._nonPersistentEntitiesScriptManager=std::move(manager);else renderer._persistentEntitiesScriptManager=std::move(manager);
 if(mode=="shutdown"||mode=="shutdown-nonpersistent")renderer.shutdownManagers();else if(mode=="nonpersistent")renderer.resetNonPersistentEntitiesScriptEngine();else renderer.resetPersistentEntitiesScriptEngine();
 assert(!renderer._persistentEntitiesScriptManager&&!renderer._nonPersistentEntitiesScriptManager);assert(state.stopped);
 while(state.disconnects==0&&deadline.elapsed()<2000){QCoreApplication::processEvents();QThread::msleep(1);}assert(state.done&&state.unloaded);
 assert(worker.wait(1000));assert(observed.isNull());assert(state.removed==(mode!="registry-expired"));
}
