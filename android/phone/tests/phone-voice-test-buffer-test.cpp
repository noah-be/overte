#include "../../../libraries/audio-client/src/PhoneVoiceTestBuffer.h"
#include <cassert>
#include <string>
static std::string step(PhoneVoiceTestBuffer& b, const std::string& in, size_t n) {
    auto out=b.process(in.data(),in.size(),n); return {out.begin(),out.end()};
}
int main() {
    PhoneVoiceTestBuffer b;
    assert(step(b,"ab",5)==std::string(2,0));
    assert(step(b,"cdef",5)==std::string(4,0));
    // Loud feedback during playback must never enter the recording.
    assert(step(b,"ZZ",5)=="ab");
    assert(step(b,"ZZZZ",5)==std::string("cde\0",4));
    assert(step(b,"ZZ",5)==std::string(2,0));
    b.reset();
    assert(step(b,"xy",2)==std::string(2,0));
    assert(step(b,"ZZ",2)=="xy");
    // Format/duration changes discard old recorded data.
    assert(step(b,"123",3)==std::string(3,0));
    assert(step(b,"ZZZ",3)=="123");
    assert(step(b,"x",0)==std::string(1,0));
    assert(step(b,"x",17*1024*1024)==std::string(1,0));
}
