"""Actual injector scheduler and local completion caller on a real Qt thread."""
from pathlib import Path
import os,shlex,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(Path(__file__).parents[1]/'lifecycle'))
from test_login_dialog_domain_receiver import block
baseline=os.environ.get('OVERTE_INJECTOR_EVENT_BASELINE')
def read(path):
 return subprocess.check_output(['git','show',baseline+':'+path],cwd=ROOT,text=True) if baseline else (ROOT/path).read_text()
manager=read('libraries/audio/src/AudioInjectorManager.cpp')
notify=(block(manager,'void AudioInjectorManager::notifyInjectorReadyCondition(') if not baseline else
        block(read('libraries/audio/src/AudioInjectorManager.h'),'void notifyInjectorReadyCondition(').replace('void notifyInjectorReadyCondition','void AudioInjectorManager::notifyInjectorReadyCondition'))
methods=block(manager,'AudioInjectorManager::~AudioInjectorManager(')+'\n'+block(manager,'void AudioInjectorManager::run(')+'\n'+notify+'\n'+block(read('libraries/audio/src/AudioInjector.cpp'),'void AudioInjector::finishLocalInjection(')
fixture=r'''
#include <QCoreApplication>
#include <QThread>
#include <QSharedPointer>
#include <QObject>
#include <atomic>
#include <condition_variable>
#include <mutex>
#include <queue>
#include <future>
#include <chrono>
#include <cassert>
#include <iostream>
#include "libraries/shared/src/shared/ReadWriteLockable.h"
uint64_t usecTimestampNow(){return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
struct AudioInjectorManager;
AudioInjectorManager* instance=nullptr;
struct DependencyManager{template<class T> static T* get(){return instance;}};
enum class AudioInjectorState{LocalInjectionFinished=1,NetworkInjectionFinished=2};
AudioInjectorState& operator|=(AudioInjectorState& a,AudioInjectorState b){return a=AudioInjectorState(int(a)|int(b));}
struct AudioInjector:QObject,ReadWriteLockable{
 Q_OBJECT
public:
 AudioInjectorState _state{};
 struct {bool localOnly=true;} _options;
 std::promise<void> completed;
 bool stateHas(AudioInjectorState)const{return false;}
 std::function<void()> onFinished;
 void finish(){assert(QThread::currentThread()==thread());completed.set_value();if(onFinished)onFinished();}
 std::promise<void> networkFrame;
 int64_t injectNextFrame(){networkFrame.set_value();return -1;}
 bool isFinished(){return true;}
 void sendStopInjectorPacket(){}
public slots:
 void finishLocalInjection();
};
using AudioInjectorPointer=QSharedPointer<AudioInjector>;
struct AudioInjectorManager:QObject{
 using Lock=std::unique_lock<std::mutex>;
 using TimeInjectorPointerPair=std::pair<uint64_t,AudioInjectorPointer>;
 struct Greater{bool operator()(const TimeInjectorPointerPair&a,const TimeInjectorPointerPair&b)const{return a.first>b.first;}};
 using InjectorQueue=std::priority_queue<TimeInjectorPointerPair,std::deque<TimeInjectorPointerPair>,Greater>;
 InjectorQueue _injectors;
 QThread* _thread=nullptr;
 ~AudioInjectorManager();
 std::mutex _injectorsMutex;
 std::condition_variable _injectorReady;
 std::atomic<bool> _shouldStop{false};
 bool _pendingEvents=false;
 void run();
 void notifyInjectorReadyCondition();
};
/* METHODS */
int main(int argc,char**argv){
 QCoreApplication app(argc,argv);
 if(argc>1 && QString::fromLocal8Bit(argv[1])=="teardown"){
  auto manager=new AudioInjectorManager;instance=manager;
  auto injector=AudioInjectorPointer::create();
  injector->onFinished=[&]{manager->notifyInjectorReadyCondition();};
  manager->_injectors.emplace(0,injector);
  delete manager;
  std::cout<<"teardown-reentrancy-safe"<<std::endl;return 0;
 }
 QThread worker;AudioInjectorManager manager;instance=&manager;
 AudioInjector injector;
 manager.moveToThread(&worker);injector.moveToThread(&worker);
 QObject::connect(&worker,&QThread::started,&manager,[&]{manager.run();},Qt::DirectConnection);
 AudioInjectorPointer network;
 std::future<void> networkDone;
 if(argc>1){
  network=AudioInjectorPointer::create();network->moveToThread(&worker);
  networkDone=network->networkFrame.get_future();
  manager._injectors.emplace(usecTimestampNow()+100000,network);
 }
 auto completed=injector.completed.get_future();
 // A local-only sound finishes before the scheduler reaches its first wait.
 // The Qt event and its wake must both survive that ordering.
 injector.finishLocalInjection();
 worker.start();
 const bool delivered=completed.wait_for(std::chrono::seconds(2))==std::future_status::ready;
 const bool networkDelivered=!network || networkDone.wait_for(std::chrono::seconds(2))==std::future_status::ready;
 manager._shouldStop=true;manager._injectorReady.notify_one();worker.quit();
 assert(worker.wait(2000));
 std::cout<<(delivered?"completion-delivered":"completion-not-delivered")<<std::endl;
 return delivered&&networkDelivered?0:2;
}
#include "test.moc"
'''
flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
moc=Path(subprocess.check_output(['pkg-config','--variable=libexecdir','Qt6Core'],text=True).strip())/'moc'
with tempfile.TemporaryDirectory(prefix='overte-injector-events-') as scratch:
 p=Path(scratch);(p/'test.cpp').write_text(fixture.replace('/* METHODS */',methods))
 subprocess.run([str(moc),str(p/'test.cpp'),'-o',str(p/'test.moc')],check=True,timeout=15)
 subprocess.run(['c++','-std=c++17','-fPIC','-pthread','-I'+str(ROOT),str(p/'test.cpp'),'-o',str(p/'test'),*flags],check=True,timeout=30)
 teardown=subprocess.run([str(p/'test'),'teardown'],capture_output=True,text=True,timeout=5)
 assert teardown.returncode==0 and 'teardown-reentrancy-safe' in teardown.stdout,teardown
 network=subprocess.run([str(p/'test'),'network'],capture_output=True,text=True,timeout=6)
 assert network.returncode==0,network
 result=subprocess.run([str(p/'test')],capture_output=True,text=True,timeout=6)
 if baseline:
  assert result.returncode==2 and 'completion-not-delivered' in result.stdout,result
  print('EXPECTED BASELINE FAILURE: local completion remains queued without a network injector')
 else:
  assert result.returncode==0 and 'completion-delivered' in result.stdout,result
  print('PASS actual scheduler/caller: local completion delivered, pre-wait notification retained, idle shutdown drains')
