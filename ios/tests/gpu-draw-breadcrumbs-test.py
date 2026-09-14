#!/usr/bin/env python3
"""Exercise bounded production GPU evidence and its real failure formatter."""
from pathlib import Path
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / 'libraries/gpu-vk/src/gpu/vk/VKBackend.cpp').read_text()
start = source.index('void VKBackend::reportIOSFailedSubmit() const {')
end = source.index('\nvoid VKBackend::retireIOSDiagnosticSubmit()', start)
method = source[start:end]
code = r'''
#include "ios/render/GpuDrawBreadcrumbs.h"
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>
using overte::ios::GpuDrawBreadcrumbs;
std::vector<std::string> logs;
template<class... Args> void capture(int, const char* format, Args... args) {
    std::string f = format;
    for(size_t p; (p=f.find("%{public}"))!=std::string::npos;) f.replace(p,9,"%");
    char line[1024]; auto n=std::snprintf(line,sizeof(line),f.c_str(),args...);
    assert(n>=0 && size_t(n)<sizeof(line)); logs.emplace_back(line);
}
#define OS_LOG_DEFAULT 0
#define os_log_fault(...) capture(__VA_ARGS__)
struct VKBackend {
    GpuDrawBreadcrumbs _iosDrawBreadcrumbs;
    void reportIOSFailedSubmit() const;
};
METHOD
int main() {
    VKBackend b; auto& ring=b._iosDrawBreadcrumbs;
    // Empty failure must never invent a draw or a successful submission.
    b.reportIOSFailedSubmit(); assert(logs.size()==1);
    assert(logs[0]=="OVT_IOS_GPU_FAILURE_V1 submit=0 attempts=0 retained=0");
    logs.clear();
    for(uint64_t i=1;i<=200;++i) {
        ring.attempt({7,3,i,2,99,100});
        ring.input(true,4,6,2,1,i!=200,true,0,9999);
    }
    ring.submit(4361);
    assert(ring.pending().size==128 && ring.pending().total==200);
    assert(GpuDrawBreadcrumbs::at(ring.pending(),0).ordinal==73);
    assert(GpuDrawBreadcrumbs::at(ring.pending(),127).ordinal==200);
    // Encoding the next frame must not overwrite the submitted frame's evidence.
    ring.attempt({8,4,201,2,101,102});
    ring.input(false,0,3,1,0,true,true,0,2);
    b.reportIOSFailedSubmit(); assert(logs.size()==129);
    assert(logs.front()=="OVT_IOS_GPU_FAILURE_V1 submit=4361 attempts=200 retained=128");
    assert(logs.back().find("frame=7 batch=3 ordinal=200")!=std::string::npos);
    assert(logs.back().find("checked=1 valid=0 indexed=1 first=4 count=6")!=std::string::npos);
    assert(logs.back().find("min=0 max=9999")!=std::string::npos);
    ring.retire(); assert(ring.pending().submit==0 && ring.pending().size==0);
    ring.submit(4362); assert(ring.pending().size==1);
    assert(GpuDrawBreadcrumbs::at(ring.pending(),0).ordinal==201);
    // Default unchecked means unknown, never a successful validation receipt.
    ring.attempt({9,5,202,2,103,104}); ring.submit(4363);
    assert(!GpuDrawBreadcrumbs::at(ring.pending(),0).inputChecked);
    assert(!GpuDrawBreadcrumbs::at(ring.pending(),0).inputValid);
}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='overte-gpu-evidence-') as d:
    cpp=Path(d)/'test.cpp';binary=Path(d)/'test';cpp.write_text(code)
    subprocess.run(['c++','-std=c++17','-O1','-Wall','-Wextra','-Werror','-I',str(ROOT),str(cpp),'-o',str(binary)],check=True,timeout=40)
    subprocess.run([str(binary)],check=True,timeout=10)
# Check the real producer/fence/failure hooks, not only the independent storage.
assert '_iosDrawBreadcrumbs.attempt({' in source
assert '_iosDrawBreadcrumbs.input(indexed, first, count' in source
assert 'persistIOSDiagnosticSubmit(uint64_t submitId) {\n    _iosDrawBreadcrumbs.submit(submitId);' in source
assert 'retireIOSDiagnosticSubmit() {\n    _iosDrawBreadcrumbs.retire();' in source
display=(ROOT/'libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.cpp').read_text()
assert display.count('backend->reportIOSFailedSubmit();')==2
print('PASS: real bounded submit snapshot/failure formatter, overflow order, next-frame isolation, fence retirement, unchecked/invalid inputs, production hooks')
