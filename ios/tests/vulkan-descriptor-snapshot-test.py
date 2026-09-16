"""Compile real descriptor writers against a recording Vulkan boundary.

No GPU/native acceptance. OVERTE_DESCRIPTOR_BASELINE selects old production code.
"""
import os
import resource
from pathlib import Path
import subprocess
import tempfile

resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

ROOT = Path(__file__).resolve().parents[2]
baseline = os.environ.get('OVERTE_DESCRIPTOR_BASELINE')
path = 'libraries/gpu-vk/src/gpu/vk/VKBackend.cpp'
# The backend's applied-snapshot access must remain legal in the production API.
assert 'friend class ::gpu::vk::VKBackend;' in (ROOT/'libraries/gpu/src/gpu/Buffer.h').read_text()
source = subprocess.check_output(['git', 'show', baseline + ':' + path], cwd=ROOT, text=True) if baseline else (ROOT/path).read_text()

def function(signature):
    start = source.index(signature)
    brace = source.index('{', start)
    end, depth = brace + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

code = r'''
#include <vulkan/vulkan.h>
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <memory>
#include <set>
#include <unordered_map>
#include <vector>
#include <iostream>
struct VKBuffer { VkBuffer buffer; struct { size_t size; } allocation; };
struct Buffer {
    struct { size_t size; size_t getSize() const { return size; } } _renderSysmem;
    size_t producerSize;
    VKBuffer* gpu;
    mutable unsigned producerReads = 0;
    size_t getSize() const { ++producerReads; return producerSize; }
};
std::vector<VkDescriptorBufferInfo> written;
VkResult vkAllocateDescriptorSets(VkDevice, const VkDescriptorSetAllocateInfo*, VkDescriptorSet* set) {
    *set = reinterpret_cast<VkDescriptorSet>(1); return VK_SUCCESS;
}
void vkUpdateDescriptorSets(VkDevice, uint32_t count, const VkWriteDescriptorSet* sets, uint32_t, const VkCopyDescriptorSet*) {
    written.clear(); for (uint32_t i=0;i<count;++i) written.push_back(*sets[i].pBufferInfo);
}
void vkCmdBindDescriptorSets(VkCommandBuffer, VkPipelineBindPoint, VkPipelineLayout, uint32_t, uint32_t,
                            const VkDescriptorSet*, uint32_t, const uint32_t*) {}
#define VK_CHECK_RESULT(expr) assert((expr)==VK_SUCCESS)
#define OS_LOG_DEFAULT 0
#define os_log_info(...) ((void)0)
#define os_log_fault(...) ((void)0)
bool iosRuntimeRenderDiagnosticsEnabled() { return false; }
namespace overte { namespace ios {
    enum class RenderMetric { uniformFallbacks, storageFallbacks };
    void observeRender(RenderMetric) {}
}}
template<class... T> void reportDescriptorCoverage(T&&...) {}
struct VKBackend {
    struct Cache { struct PipelineLayout {
        std::unordered_map<size_t,size_t> uniformBindingMap {{0,0}}, storageBindingMap {{0,0}};
        VkDescriptorSetLayout uniformLayout {}, storageLayout {};
        VkPipelineLayout pipelineLayout {};
    }; };
    struct State { Buffer* buffer {}; uint64_t offset {}, size {}; };
    struct { std::vector<State> _buffers {1}; } _uniform, _resource;
    VkDescriptorBufferInfo _defaultBufferInfo {reinterpret_cast<VkBuffer>(999),0,65536};
    std::vector<VkWriteDescriptorSet> uniformVkWriteDescriptorSets, storageVkWriteDescriptorSets;
    std::vector<VkDescriptorBufferInfo> uniformVkDescriptorBufferInfo, storageVkDescriptorBufferInfo;
    struct Device { VkDevice logicalDevice {}; } device;
    struct { Device* device; } _context {&device};
    struct Frame { VkDescriptorPool _descriptorPool {}; } frame;
    Frame* _currentFrame {&frame};
    VkCommandBuffer _currentCommandBuffer {};
    std::set<int> _iosFallbackUniformBindings, _iosFallbackStorageBindings;
    bool _iosTraceCurrentDraw = false;
    unsigned syncCalls = 0;
    VKBuffer* syncGPUObject(Buffer* b) { ++syncCalls; return b->gpu; }
    void updateVkDescriptorWriteSetsUniform(const Cache::PipelineLayout&, std::vector<VkWriteDescriptorSet>&,
                                           std::vector<VkDescriptorBufferInfo>&, bool);
    void updateVkDescriptorWriteSetsStorage(const Cache::PipelineLayout&, std::vector<VkWriteDescriptorSet>&,
                                           std::vector<VkDescriptorBufferInfo>&, bool);
};
PRODUCTION
int main() {
    VKBackend backend; VKBackend::Cache::PipelineLayout layout;
    std::vector<VkWriteDescriptorSet> oldSets; std::vector<VkDescriptorBufferInfo> oldInfos;
    VKBuffer gpu {reinterpret_cast<VkBuffer>(1), {512}};
    Buffer buffer {{512}, 4096, &gpu};
    backend._uniform._buffers[0] = {&buffer, 0, 1024};
    backend._resource._buffers[0] = {&buffer, 0, 0};
    auto uniform=[&] { backend.updateVkDescriptorWriteSetsUniform(layout,oldSets,oldInfos,true); assert(written.size()==1); return written[0]; };
    auto storage=[&] { backend.updateVkDescriptorWriteSetsStorage(layout,oldSets,oldInfos,true); assert(written.size()==1); return written[0]; };
    auto fallback=[&](const auto& info) { return info.buffer==backend._defaultBufferInfo.buffer; };
    assert(fallback(uniform()) && "descriptor extends beyond applied GPU allocation");
    auto info=storage(); assert(info.buffer==gpu.buffer && info.range==512);
    backend._uniform._buffers[0] = {&buffer,256,256};
    info=uniform(); assert(info.buffer==gpu.buffer && info.offset==256 && info.range==256);
    // Reusing an unchanged binding must not allocate/write descriptors again.
    written.clear();
    backend.updateVkDescriptorWriteSetsUniform(layout,oldSets,oldInfos,false);
    assert(written.empty());
    backend._uniform._buffers[0].size=128;
    backend.updateVkDescriptorWriteSetsUniform(layout,oldSets,oldInfos,false);
    assert(written.size()==1 && written[0].range==128);
    backend._uniform._buffers[0].size=256;
    // Producer shrink/zero must not change the already-applied frame's bindings.
    buffer.producerSize=0; assert(!fallback(uniform())); assert(storage().range==512);
    // Snapshot cannot advertise bytes past the actual allocation either.
    buffer._renderSysmem.size=1024; assert(storage().range==512);
    backend._uniform._buffers[0] = {&buffer,510,3}; assert(fallback(uniform()));
    backend._uniform._buffers[0] = {&buffer,UINT64_MAX,2}; assert(fallback(uniform()));
    backend._uniform._buffers[0] = {&buffer,0,0}; assert(fallback(uniform()));
    buffer._renderSysmem.size=0; auto before=backend.syncCalls;
    assert(fallback(storage())); assert(fallback(uniform())); assert(before==backend.syncCalls);
    buffer._renderSysmem.size=512; buffer.gpu=nullptr;
    assert(fallback(storage())); assert(fallback(uniform()));
    buffer.gpu=&gpu; gpu.buffer=VK_NULL_HANDLE;
    assert(fallback(storage())); assert(fallback(uniform()));
    gpu.buffer=reinterpret_cast<VkBuffer>(1); backend._uniform._buffers[0]={&buffer,0,64};
#ifdef Q_OS_IOS
    backend._iosFallbackUniformBindings.insert(0); backend._iosFallbackStorageBindings.insert(0);
    assert(fallback(uniform())); assert(fallback(storage()));
#endif
    assert(buffer.producerReads==0 && "render path consulted mutable producer size");
    std::cout << "PASS: real descriptor writers; CPU growth/shrink; allocation cap; empty/missing buffers; overflow; iOS isolation\n";
}
'''
code=code.replace('PRODUCTION','\n'.join(function(s) for s in [
    'bool haveBufferDescriptorSetsChanged(',
    'void VKBackend::updateVkDescriptorWriteSetsUniform(',
    'void VKBackend::updateVkDescriptorWriteSetsStorage(']))
with tempfile.TemporaryDirectory(prefix='overte-descriptor-') as temp:
    cpp=Path(temp)/'test.cpp'; cpp.write_text(code)
    for platform in ['desktop','ios']:
        binary=Path(temp)/platform
        subprocess.run(['c++','-std=c++20','-O1','-g',*(['-DQ_OS_IOS'] if platform=='ios' else []),str(cpp),'-o',str(binary)],check=True,timeout=40)
        result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=20)
        if baseline:
            assert result.returncode != 0 and 'descriptor extends beyond applied GPU allocation' in result.stderr,result.stderr
            print(platform+': EXPECTED BASELINE FAILURE: GPU descriptor overrun')
        else:
            assert result.returncode==0,result.stderr
            print(platform+': '+result.stdout.strip())
