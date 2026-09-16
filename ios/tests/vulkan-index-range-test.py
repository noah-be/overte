#!/usr/bin/env python3
"""Exercise exact index-slice cache and real staging invalidation at a CPU boundary.

This is not native Vulkan/GPU acceptance. --mutation verifies that omitting upload
invalidation is caught, including unchanged-size partial updates.
"""
from pathlib import Path
import argparse
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--mutation', action='store_true')
args = parser.parse_args()
source = (ROOT/'libraries/gpu-vk/src/gpu/vk/VKBuffer.cpp').read_text()
start = source.index('void VKBuffer::transferToStaging(')
brace = source.index('{', start)
end, depth = brace + 1, 1
while depth:
    depth += (source[end] == '{') - (source[end] == '}')
    end += 1
transfer = source[start:end]
if args.mutation:
    assert '_indexRanges.invalidate();' in transfer
    transfer = transfer.replace('_indexRanges.invalidate();', '')
code = r'''
#include "VKIndexRange.h"
#include <cassert>
#include <vector>
#include <random>
#include <iostream>
using gpu::vk::IndexRangeCache;
using Size = size_t;
#define Q_ASSERT assert
#define VK_WHOLE_SIZE 0
struct PageManager { enum { DIRTY=1 }; };
struct VKBackend {};
struct VKBuffer {
    IndexRangeCache _indexRanges;
    std::vector<uint8_t> _localData=std::vector<uint8_t>(16);
    struct {
        struct {
            std::vector<uint8_t> data=std::vector<uint8_t>(16);
            const uint8_t* readData() const { return data.data(); }
        } _renderSysmem;
        struct {
            int _flags=PageManager::DIRTY;
            size_t offset=4, bytes=4;
            bool getNextTransferBlock(Size& outOffset, Size& outSize, Size& page) {
                if (page++) { return false; }
                outOffset=offset; outSize=bytes; return true;
            }
        } _renderPages;
    } _gpuObject;
    struct {
        size_t size=16;
        std::vector<uint8_t> copied;
        void map() {}
        void copy(size_t n, const uint8_t* data) { copied.assign(data, data+n); }
        void flush(int) {}
        void unmap() {}
    } stagingAllocation;
    void transferToStaging(VKBackend&);
};
PRODUCTION
int main() {
    IndexRangeCache cache; IndexRangeCache::Range range;
    // Deliberately unaligned CPU address: Vulkan byte offset is still aligned.
    std::vector<uint8_t> unaligned(33);
    const uint32_t indices[] = {9999, 2, 5, UINT32_MAX, 7, 0, 0, 0};
    memcpy(unaligned.data()+1, indices, sizeof(indices));
    const auto* data=unaligned.data()+1;
    assert(cache.get(data,32,4,0,2,4,false,range) && range.minimum==2 && range.maximum==5);
    assert(cache.get(data,32,0,0,1,4,false,range) && range.maximum==9999);
    assert(cache.get(data,32,0,1,2,4,false,range) && range.maximum==5);
    assert(cache.get(data,32,0,3,1,4,false,range) && range.maximum==UINT32_MAX);
    assert(cache.get(data,32,0,3,1,4,true,range) && !range.hasVertices);
    assert(cache.get(data,32,0,1,4,4,true,range) && range.minimum==2 && range.maximum==7);
    assert(!cache.get(data,32,1,0,1,4,false,range));
    assert(!cache.get(data,32,0,UINT32_MAX,2,4,false,range));
    assert(!cache.get(data,32,0,1,UINT32_MAX,4,false,range));
    assert(!cache.get(data,32,0,0,1,1,false,range));
    assert(!cache.get(nullptr,32,0,0,1,4,false,range));
    const uint16_t shortIndices[]={UINT16_MAX, 4, 8};
    cache.invalidate();
    data=reinterpret_cast<const uint8_t*>(shortIndices);
    assert(cache.get(data,6,0,0,3,2,true,range) && range.maximum==8);
    assert(cache.get(data,6,0,0,3,2,false,range) && range.maximum==UINT16_MAX);
    assert(!cache.get(data,4,0,0,3,2,false,range)); // applied shrink
    // Random slices compare to a direct reference, alternating width/restart.
    std::mt19937 rng(12095);
    for (unsigned generation=0; generation<30; ++generation) {
        std::vector<uint32_t> values(300);
        for (auto& value:values) { value=rng(); }
        values[30]=UINT32_MAX;
        cache.invalidate();
        for (unsigned n=0; n<200; ++n) {
            const size_t width=n%2 ? 2:4, elements=values.size()*4/width;
            size_t first=rng()%elements, count=rng()%(elements-first)+1;
            bool restart=n%3==0; uint32_t minimum=UINT32_MAX, maximum=0; bool has=false;
            for (size_t i=first; i<first+count; ++i) {
                uint32_t value;
                if(width==2) { uint16_t v; memcpy(&v,reinterpret_cast<uint8_t*>(values.data())+i*width,2); value=v; }
                else { value=values[i]; }
                if(restart && value==(width==2?UINT16_MAX:UINT32_MAX)) { continue; }
                has=true; minimum=std::min(minimum,value); maximum=std::max(maximum,value);
            }
            for(int repeat=0;repeat<2;++repeat) {
                assert(cache.get(reinterpret_cast<uint8_t*>(values.data()),values.size()*4,0,first,count,width,restart,range));
                assert(range.hasVertices==has && range.minimum==minimum && range.maximum==maximum);
            }
        }
    }
    // Execute the actual staging transfer method. An in-place dirty page changes
    // the index without changing allocation size, sysmem stamp or draw slice.
    VKBuffer buffer; VKBackend backend;
    assert(buffer._indexRanges.get(buffer._localData.data(),16,0,1,1,4,false,range) && range.maximum==0);
    uint32_t changed=9999;
    memcpy(buffer._gpuObject._renderSysmem.data.data()+4,&changed,4);
    buffer.transferToStaging(backend);
    assert(buffer._indexRanges.get(buffer._localData.data(),16,0,1,1,4,false,range));
    if (range.maximum!=9999) { std::cerr << "stale index range after same-size staging upload\n"; return 23; }
    assert(buffer.stagingAllocation.copied==buffer._localData);
    assert(buffer._gpuObject._renderPages._flags==0);
    std::cout << "PASS exact slices, 16/32-bit, restart, partial upload invalidation and 12000 reference comparisons\n";
}
'''.replace('PRODUCTION', transfer)
with tempfile.TemporaryDirectory(prefix='overte-index-range-') as temp:
    cpp=Path(temp)/'test.cpp'; cpp.write_text(code); binary=Path(temp)/'test'
    subprocess.run(['c++','-std=c++17','-O1', '-I'+str(ROOT/'libraries/gpu-vk/src/gpu/vk'),str(cpp),'-o',str(binary)],check=True,timeout=40)
    result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=15)
    if args.mutation:
        assert result.returncode==23 and 'stale index range' in result.stderr, result.stderr
        print('PASS mutation rejected: stale index range after same-size staging upload')
    else:
        assert result.returncode==0, result.stderr
        print(result.stdout.strip())
