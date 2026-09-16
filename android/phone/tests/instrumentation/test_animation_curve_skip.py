#!/usr/bin/env python3
"""Compile the production skip block and exercise caller scope and seek bounds."""
from pathlib import Path
import subprocess
import tempfile
repo = Path(__file__).resolve().parents[4]
s = (repo/'libraries/model-serializers/src/FBXSerializer_Node.cpp').read_text()
a = s.index('    // The HFM animation importer consumes only KeyValueFloat')
b = s.index('    for (quint32 i = 0; i < propertyCount;', a)
block = s[a:b]
fixture = r'''
#include <cassert>
#include <limits>
#include <string>
#include <cstdint>
struct Device {
    bool sequential = false, seekWorks = true;
    int64_t length = 1000, current = 50;
    bool isSequential() { return sequential; }
    int64_t size() { return length; }
    bool seek(int64_t p) { if (!seekWorks) return false; current=p; return true; }
};
struct Stream { Device d; Device* device() { return &d; } };
struct FBXNode { std::string name; };
FBXNode run(Stream& in, int& position, int64_t endOffset, FBXNode node,
            bool skipUnusedAnimationCurveData, bool animationCurveChild) {
''' + block + r'''
    return node;
}
void check(const std::string& name, bool enabled, bool curveChild, bool expected,
           int64_t end=100, bool sequential=false, bool seekWorks=true, int64_t length=1000) {
    Stream in; in.d.sequential=sequential; in.d.seekWorks=seekWorks; in.d.length=length;
    int position=50;
    auto node=run(in,position,end,{name},enabled,curveChild);
    assert(node.name.empty()==expected);
    assert(position==(expected?end:50));
    assert(in.d.current==(expected?end:50));
}
int main() {
    for (auto name : {"KeyTime", "KeyAttrFlags", "KeyAttrDataFloat", "KeyAttrRefCount"}) {
        check(name,true,true,true);
        check(name,false,true,false);
        check(name,true,false,false);
        check(name,true,true,false,49);
        check(name,true,true,false,1001);
        check(name,true,true,false,100,true);
        check(name,true,true,false,100,false,false);
        check(name,true,true,false,int64_t(std::numeric_limits<int>::max())+1,false,true,
              int64_t(std::numeric_limits<int>::max())+100);
    }
    check("KeyValueFloat",true,true,false);
    check("Default",true,true,false);
    check("Vertices",true,true,false);
    check("KeyTime",true,true,true,50);
}
'''
with tempfile.TemporaryDirectory() as tmp:
    cpp=Path(tmp)/'test.cpp';cpp.write_text(fixture);exe=Path(tmp)/'test'
    subprocess.run(['c++','-std=c++14','-O2',str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
print('PASS: production skip block preserves required fields and full-parser callers; malformed offsets, sequential devices and failed seeks fall back')
