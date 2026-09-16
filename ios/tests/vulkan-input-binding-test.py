#!/usr/bin/env python3
"""Exercise actual Vulkan input/draw methods at a recording Vulkan boundary.

OVERTE_INPUT_BASELINE selects historical source for the type-change counterexample.
OVERTE_INDEX_RANGE_MUTATION restores the former byte-only vertex check.
No GPU or native acceptance is claimed.
"""
import os
import resource
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
path = 'libraries/gpu-vk/src/gpu/vk/VKBackend.cpp'
baseline = os.environ.get('OVERTE_INPUT_BASELINE')
index_mutation = os.environ.get('OVERTE_INDEX_RANGE_MUTATION') == '1'
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
#include <array>
#include <bitset>
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <vector>
#include <iostream>
#include "VKIndexRange.h"
using gpu::vk::IndexRangeCache;
#define Q_ASSERT(x) ((void)0)
#define OS_LOG_DEFAULT 0
#define os_log_fault(...) ((void)0)
#define GPU_STEREO_DRAWCALL_INSTANCED
using uint32 = uint32_t;
namespace gpu {
enum Type { UINT32, UINT16, INVALID };
enum Primitive { TRIANGLES, LINE_STRIP, TRIANGLE_STRIP };
using Offset = uint32_t;
namespace Stream { enum { PER_VERTEX, PER_INSTANCE }; }
template<class T> T* acquire(T* p) { return p; }
}
using gpu::Type;
using gpu::Offset;
struct VKBuffer {
    VkBuffer buffer;
    struct { size_t size=64; } allocation;
    std::vector<uint8_t> _localData = std::vector<uint8_t>(64);
    IndexRangeCache _indexRanges;
    INDEX_METHOD
};
struct Buffer {
    struct { size_t size; size_t getSize() const { return size; } } _renderSysmem;
    VKBuffer* gpu;
};
struct Backend { template<class T> static T* getGPUObject(const Buffer& b) { return b.gpu; } };
using BufferPointer = std::shared_ptr<Buffer>;
struct Batch {
    struct Param { uint32_t _uint; };
    std::array<Param,5> _params{};
    struct { BufferPointer value; BufferPointer get(uint32_t) const { return value; } } _buffers;
};
struct Format {
    struct Attribute { unsigned _offset=0; unsigned getSize() const { return 4; } };
    struct Channel { std::vector<int> _slots{0}; int _frequency = gpu::Stream::PER_VERTEX; };
    std::map<int,Attribute> attributes{{0,{}}};
    std::map<int,Channel> channels{{0,{}}};
    const auto& getAttributes() const { return attributes; }
    const auto& getChannels() const { return channels; }
};
unsigned indexBinds=0,vertexBinds=0,draws=0; VkIndexType lastType{}; uint32_t lastInstance=0;
void vkCmdBindIndexBuffer(VkCommandBuffer,VkBuffer b,VkDeviceSize,VkIndexType t) { assert(b); ++indexBinds; lastType=t; }
void vkCmdBindVertexBuffers(VkCommandBuffer,uint32_t,uint32_t,const VkBuffer* b,const VkDeviceSize*) { assert(*b); ++vertexBinds; }
void vkCmdDraw(VkCommandBuffer,uint32_t,uint32_t,uint32_t,uint32_t first) { ++draws; lastInstance=first; }
void vkCmdDrawIndexed(VkCommandBuffer,uint32_t,uint32_t,uint32_t,int32_t,uint32_t first) { ++draws; lastInstance=first; }
struct VKBackend {
    struct Breadcrumbs { template<class... T> void input(T...) const {} } _iosDrawBreadcrumbs;
    struct Input {
        Type _indexBufferType=gpu::UINT32; Buffer* _indexBuffer=nullptr; Offset _indexBufferOffset=0;
        Format* _format=nullptr;
        std::array<Buffer*,2> _buffers{}; std::array<VkBuffer,2> _bufferVBOs{};
        std::array<Offset,2> _bufferOffsets{}, _bufferStrides{};
        std::bitset<2> _invalidBuffers; bool _lastUpdateStereoState=false,_invalidFormat=false;
    } _input;
    struct { struct { gpu::Primitive primitiveTopology=gpu::TRIANGLES; std::array<Offset,2> _bufferStrides{}; std::bitset<2> _bufferStrideSet; } pipelineState; } _cache;
    struct { uint64_t _DSNumTriangles=0,_DSNumDrawcalls=0,_DSNumAPIDrawcalls=0,_ISNumInputBufferChanges=0; } _stats;
    bool _inRenderTransferPass=false,stereo=false;
    VkCommandBuffer _currentCommandBuffer{};
    bool isStereo() const { return stereo; }
    size_t getNumInputBuffers() const { return 2; }
    VKBuffer* syncGPUObject(const Buffer* b) { return b ? b->gpu : nullptr; }
    bool validateInputDraw(bool,uint32_t,uint32_t,uint32_t,uint32_t) const;
    void do_setIndexBuffer(const Batch&,size_t);
    void do_setInputBuffer(const Batch&,size_t);
    void updateInput();
    void draw(VkPrimitiveTopology,uint32,uint32);
    void do_drawIndexed(const Batch&,size_t);
    void do_drawInstanced(const Batch&,size_t);
    void do_drawIndexedInstanced(const Batch&,size_t);
};
PRODUCTION
int main() {
    VKBackend b; Batch command;
    VKBuffer native{reinterpret_cast<VkBuffer>(1)};
    auto data=std::make_shared<Buffer>(Buffer{{64},&native});
    command._buffers.value=data; command._params[2]._uint=gpu::UINT16;
    b.do_setIndexBuffer(command,0); assert(indexBinds==1 && lastType==VK_INDEX_TYPE_UINT16);
    command._params[2]._uint=gpu::UINT32;
    b.do_setIndexBuffer(command,0);
    assert(indexBinds==2 && lastType==VK_INDEX_TYPE_UINT32 && "same buffer index type change must rebind");
    b._inRenderTransferPass=true; command._params[2]._uint=gpu::UINT16;
    b.do_setIndexBuffer(command,0); assert(b._input._indexBufferType==gpu::UINT32);
    b._inRenderTransferPass=false;
    command._params[0]._uint=1; b.do_setIndexBuffer(command,0);
    assert(!b._input._indexBuffer && indexBinds==2);
    command._params[0]._uint=0; command._params[2]._uint=gpu::INVALID;
    b.do_setIndexBuffer(command,0); assert(!b._input._indexBuffer);
    command._params[2]._uint=gpu::UINT32; b.do_setIndexBuffer(command,0);
    assert(b.validateInputDraw(true,16,0,1,0));
    assert(!b.validateInputDraw(true,17,0,1,0));
    assert(!b.validateInputDraw(true,2,UINT32_MAX,1,0));
    command._buffers.value=nullptr; b.do_setIndexBuffer(command,0);
    assert(!b.validateInputDraw(true,1,0,1,0));
    command._params[0]._uint=0;command._params[1]._uint=1;
    b.do_drawIndexed(command,0); assert(draws==0);
    Format format; b._input._format=&format;
    assert(!b.validateInputDraw(false,1,0,1,0));
    b._input._buffers[0]=data.get();b._input._bufferStrides[0]=4;
    b._input._invalidBuffers.set(0); b.updateInput();
    assert(vertexBinds==1 && b._input._bufferVBOs[0]==native.buffer);
    assert(b.validateInputDraw(false,16,0,1,0));
    assert(!b.validateInputDraw(false,17,0,1,0));
    b.draw(VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,3,0); assert(draws==1);
    b.draw(VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,20,0); assert(draws==1);
    // An index buffer with valid byte extent can still fetch beyond vertex data.
    command._buffers.value=data; command._params[0]._uint=0; command._params[2]._uint=gpu::UINT32;
    b.do_setIndexBuffer(command,0);
    uint32_t bad=16; std::memcpy(native._localData.data(),&bad,4); native._indexRanges.invalidate();
    assert(!b.validateInputDraw(true,1,0,1,0) && "semantic index must fit vertex storage");
    command._params[0]._uint=0; command._params[1]._uint=1;
    b.do_drawIndexed(command,0); assert(draws==1); // malformed fetch never reaches Vulkan
    assert(b.validateInputDraw(true,1,1,1,0)); // unrelated slice remains valid
    bad=15; std::memcpy(native._localData.data(),&bad,4); native._indexRanges.invalidate();
    assert(b.validateInputDraw(true,1,0,1,0)); // same-size repair must invalidate
    bad=UINT32_MAX; std::memcpy(native._localData.data(),&bad,4); native._indexRanges.invalidate();
    assert(!b.validateInputDraw(true,1,0,1,0)); // list sentinel is a real invalid index
    b._cache.pipelineState.primitiveTopology=gpu::TRIANGLE_STRIP;
#if defined(Q_OS_IOS)
    assert(b.validateInputDraw(true,1,0,1,0)); // restart-only strip has no fetch
#else
    assert(!b.validateInputDraw(true,1,0,1,0)); // desktop restart disabled
#endif
    b._cache.pipelineState.primitiveTopology=gpu::TRIANGLES;
    bad=0; std::memcpy(native._localData.data(),&bad,4); native._indexRanges.invalidate();
    format.channels[0]._frequency=gpu::Stream::PER_INSTANCE;
    assert(b.validateInputDraw(false,1,0,2,14));
    assert(!b.validateInputDraw(false,1,0,2,15));
    command._params={{{14},{0},{3},{0},{2}}};
    b.do_drawInstanced(command,0); assert(draws==2 && lastInstance==14);
    command._params[0]._uint=15;b.do_drawInstanced(command,0);assert(draws==2);
    command._buffers.value=data;command._params[0]._uint=0;command._params[2]._uint=gpu::UINT32;
    b.do_setIndexBuffer(command,0);
    command._params={{{14},{0},{3},{0},{2}}};
    b.do_drawIndexedInstanced(command,0);assert(draws==3 && lastInstance==14);
    b._input._buffers[1]=nullptr;b._input._invalidBuffers.set(1);b.updateInput();
    assert(vertexBinds==1 && b.validateInputDraw(false,1,0,1,0)); // unused channel clear
    b._input._buffers[0]=nullptr;b._input._invalidBuffers.set(0);b.updateInput();
    assert(vertexBinds==1 && !b.validateInputDraw(false,1,0,1,0));
    b._input._buffers[0]=data.get();b._input._bufferOffsets[0]=64;b._input._invalidBuffers.set(0);b.updateInput();
    assert(vertexBinds==1 && !b.validateInputDraw(false,1,0,1,0));
    std::cout << "PASS input bindings, semantic index bounds, slice/restart behavior, instance offsets and valid draws\n";
}
'''
signatures=['void VKBackend::do_setIndexBuffer(', 'void VKBackend::do_setInputBuffer(',
            'void VKBackend::updateInput(', 'void VKBackend::draw(',
            'void VKBackend::do_drawIndexed(', 'void VKBackend::do_drawInstanced(',
            'void VKBackend::do_drawIndexedInstanced(']
production='\n'.join(function(s) for s in signatures)
production += '\n' + (function('bool VKBackend::validateInputDraw(') if not baseline else
    'bool VKBackend::validateInputDraw(bool,uint32_t,uint32_t,uint32_t,uint32_t) const { return true; }')
if index_mutation:
    assert 'indexed ? indexRange.maximum' in production
    production=production.replace('indexed ? indexRange.maximum', 'indexed ? 0')
header=(ROOT/'libraries/gpu-vk/src/gpu/vk/VKBuffer.h').read_text()
start=header.index('    bool getIndexRange(')
end=header.index('\n    }',start)+6
code=code.replace('INDEX_METHOD',header[start:end]).replace('PRODUCTION',production)
with tempfile.TemporaryDirectory(prefix='overte-input-') as temp:
    cpp=Path(temp)/'test.cpp';cpp.write_text(code);binary=Path(temp)/'test'
    for platform in ['desktop', 'ios']:
        subprocess.run(['c++','-std=c++17','-O1','-I'+str(ROOT/'libraries/gpu-vk/src/gpu/vk'),*(['-DQ_OS_IOS'] if platform == 'ios' else []),str(cpp),'-o',str(binary)],check=True,timeout=40)
        result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=15)
        if baseline:
            assert result.returncode != 0 and 'same buffer index type change must rebind' in result.stderr,result.stderr
            print(platform + ': EXPECTED BASELINE FAILURE: same buffer index type change must rebind')
        elif index_mutation:
            assert result.returncode != 0 and 'semantic index must fit vertex storage' in result.stderr,result.stderr
            print(platform + ': EXPECTED MUTATION FAILURE: semantic index must fit vertex storage')
        else:
            assert result.returncode == 0,result.stderr
            print(platform + ': ' + result.stdout.strip())
