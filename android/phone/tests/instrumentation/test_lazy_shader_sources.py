"""Exercise the production cache for laziness, stable references, and concurrency."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[4]
class LazyShaderSourcesTest(unittest.TestCase):
    def test_known_unknown_concurrent_and_eager_control(self):
        source = (ROOT/'libraries/shaders/src/shaders/Shaders.cpp.in').read_text()
        start = source.index('const Source& Source::get(uint32_t shaderId) {')
        end = source.index('\nbool Source::doReplacement', start)
        driver = r'''
#include <mutex>
#include <memory>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <thread>
#include <atomic>
#include <cassert>
#include <cstdint>
#define OVERTE_ANDROID_PHONE_SHADER_PAYLOAD
#define ANDROID_APP_PHONE_INTERFACE
#define PROP_VALUE_MAX 92
#define PHONE_LOADING(...) do {} while(false)
bool enabled = true;
char selected = '0';
bool phoneLoadingDiagnosticsEnabled() { return enabled; }
int __system_property_get(const char*, char* value) { value[0]=selected; value[1]=0; return 1; }
struct QElapsedTimer { void start(){} long long elapsed() const { return 0; } };
std::atomic<int> resourceInitializations{0}, loads{0};
void initShadersResources() { ++resourceInitializations; }
const std::vector<uint32_t>& allShaders() { static const std::vector<uint32_t> ids = [] { std::vector<uint32_t> v; for(uint32_t i=1;i<=128;++i)v.push_back(i);return v; }();return ids; }
struct Source {
    using Pointer = std::shared_ptr<Source>;
    uint32_t id{0};
    static const Source& get(uint32_t);
    static Pointer loadSource(uint32_t id) { ++loads; auto s=std::make_shared<Source>();s->id=id;return s; }
};
''' + source[start:end] + r'''
int main(int argc, char** argv) {
    assert(argc==2);
    selected=argv[1][0]=='1'?'1':'0';
    if(argv[1][0]=='2') { selected='1'; enabled=false; }
    const bool eager=enabled && selected=='1';
    assert(Source::get(999).id==0);
    assert(resourceInitializations==1);
    assert(loads==(eager?128:0));
    std::vector<std::thread> threads;
    const Source* results[32]{};
    for(int i=0;i<32;++i)threads.emplace_back([&,i]{results[i]=&Source::get(7);});
    for(auto& t:threads)t.join();
    for(auto result:results)assert(result==results[0] && result->id==7);
    assert(loads==(eager?128:1));
    // Loading every remaining ID must not invalidate the earlier reference.
    unsigned checksum=0;
    for(auto id:allShaders())checksum+=Source::get(id).id;
    assert(checksum==128*129/2);
    assert(loads==128 && resourceInitializations==1);
    assert(&Source::get(7)==results[0]);
    assert(Source::get(999).id==0 && loads==128);
}
'''
        with tempfile.TemporaryDirectory(prefix='phone-shader-cache-') as directory:
            path=Path(directory);(path/'test.cpp').write_text(driver)
            subprocess.run(['c++','-std=c++17','-pthread',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
            for mode in ['0','1','2']:
                subprocess.run([str(path/'test'),mode],check=True)
if __name__=='__main__':
    unittest.main()
