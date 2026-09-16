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
    // Low-level PCM receives bounded gain without changing capture isolation.
    b.reset();
    const int16_t quiet[] = { 100, -100, 0, 50 };
    auto silent = b.process(reinterpret_cast<const char*>(quiet), sizeof(quiet), sizeof(quiet), true);
    assert(silent == std::vector<char>(sizeof(quiet), 0));
    auto amplified = b.process(reinterpret_cast<const char*>(quiet), sizeof(quiet), sizeof(quiet), true);
    int16_t result[4]; std::memcpy(result, amplified.data(), sizeof(result));
    assert(result[0] == 3200 && result[1] == -3200 && result[2] == 0 && result[3] == 1600);
    b.reset();
    const int16_t loud[] = { 32767, -32768 };
    b.process(reinterpret_cast<const char*>(loud), sizeof(loud), sizeof(loud), true);
    auto unchanged = b.process(reinterpret_cast<const char*>(loud), sizeof(loud), sizeof(loud), true);
    assert(std::memcmp(unchanged.data(), loud, sizeof(loud)) == 0);
    b.reset();
    const int16_t zero[] = { 0, 0 };
    b.process(reinterpret_cast<const char*>(zero), sizeof(zero), sizeof(zero), true);
    assert(b.process(reinterpret_cast<const char*>(zero), sizeof(zero), sizeof(zero), true)
        == std::vector<char>(sizeof(zero), 0));
}
