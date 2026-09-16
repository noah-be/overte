#!/usr/bin/env python3
"""Compile portable batch capture and shader decoding at the uint16 boundary.

Only math, Qt logging and buffer-upload boundaries are mocked. This is a source
regression, not evidence of a native shader compiler or GPU execution.
"""
from pathlib import Path
import re
import resource
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[4]
batch = (ROOT / 'libraries/gpu/src/gpu/Batch.cpp').read_text()
header = (ROOT / 'libraries/gpu/src/gpu/Batch.h').read_text()
shader = (ROOT / 'libraries/gpu/src/gpu/Transform.slh').read_text()
def extract(source, signature):
    start = source.index(signature)
    pos = source.index('{', start)
    depth = 1
    end = pos + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]
info = extract(header, 'class DrawCallInfo {') + ';'
capture = '\n'.join(extract(batch, signature) for signature in (
    'bool Batch::captureDrawCallInfoImpl()', 'bool Batch::captureDrawCallInfo()',
    'void Batch::captureNamedDrawCallInfo(', 'void Batch::draw('))
process = extract(header, 'void process(Batch& batch)')
ssbo_index = re.search(r'_object\[([^]]+)\]', shader[shader.index('TransformObject getTransformObject()'):]).group(1)
texel_index = re.search(r'int offset = ([^;]+);', shader).group(1)
for command in ('draw', 'drawIndexed', 'drawInstanced', 'drawIndexedInstanced', 'multiDrawIndirect', 'multiDrawIndexedIndirect'):
    method = extract(batch, 'void Batch::' + command + '(')
    assert method.index('if (!captureDrawCallInfo())') < method.index('ADD_COMMAND(')
code = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <string>
#include <vector>
using uint32 = uint32_t;
using Primitive = uint32_t;
namespace glm { int inverse(int n) { return n; } }
#define Q_UNUSED(x) (void)x;
#define qCWarning(x) std::cerr
#define ADD_COMMAND(x) _commands.push_back(COMMAND_##x); _commandOffsets.push_back(_params.size())
struct Batch {
INFO
using DrawCallInfoBuffer = std::vector<DrawCallInfo>;
struct TransformObject { int _model{}, _previousModel{}, _modelInverse{}, _previousModelInverse{}; };
struct Model { void getMatrix(int& out) { out = 42; } } _currentModel, _previousModel;
struct NamedBatchData {
 std::function<void(Batch&, NamedBatchData&)> function;
 DrawCallInfoBuffer drawCallInfos;
 bool invalidTransformIndex = false;
 PROCESS
};
enum Command { COMMAND_draw, COMMAND_drawIndexed, COMMAND_drawInstanced, COMMAND_drawIndexedInstanced,
 COMMAND_multiDrawIndirect, COMMAND_multiDrawIndexedIndirect, COMMAND_startNamedCall, COMMAND_stopNamedCall };
struct Param { uint32_t _uint; Param(uint32_t n) : _uint(n) {} };
std::vector<Command> _commands;
std::vector<size_t> _commandOffsets;
std::vector<Param> _params;
std::vector<TransformObject> _objects;
std::vector<DrawCallInfo> _drawCallInfos;
std::map<std::string, NamedBatchData> _namedData;
std::string _currentNamedCall;
bool _invalidModel = true;
uint16_t _drawcallUniform=0, _drawcallUniformReset=0;
DrawCallInfoBuffer& getDrawCallInfoBuffer() { return _currentNamedCall.empty() ? _drawCallInfos : _namedData[_currentNamedCall].drawCallInfos; }
const auto& getCommands() const { return _commands; }
const auto& getCommandOffsets() const { return _commandOffsets; }
void validateDrawState() {}
bool captureDrawCallInfoImpl(); bool captureDrawCallInfo(); void captureNamedDrawCallInfo(std::string);
void draw(Primitive, uint32, uint32);
};
static_assert(sizeof(Batch::DrawCallInfo)==4);
CAPTURE
int main() {
 for (uint32_t index : {32767U, 32768U, 65535U}) {
  Batch batch; batch._objects.resize(index); batch._drawcallUniform=0xa55a;
  batch.draw(0,3,0);
  assert(batch._objects.size()==index+1 && batch._drawCallInfos.back().index==index);
  assert(batch._drawCallInfos.back().user==0xa55a && batch._drawcallUniform==0);
  struct { int x; } _drawCallInfo{static_cast<int16_t>(index)};
  assert((SSBO_INDEX)==index && (TEXEL_INDEX)==16*index);
 }
 Batch overflow; overflow._objects.resize(65536); overflow._drawcallUniform=23;
 overflow.draw(0,3,0);
 assert(overflow._objects.size()==65536 && overflow._drawCallInfos.empty());
 assert(overflow._commands.empty() && overflow._params.empty() && overflow._drawcallUniform==0);
 overflow.captureNamedDrawCallInfo("group");
 assert(overflow._namedData["group"].invalidTransformIndex);
 bool called=false; auto& group=overflow._namedData["group"];
 group.function=[&](Batch&, Batch::NamedBatchData&) { called=true; };
 group.process(overflow); assert(!called);
 // Reuse of the last representable transform remains valid.
 overflow._invalidModel=false; overflow.draw(0,3,0);
 assert(overflow._drawCallInfos.back().index==65535);
 std::cout << "PASS DrawCallInfo signed decode, boundary capture, overflow and named-batch rejection\n";
}
'''
for key, value in [('INFO',info), ('PROCESS',process), ('CAPTURE',capture),
 ('SSBO_INDEX',ssbo_index), ('TEXEL_INDEX',texel_index)]:
    code = code.replace(key, value)
with tempfile.TemporaryDirectory(prefix='overte-object-index-') as tmp:
    path=Path(tmp)/'test.cpp'; binary=Path(tmp)/'test'
    path.write_text(code)
    subprocess.run(['c++','-std=c++17','-O1','-D_GLIBCXX_ASSERTIONS',str(path),'-o',str(binary)],check=True,timeout=40)
    subprocess.run([str(binary)],check=True,timeout=15)
    mutations = {
        'signed-shader-index': code.replace('_drawCallInfo.x & 0xffff', '_drawCallInfo.x'),
        'wrapped-capture-index': code.replace('if ((_invalidModel && _objects.size()', 'if ((false && _invalidModel && _objects.size()'),
        'unchecked-named-process': code.replace('function && !invalidTransformIndex', 'function'),
    }
    for name, mutated in mutations.items():
        assert mutated != code, name
        path.write_text(mutated)
        subprocess.run(['c++','-std=c++17','-O1','-D_GLIBCXX_ASSERTIONS',str(path),'-o',str(binary)],check=True,timeout=40)
        result = subprocess.run([str(binary)],capture_output=True,text=True,timeout=15)
        assert result.returncode != 0 and 'Assertion' in result.stderr, (name, result.stderr)
        print('EXPECTED REGRESSION FAILURE:', name)
