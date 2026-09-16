"""Original injector publication/finish bodies, real Qt locks, held buffer init."""
from pathlib import Path
import os,resource,shlex,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(Path(__file__).parents[1]/'lifecycle'))
from test_login_dialog_domain_receiver import block
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
baseline=os.environ.get('OVERTE_INJECTOR_BUFFER_BASELINE')
def read(path):
 return subprocess.check_output(['git','show',baseline+':'+path],cwd=ROOT,text=True) if baseline else (ROOT/path).read_text()
source=read('libraries/audio/src/AudioInjector.cpp');header=read('libraries/audio/src/AudioInjector.h')
methods='\n'.join(block(source,marker) for marker in ('bool AudioInjector::injectLocally(', 'void AudioInjector::finish('))
getter=block(header,'QSharedPointer<AudioInjectorLocalBuffer> getLocalBuffer(')
fixture=r'''
#include <QObject>
#include <QCoreApplication>
#include <QSharedPointer>
#include <QEnableSharedFromThis>
#include <QIODevice>
#include <QDebug>
#include <QLoggingCategory>
#include <future>
#include <atomic>
#include <cassert>
#include "libraries/shared/src/shared/ReadWriteLockable.h"
Q_LOGGING_CATEGORY(audio,"overte.test.injector")
struct Data { int getNumBytes()const{return 8;} };
using AudioDataPointer=QSharedPointer<Data>;
std::atomic<bool> hold{false};
std::promise<void> entered,release;
std::shared_future<void> released{release.get_future()};
struct AudioInjectorLocalBuffer:QObject {
    explicit AudioInjectorLocalBuffer(AudioDataPointer) {}
    bool opened=false,loop=false;int offset=-1;
    bool open(QIODevice::OpenMode) {
        if(hold.exchange(false)){entered.set_value();released.wait();}
        opened=true;return true;
    }
    void setShouldLoop(bool value){loop=value;}
    void setCurrentOffset(int value){offset=value;}
};
struct AudioInjector;
struct AudioInterface {
    bool outputLocalInjector(const QSharedPointer<AudioInjector>&){return true;}
};
enum class AudioInjectorState { LocalInjectionFinished=1,NetworkInjectionFinished=2,Finished=4 };
AudioInjectorState& operator|=(AudioInjectorState& a,AudioInjectorState b){return a=AudioInjectorState(int(a)|int(b));}
struct AudioInjector:QObject,QEnableSharedFromThis<AudioInjector>,ReadWriteLockable {
    AudioDataPointer _audioData{new Data};
    struct Options{bool loop=true;} _options;
    int _currentSendOffset=4;
    AudioInjectorState _state{};
    AudioInterface interface;
    AudioInterface* _localAudioInterface=&interface;
    QSharedPointer<AudioInjectorLocalBuffer> _localBuffer;
    std::function<void()> onFinished;
    void finished(){if(onFinished)onFinished();}
    auto getOptions()const{return resultWithReadLock<Options>([&]{return _options;});}
    /* GETTER */
    bool injectLocally();
    void finish();
};
/* METHODS */
int main(int argc,char**argv){
    QCoreApplication app(argc,argv);
    auto injector=QSharedPointer<AudioInjector>::create();
    assert(injector->injectLocally());
    auto old=injector->getLocalBuffer();assert(old&&old->opened&&old->offset==4&&old->loop);
    // A direct finished receiver starts a replacement before finish returns.
    injector->onFinished=[&]{assert(injector->injectLocally());};
    injector->finish();
    auto current=injector->getLocalBuffer();assert(current&&current!=old);
    assert(old->opened); // outstanding mixer references remain valid
    injector->onFinished={};
    hold=true;
    auto pending=std::async(std::launch::async,[&]{return injector->injectLocally();});
    entered.get_future().wait();
    auto during=injector->getLocalBuffer();assert(during==current&&during->opened);
    release.set_value();assert(pending.get());
    auto after=injector->getLocalBuffer();assert(after!=current&&after->opened&&after->offset==4);
    injector->finish();assert(!injector->getLocalBuffer());
}
'''
flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
with tempfile.TemporaryDirectory(prefix='overte-injector-buffer-') as scratch:
 p=Path(scratch)
 (p/'test.cpp').write_text(fixture.replace('/* GETTER */',getter).replace('/* METHODS */',methods))
 subprocess.run(['c++','-std=c++17','-fPIC','-pthread','-I'+str(ROOT),str(p/'test.cpp'),'-o',str(p/'test'),*flags],check=True,timeout=30)
 result=subprocess.run([str(p/'test')],capture_output=True,text=True,timeout=5)
 if baseline:
  assert result.returncode!=0 and 'current&&current!=old' in result.stderr,result
  print('EXPECTED BASELINE FAILURE: finish clears the reentrant replacement buffer')
 else:
  assert result.returncode==0,result.stderr
  print('PASS actual injector: reentrant restart survives, old readers retain ownership, complete initialization precedes publication')
