"""Execute the actual Phone header probe with Qt lifecycle and controlled cache seams."""
from pathlib import Path
import shlex
import resource
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


def driver():
    source = (ROOT / 'libraries/material-networking/src/material-networking/TextureCache.cpp').read_text()
    start = source.index('void NetworkTexture::probeInitialKtxCache()')
    method = source[start:source.index('\n}', start) + 2]
    return r'''
#include <QCoreApplication>
#include <QPointer>
#include <QSharedPointer>
#include <QUrl>
#include <QElapsedTimer>
#include <QCryptographicHash>
#include <QThread>
#include <algorithm>
#include <cassert>
#include <cstring>
#include <functional>
#include <memory>
#include <stdexcept>
#include <thread>
#include <vector>
#define PHONE_LOADING(...) do {} while(false)
#define PROFILE_ASYNC_END(...) do {} while(false)
namespace glm { struct ivec2 { int x=0,y=0; }; }
namespace ktx {
using Byte=unsigned char;
struct Header {
    Byte identifier[12]{};
    uint32_t endianness=0x04030201, bytesOfKeyValueData=0, levels=3;
    static constexpr uint32_t ENDIAN_TEST=0x04030201;
    uint32_t getNumberOfLevels() const {return levels;}
    std::vector<int> generateImageDescriptors() const {return levels ? std::vector<int>{1} : std::vector<int>{};}
};
constexpr size_t KTX_HEADER_SIZE=sizeof(Header);
bool checkIdentifier(const Byte* p) {return p[0]==42;}
struct KeyValue {std::string _key; std::vector<Byte> _value;};
using KeyValues=std::vector<KeyValue>;
struct KTX {static KeyValues parseKeyValues(size_t n,const Byte* p) {
    KeyValues out;
    for(size_t off=0;off<n;) {
        uint32_t length; std::memcpy(&length,p+off,4);
        const char* key=reinterpret_cast<const char*>(p+off+4);
        size_t kl=std::strlen(key);
        out.push_back({std::string(key),std::vector<Byte>(p+off+4+kl+1,p+off+4+length)});
        off+=4+((length+3)&~3u);
    }
    return out;
}};
struct KTXDescriptor {KTXDescriptor(const Header&,const KeyValues&,const std::vector<int>&){}};
}
struct File {bool valid=true;};
namespace gpu {
const std::string SOURCE_HASH_KEY="hash";
constexpr int SOURCE_HASH_BYTES=16;
struct Texture;
using TexturePointer=std::shared_ptr<Texture>;
struct Texture {
    int min=0; std::string src;
    int minAvailableMipLevel() const {return min;}
    const std::string& source() const {return src;}
    void setSource(const std::string& s){src=s;}
    static std::pair<TexturePointer,glm::ivec2> unserialize(std::shared_ptr<File>);
};
}
int releases=0, tails=0, images=0, failures=0, parses=0;
bool throwCache=false, tailCreationFails=false;
std::function<void()> onComplete;
std::shared_ptr<File> disk;
gpu::TexturePointer memoryTexture, diskTexture;
std::thread::id owner;
struct FakeFileCache {std::shared_ptr<File> getFile(const std::string&) {assert(std::this_thread::get_id()!=owner); return disk;}};
struct TextureCache {
    std::shared_ptr<FakeFileCache> _ktxCache=std::make_shared<FakeFileCache>();
    std::pair<gpu::TexturePointer,glm::ivec2> getTextureByHash(const std::string&) {
        assert(std::this_thread::get_id()!=owner); if(throwCache)throw std::runtime_error("cache failure");return {memoryTexture,{12,8}};
    }
    std::pair<gpu::TexturePointer,glm::ivec2> cacheTextureByHash(const std::string&,std::pair<gpu::TexturePointer,glm::ivec2> p){return p;}
    template<class T> static void requestCompleted(const T&){assert(std::this_thread::get_id()==owner);++releases;if(onComplete){auto callback=std::move(onComplete);onComplete={};callback();}}
};
std::pair<gpu::TexturePointer,glm::ivec2> gpu::Texture::unserialize(std::shared_ptr<File> f) {
    assert(std::this_thread::get_id()!=owner);++parses;return {f->valid?diskTexture:nullptr,{12,8}};
}
struct StatTracker {int pending=0;void incrementStat(const char*){++pending;}void decrementStat(const char*){--pending;}};
struct CounterStat {CounterStat(const char*){}};
struct DependencyManager {template<class T>static std::shared_ptr<T> get(){static auto p=std::make_shared<T>();return p;}};
std::vector<std::function<void()>> work;
struct ProbePoolSeam {bool stopping=false;bool isStopping()const{return stopping;}};
ProbePoolSeam probePool;
ProbePoolSeam& phoneKtxProbePool(){return probePool;}
bool queuePhoneKtxProbeTask(std::function<void()> f,const QUrl&){if(probePool.stopping)return false;work.push_back(std::move(f));return true;}
class ResourceRequest:public QObject {
public:
    enum Result {Success,Error}; Result result=Success; QByteArray data;
    Result getResult()const{return result;}QByteArray getData()const{return data;}
};
class Resource:public QObject {
public:
    void handleFailedRequest(ResourceRequest::Result){++failures;}
};
class NetworkTexture:public Resource {
public:
    enum ResourceType {KTX,OTHER};
    enum State {LOADING_INITIAL_DATA,WAITING_FOR_MIP_REQUEST,FAILED_TO_LOAD};
    static constexpr int NULL_MIP_LEVEL=65535;
    QWeakPointer<Resource> _self;
    ResourceRequest* _ktxHeaderRequest=nullptr;ResourceRequest* _ktxMipRequest=nullptr;
    QUrl _activeUrl{"https://fixture.invalid/image.ktx"},_url{"https://fixture.invalid/image.ktx#head"};
    State _ktxResourceState=LOADING_INITIAL_DATA;ResourceType _currentlyLoadingResourceType=KTX;
    std::unique_ptr<ktx::KTXDescriptor> _originalKtxDescriptor;
    int _requestID=1,_bytesTotal=0,_lowestKnownPopulatedMip=65535;
    std::function<void()> onImage;
    QString getType(){return "Texture";}void setSize(int){}
    void setImage(gpu::TexturePointer p,int,int){assert(p);assert(_originalKtxDescriptor);++images;if(onImage)onImage();}
    void startMipRangeRequest(int,int){assert(std::this_thread::get_id()==owner);++tails;if(!tailCreationFails)_ktxMipRequest=new ResourceRequest;}
    void probeInitialKtxCache();
    // Test seam models existing sentinel teardown, not the method under test.
    void retire(){if(_ktxHeaderRequest||_ktxMipRequest){delete _ktxHeaderRequest;delete _ktxMipRequest;_ktxHeaderRequest=nullptr;_ktxMipRequest=nullptr;++releases;}}
    ~NetworkTexture(){retire();}
};
''' + method + r'''
QByteArray validData(){
    ktx::Header h;h.identifier[0]=42;
    QByteArray record("hash",4);record.append('\0');record.append(QByteArray(16,'a'));
    uint32_t length=record.size();QByteArray kv(reinterpret_cast<const char*>(&length),4);kv.append(record);
    while(kv.size()%4)kv.append('\0');h.bytesOfKeyValueData=kv.size();
    QByteArray result(reinterpret_cast<const char*>(&h),sizeof(h));result.append(kv);return result;
}
QSharedPointer<NetworkTexture> fixture(){
    releases=tails=images=failures=parses=0;throwCache=tailCreationFails=false;onComplete={};probePool.stopping=false;
    disk.reset();memoryTexture.reset();diskTexture.reset();assert(work.empty());
    assert(DependencyManager::get<StatTracker>()->pending==0);
    auto t=QSharedPointer<NetworkTexture>::create();t->_self=t;t->_ktxHeaderRequest=new ResourceRequest;t->_ktxHeaderRequest->data=validData();return t;
}
void worker(){assert(work.size()==1);auto f=std::move(work.front());work.clear();std::thread thread(std::move(f));thread.join();}
void dispatch(){QCoreApplication::sendPostedEvents(nullptr,QEvent::MetaCall);QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete);}
void run(){worker();dispatch();assert(DependencyManager::get<StatTracker>()->pending==0);}
void missComplete(QSharedPointer<NetworkTexture>& t){assert(tails==1&&releases==0&&images==0&&t->_ktxHeaderRequest&&t->_ktxMipRequest);t->retire();assert(releases==1);t.reset();assert(releases==1);}
int main(int argc,char** argv){QCoreApplication app(argc,argv);owner=std::this_thread::get_id();
    {auto t=fixture();memoryTexture=std::make_shared<gpu::Texture>();t->probeInitialKtxCache();run();assert(images==1&&tails==0&&releases==1&&parses==0);t.reset();assert(releases==1);}
    {auto t=fixture();disk=std::make_shared<File>();diskTexture=std::make_shared<gpu::Texture>();t->probeInitialKtxCache();run();assert(images==1&&tails==0&&releases==1&&parses==1);t.reset();assert(releases==1);}
    {auto t=fixture();t->probeInitialKtxCache();run();missComplete(t);}
    {auto t=fixture();memoryTexture=std::make_shared<gpu::Texture>();memoryTexture->min=2;t->probeInitialKtxCache();run();missComplete(t);}
    {auto t=fixture();disk=std::make_shared<File>();disk->valid=false;t->probeInitialKtxCache();run();assert(parses==1);missComplete(t);}
    {auto t=fixture();throwCache=true;t->probeInitialKtxCache();run();missComplete(t);}
    {auto t=fixture();t->_ktxHeaderRequest->result=ResourceRequest::Error;t->probeInitialKtxCache();run();missComplete(t);}
    for(int malformed=0;malformed<8;++malformed){auto t=fixture();auto& d=t->_ktxHeaderRequest->data;ktx::Header h;std::memcpy(&h,d.data(),sizeof(h));
        if(malformed==0)d=QByteArray(3,'x');
        if(malformed==1)d[0]=0;
        if(malformed==2){h.endianness=0;std::memcpy(d.data(),&h,sizeof(h));}
        if(malformed==3){h.bytesOfKeyValueData=999;std::memcpy(d.data(),&h,sizeof(h));}
        if(malformed==4){h.levels=33;std::memcpy(d.data(),&h,sizeof(h));}
        if(malformed==5){uint32_t n=999;std::memcpy(d.data()+sizeof(h),&n,4);}
        if(malformed==6){for(int i=sizeof(h)+4;i<d.size();++i)d[i]='x';}
        if(malformed==7)d[int(sizeof(h)+4)]=0;
        memoryTexture=std::make_shared<gpu::Texture>();t->probeInitialKtxCache();run();missComplete(t);
    }
    {auto t=fixture();tailCreationFails=true;t->probeInitialKtxCache();run();assert(releases==1&&failures==1&&tails==1&&!t->_ktxHeaderRequest);t.reset();assert(releases==1);}
    // Destroy before work begins: no owner callback or tail should occur.
    {auto t=fixture();t->probeInitialKtxCache();t.reset();run();assert(releases==1&&tails==0&&images==0);}
    // Destroy after worker posts callback: Qt removes context-bound callback.
    {auto t=fixture();t->probeInitialKtxCache();worker();t.reset();dispatch();assert(releases==1&&tails==0&&images==0);}
    // Refresh retires original request; even a same-URL replacement cannot accept stale result.
    {auto t=fixture();memoryTexture=std::make_shared<gpu::Texture>();t->probeInitialKtxCache();worker();t->retire();t->_ktxHeaderRequest=new ResourceRequest;dispatch();assert(releases==1&&images==0&&tails==0);t.reset();assert(releases==2);}
    // An old request may remain alive while replacement is installed.
    {auto t=fixture();t->probeInitialKtxCache();auto old=t->_ktxHeaderRequest;t->_ktxHeaderRequest=new ResourceRequest;run();assert(releases==0&&tails==0&&images==0);delete old;t.reset();}
    for(int guard=0;guard<3;++guard){auto t=fixture();memoryTexture=std::make_shared<gpu::Texture>();t->probeInitialKtxCache();worker();
        if(guard==0)t->_activeUrl=QUrl("https://fixture.invalid/replacement.ktx");
        if(guard==1)t->_currentlyLoadingResourceType=NetworkTexture::OTHER;
        if(guard==2)t->_ktxResourceState=NetworkTexture::FAILED_TO_LOAD;
        dispatch();assert(images==0&&tails==0&&releases==0);t.reset();assert(releases==1);
    }
    {auto t=fixture();memoryTexture=std::make_shared<gpu::Texture>();t->onImage=[&]{assert(!t->_ktxHeaderRequest);assert(releases==1);t->_ktxResourceState=NetworkTexture::LOADING_INITIAL_DATA;t->_ktxHeaderRequest=new ResourceRequest;};t->probeInitialKtxCache();run();assert(images==1&&tails==0&&releases==1&&t->_ktxHeaderRequest);t.reset();assert(releases==2);}
    for(int guard=0;guard<3;++guard){auto t=fixture();memoryTexture=std::make_shared<gpu::Texture>();onComplete=[&]{
        if(guard==0)t->_activeUrl=QUrl("https://fixture.invalid/reentrant.ktx");
        if(guard==1)t->_ktxResourceState=NetworkTexture::LOADING_INITIAL_DATA;
        if(guard==2)t->_originalKtxDescriptor.reset();
    };t->probeInitialKtxCache();run();assert(releases==1&&images==0&&tails==0);t.reset();assert(releases==1);}
    {auto t=fixture();tailCreationFails=true;onComplete=[&]{t->_ktxResourceState=NetworkTexture::LOADING_INITIAL_DATA;t->_ktxHeaderRequest=new ResourceRequest;};
        t->probeInitialKtxCache();run();assert(releases==1&&failures==0&&tails==1&&t->_ktxHeaderRequest);t.reset();assert(releases==2);}
    {auto t=fixture();probePool.stopping=true;t->probeInitialKtxCache();assert(work.empty()&&DependencyManager::get<StatTracker>()->pending==0);assert(!tails&&!images&&!releases);t.reset();assert(releases==1);}
    {auto t=fixture();t->probeInitialKtxCache();probePool.stopping=true;run();assert(!tails&&!images&&!releases);t.reset();assert(releases==1);}
    {auto t=fixture();memoryTexture=std::make_shared<gpu::Texture>();t->probeInitialKtxCache();worker();probePool.stopping=true;dispatch();assert(!tails&&!images&&!releases);t.reset();assert(releases==1);}
    {auto t=fixture();memoryTexture=std::make_shared<gpu::Texture>();onComplete=[] {probePool.stopping=true;};t->probeInitialKtxCache();run();assert(releases==1&&images==0&&failures==0);t.reset();assert(releases==1);}
    {auto t=fixture();tailCreationFails=true;onComplete=[] {probePool.stopping=true;};t->probeInitialKtxCache();run();assert(releases==1&&images==0&&failures==0&&tails==1);t.reset();assert(releases==1);}
    printf("PASS: actual production probe, Qt queued lifecycle, worker-thread cache seams, 33 scenarios\n");
}
'''


class HeaderProbeTest(unittest.TestCase):
    def test_production_probe_lifecycle(self):
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-ktx-header-probe-') as directory:
            cpp = Path(directory) / 'probe.cpp'
            exe = Path(directory) / 'probe'
            cpp.write_text(driver())
            subprocess.run(['c++', '-std=c++17', '-O2', '-pthread', str(cpp), '-o', str(exe), *flags], check=True)
            subprocess.run([str(exe)], check=True, timeout=30,
                           preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))


if __name__ == '__main__':
    unittest.main()
