#!/usr/bin/env python3
"""Execute production DrawCallInfo binding with a recording Vulkan boundary."""
import os
import resource
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
path='libraries/gpu-vk/src/gpu/vk/VKBackend.cpp'
baseline=os.environ.get('OVERTE_DRAW_INFO_BASELINE')
source=subprocess.check_output(['git','show',baseline+':'+path],cwd=ROOT,text=True) if baseline else (ROOT/path).read_text()
def extract(signature):
    a=source.index(signature); b=source.index('{',a); end=b+1; depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[a:end]
method=extract(('void' if baseline else 'bool')+' VKBackend::updateTransform(')
if baseline:
    method=method.replace('void VKBackend::updateTransform(', 'bool VKBackend::updateTransform(')
    method=method[:-1]+'return true;\n}'
code=r'''
#include <vulkan/vulkan.h>
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>
#include <iostream>
#define Q_ASSERT(x) ((void)0)
#define GPU_STEREO_DRAWCALL_INSTANCED
namespace gpu {
struct Batch {
 enum Command {COMMAND_draw,COMMAND_drawIndexed,COMMAND_drawInstanced,COMMAND_drawIndexedInstanced, COMMAND_startNamedCall, COMMAND_stopNamedCall, COMMAND_multiDrawIndirect, COMMAND_multiDrawIndexedIndirect};
 struct DrawCallInfo {uint32_t index=0;};
 struct Param {uint32_t _uint;};
 std::vector<Param> _params{{0},{3},{0},{0},{2}};
 std::vector<Command> commands{COMMAND_drawInstanced};
 std::vector<size_t> offsets{0};
 std::string _currentNamedCall;
 std::unordered_map<std::string,int> _namedData{{"valid",0}};
 std::vector<DrawCallInfo> infos{{},{},{},{}};
 std::vector<DrawCallInfo> _drawCallInfos{{},{}};
 std::vector<int> _objects{0};
 const auto& getCommands() const{return commands;}
 const auto& getCommandOffsets() const{return offsets;}
 const auto& getDrawCallInfoBuffer() const{return infos;}
};
}
using gpu::Batch;
struct VKBuffer { VkBuffer buffer=reinterpret_cast<VkBuffer>(1); };
struct Buffer { struct {size_t size=32;size_t getSize() const{return size;}} _renderSysmem;VKBuffer native; };
unsigned binds=0; VkDeviceSize lastOffset=0;
void vkCmdBindVertexBuffers(VkCommandBuffer,uint32_t,uint32_t,const VkBuffer* b,const VkDeviceSize* offset){assert(*b);++binds;lastOffset=*offset;}
struct VKBackend {
 struct Frame {std::shared_ptr<Buffer> _drawCallInfoBuffer=std::make_shared<Buffer>();} frame;
 Frame* _currentFrame=&frame;
 struct Transform {
  bool _enabledDrawcallInfoBuffer=false;
  std::vector<VkDeviceSize> _unnamedDrawCallInfoOffsets{0};
  std::vector<size_t> _unnamedDrawCallInfoElementCounts{8};
  std::vector<int> _unnamedDrawCallInfoSourceIndices;
  std::unordered_map<std::string,VkDeviceSize> _drawCallInfoOffsets;
  void update(int,int,int,Frame&){}
 } _transform;
 int _commandIndex=0,_currentDraw=0,_stereo=0,_uniform=0;
 bool stereo=false;
 VkCommandBuffer _currentCommandBuffer{};
 bool isStereo()const{return stereo;}
 uint32_t getDrawCallInfoBinding()const{return 0;}
 VKBuffer* syncGPUObject(Buffer* b){return &b->native;}
 bool updateTransform(const Batch&);
 void transfer(const Batch&);
};
PRODUCTION
int main(){
 VKBackend producer;Batch stream;
 stream.commands={Batch::COMMAND_draw,Batch::COMMAND_draw};stream.offsets={0,0};
 stream._drawCallInfos.resize(1);producer.transfer(stream);
 assert(producer._transform._unnamedDrawCallInfoOffsets.size()==2);
 assert(producer._transform._unnamedDrawCallInfoOffsets[0]!=VK_WHOLE_SIZE);
 assert(producer._transform._unnamedDrawCallInfoOffsets[1]==VK_WHOLE_SIZE);
 stream._drawCallInfos.resize(2);stream.offsets={99,0};producer.transfer(stream);
 assert(producer._transform._unnamedDrawCallInfoOffsets[0]==VK_WHOLE_SIZE);
 assert(producer._transform._unnamedDrawCallInfoOffsets[1]!=VK_WHOLE_SIZE);
 assert(producer._transform._unnamedDrawCallInfoSourceIndices[1]==1);
 stream.offsets={0};producer.transfer(stream);
 assert(producer._transform._unnamedDrawCallInfoOffsets[1]==VK_WHOLE_SIZE);
 stream.commands={Batch::COMMAND_drawInstanced};stream.offsets={0};stream._params.resize(4);producer.transfer(stream);
 assert(producer._transform._unnamedDrawCallInfoOffsets[0]==VK_WHOLE_SIZE);
 stream._params.resize(5);stream._params[4]._uint=2;
 stream.commands={Batch::COMMAND_startNamedCall,Batch::COMMAND_draw,Batch::COMMAND_stopNamedCall,Batch::COMMAND_drawInstanced};
 stream.offsets={0,0,0,0};producer.transfer(stream);
 assert(producer._transform._unnamedDrawCallInfoOffsets.size()==2);
 assert(producer._transform._unnamedDrawCallInfoSourceIndices[0]==-1);
 assert(producer._transform._unnamedDrawCallInfoSourceIndices[1]==0);
 assert(producer._transform._unnamedDrawCallInfoElementCounts[1]==4);
 stream.commands={Batch::COMMAND_multiDrawIndirect,Batch::COMMAND_multiDrawIndexedIndirect};
 stream.offsets={0,0};stream._params.resize(2);producer.transfer(stream);
 assert(producer._transform._unnamedDrawCallInfoOffsets[0]!=VK_WHOLE_SIZE);
 assert(producer._transform._unnamedDrawCallInfoOffsets[1]!=VK_WHOLE_SIZE);
 VKBackend indirectBackend;Batch indirectBatch;
 indirectBatch.commands={Batch::COMMAND_multiDrawIndirect};indirectBatch._params.resize(2);
 assert(indirectBackend.updateTransform(indirectBatch));
 indirectBatch.commands[0]=Batch::COMMAND_multiDrawIndexedIndirect;
 assert(indirectBackend.updateTransform(indirectBatch));binds=0;
 VKBackend b;Batch batch;
 batch._currentNamedCall="missing";
 assert(!b.updateTransform(batch) && binds==0 && "missing named draw must not bind offset zero");
 assert(b._transform._drawCallInfoOffsets.empty());
 batch._currentNamedCall="valid";b._transform._drawCallInfoOffsets["valid"]=8;
 assert(b.updateTransform(batch)&&binds==1&&lastOffset==8);
 b.stereo=true;assert(b.updateTransform(batch)&&binds==2);
 b.stereo=false;batch._params[0]._uint=3;
 assert(!b.updateTransform(batch)&&binds==2);
 batch._params[0]._uint=2;assert(b.updateTransform(batch)&&binds==3);
 b.frame._drawCallInfoBuffer->_renderSysmem.size=20;
 assert(!b.updateTransform(batch)&&binds==3); // exact applied bytes, no adjacent region spill
 b.frame._drawCallInfoBuffer->_renderSysmem.size=32;
 batch._currentNamedCall.clear();batch._params[0]._uint=0;
 assert(b.updateTransform(batch)&&binds==4);
 b._currentDraw=-1;assert(!b.updateTransform(batch)&&binds==4);
 b._currentDraw=1;assert(!b.updateTransform(batch)&&binds==4);
 b._currentDraw=0;b._transform._unnamedDrawCallInfoElementCounts.clear();
 assert(!b.updateTransform(batch)&&binds==4);
 b._transform._unnamedDrawCallInfoElementCounts={8};
 b._transform._unnamedDrawCallInfoOffsets[0]=VK_WHOLE_SIZE;
 assert(!b.updateTransform(batch)&&binds==4);
 b._transform._unnamedDrawCallInfoOffsets[0]=32;
 assert(!b.updateTransform(batch)&&binds==4);
 b._transform._unnamedDrawCallInfoOffsets[0]=0;
 batch._params[0]._uint=UINT32_MAX;assert(!b.updateTransform(batch)&&binds==4);
 batch._params[0]._uint=0;b.frame._drawCallInfoBuffer->native.buffer=VK_NULL_HANDLE;
 assert(!b.updateTransform(batch)&&binds==4);
 b.frame._drawCallInfoBuffer.reset();assert(!b.updateTransform(batch)&&binds==4);
 std::cout<<"PASS named/unnamed/stereo DrawCallInfo bounds before bind\n";
}
'''
producer_start=source.index('        bool insideNamedCall',source.index('void VKBackend::transferTransformState('))
producer_end=source.index('        for (auto& data : batch._namedData)',producer_start)
producer='void VKBackend::transfer(const Batch& batch) { std::vector<uint8_t> bufferData; '
producer+='_transform._unnamedDrawCallInfoOffsets.clear(); _transform._unnamedDrawCallInfoElementCounts.clear(); _transform._unnamedDrawCallInfoSourceIndices.clear(); '
producer+=source[producer_start:producer_end]+'}'
code=code.replace('PRODUCTION',extract('static size_t drawCommandInstanceCount(')+'\n'+method+'\n'+producer)
if not baseline:
    assert 'if (!updateTransform(batch))' in source,'caller must skip rejected draw'
with tempfile.TemporaryDirectory(prefix='overte-draw-info-') as temp:
    cpp=Path(temp)/'test.cpp';cpp.write_text(code);binary=Path(temp)/'test'
    subprocess.run(['c++','-std=c++17','-O1','-D_GLIBCXX_ASSERTIONS',str(cpp),'-o',str(binary)],check=True,timeout=40)
    result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=15)
    if baseline:
        assert result.returncode!=0 and ('missing named draw must not bind offset zero' in result.stderr or '__n < this->size()' in result.stderr),result.stderr
        print('EXPECTED BASELINE FAILURE: unchecked DrawCallInfo source or missing-name binding')
    else:
        assert result.returncode==0,result.stderr
        print(result.stdout.strip())
