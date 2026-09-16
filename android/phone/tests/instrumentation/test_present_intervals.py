#!/usr/bin/env python3
"""Run actual Phone presentation telemetry with only Clock/logging adapters.

The production histogram, window accounting, reset logic and thread-local wrapper
are extracted unchanged. Only the Clock alias is replaced. This does not model
EGL/SurfaceFlinger scanout, rendering cost, or the frame-pointer classification.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / 'libraries/display-plugins/src/display-plugins/OpenGLDisplayPlugin.cpp'
ADAPTERS = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdarg>
#include <cstdio>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
#include <string>
#include <thread>
#include <vector>
constexpr uint64_t PHONE_PRESENT_REPORT_INTERVAL_USEC = 10000000;
struct FakeClock {
    using duration = std::chrono::microseconds;
    using rep = duration::rep;
    using period = duration::period;
    using time_point = std::chrono::time_point<FakeClock>;
    static constexpr bool is_steady = true;
    static thread_local int64_t ticks;
    static time_point now() { return time_point(duration(ticks)); }
};
thread_local int64_t FakeClock::ticks = 0;
thread_local std::vector<std::string> logs;
thread_local bool diagnostics = true;
bool phoneLoadingDiagnosticsEnabled() { return diagnostics; }
void capture(const char* format, ...) {
    char buffer[2048]; va_list args; va_start(args,format);
    int n=vsnprintf(buffer,sizeof(buffer),format,args); va_end(args);
    assert(n>=0 && n<int(sizeof(buffer))); logs.emplace_back(buffer);
}
#define PHONE_LOADING(...) do { if (phoneLoadingDiagnosticsEnabled()) capture(__VA_ARGS__); } while(false)
using Record = std::map<std::string,std::string>;
Record record(const std::string& phase, unsigned window, const std::string& stream="") {
    std::vector<Record> matches;
    for(const auto& text:logs) {
        Record values; std::istringstream input(text); std::string word;
        while(input>>word) { auto split=word.find('='); assert(split!=std::string::npos);
            values.emplace(word.substr(0,split),word.substr(split+1)); }
        if(values["phase"]==phase && values["window"]==std::to_string(window) &&
                (stream.empty() || values["stream"]==stream)) matches.push_back(values);
    }
    assert(matches.size()==1); return matches[0];
}
uint64_t value(const Record& r,const char* key) { return std::stoull(r.at(key)); }
'''
TESTS = r'''
void histogramBoundaries() {
    PhoneLoadingIntervalHistogram h;
    assert(h.percentileUpperUsec(50)==0 && h.percentileUpperUsec(99)==0);
    for(uint64_t sample : {0ULL,1ULL,999ULL,1000ULL,1001ULL,50000ULL,50001ULL,
            100000ULL,100001ULL,250000ULL,250001ULL,1000000ULL,1000001ULL}) h.add(sample);
    assert(h.count==13 && h.bins[0]==1 && h.bins[1]==3 && h.bins[2]==1);
    assert(h.bins[1000]==1 && h.bins[1001]==1);
    assert(h.over50ms==7 && h.over100ms==5 && h.over250ms==3 && h.over1000ms==1);
    assert(h.percentileUpperUsec(50)==51000 && h.percentileUpperUsec(95)==1000001);
    h.add(std::numeric_limits<uint64_t>::max());
    assert(h.bins[1001]==2 && h.maximum==std::numeric_limits<uint64_t>::max());
    assert(h.percentileUpperUsec(99)==h.maximum);
    logs.clear(); h.report("boundary",7);
    auto result=record("frame_interval",7,"boundary");
    assert(value(result,"samples")==14 && value(result,"max_us")==h.maximum);
    assert(value(result,"over_1000ms")==2);

    PhoneLoadingIntervalHistogram uniform;
    for(uint64_t sample=1;sample<=100000;++sample) uniform.add(sample);
    assert(uniform.percentileUpperUsec(50)==50000);
    assert(uniform.percentileUpperUsec(95)==95000);
    assert(uniform.percentileUpperUsec(99)==99000);
    // Independent order-statistic oracle checks the advertised upper-bound
    // contract, including ceil rounding and the deliberately coarse overflow.
    std::vector<uint64_t> samples;
    PhoneLoadingIntervalHistogram varied;
    uint32_t seed=1217;
    for(unsigned i=0;i<1001;++i) {
        seed=1664525U*seed+1013904223U;
        uint64_t sample=seed%1400000U; samples.push_back(sample); varied.add(sample);
    }
    std::sort(samples.begin(),samples.end());
    for(unsigned percentile : {50U,95U,99U}) {
        auto exact=samples[(samples.size()*percentile+99)/100-1];
        auto upper=varied.percentileUpperUsec(percentile);
        assert(upper>=exact);
        if(exact<=1000000) assert(upper-exact<1000); else assert(upper==samples.back());
    }
}
void boundaryStall() {
    logs.clear(); FakeClock::ticks=0; PhoneLoadingPresentIntervals s;
    s.record(true);
    for(int64_t i=1;i<=300;++i) { FakeClock::ticks=i*33333; s.record(true); }
    assert(logs.empty()); // No per-frame logging, even near the window edge.
    FakeClock::ticks=12000000; s.record(false); // >2s stall crosses 10s boundary.
    assert(logs.size()==5);
    auto window=record("frame_window",1); auto all=record("frame_interval",1,"all");
    assert(value(window,"elapsed_us")==12000000 && value(window,"swaps")==302);
    assert(value(window,"new_frames")==301 && value(window,"repeated_swaps")==1);
    assert(value(window,"new_age_us")==2000100);
    assert(value(all,"samples")==301 && value(all,"max_us")==2000100);
    assert(value(all,"p99_upper_us")==34000 && value(all,"over_1000ms")==1);
    assert(value(record("frame_interval",1,"repeat_swap"),"samples")==1);
    assert(s.all.count==0 && s.newGap.count==0); // Report clears counts only.
    FakeClock::ticks=12033333; s.record(true);
    assert(s.newGap.count==1 && s.newGap.maximum==2033433); // Prior-window anchor retained.
    FakeClock::ticks=22000000; s.record(false);
    assert(logs.size()==10);
    auto gap=record("frame_interval",2,"new_gap");
    assert(value(gap,"samples")==1 && value(gap,"max_us")==2033433);
    assert(value(gap,"over_1000ms")==1);
    assert(value(record("frame_window",2),"new_age_us")==9966667);
}
void repeatsAndMissingAnchor() {
    logs.clear(); FakeClock::ticks=0; PhoneLoadingPresentIntervals s;
    s.record(true);
    for(int64_t i=1;i<=100;++i) { FakeClock::ticks=i*100000; s.record(false); }
    assert(logs.size()==5);
    auto window=record("frame_window",1);
    assert(value(window,"new_anchor")==1 && value(window,"new_age_us")==10000000);
    assert(value(window,"new_frames")==1 && value(window,"repeated_swaps")==100);
    assert(value(record("frame_interval",1,"new_gap"),"samples")==0);
    assert(value(record("frame_interval",1,"repeat_swap"),"samples")==100);
    FakeClock::ticks=10100000; s.record(true);
    assert(s.newGap.maximum==10100000); // Repeated swaps never refresh the new-frame anchor.
    logs.clear(); FakeClock::ticks=0; PhoneLoadingPresentIntervals noNew;
    noNew.record(false); FakeClock::ticks=10000000; noNew.record(false);
    window=record("frame_window",1);
    assert(value(window,"new_anchor")==0 && value(window,"new_age_us")==0);
    assert(value(record("frame_interval",1,"new_gap"),"samples")==0);
}
void optInAndThreadLocal() {
    logs.clear(); diagnostics=false; FakeClock::ticks=0; recordPhoneLoadingPresentInterval(true);
    FakeClock::ticks=20000000; recordPhoneLoadingPresentInterval(false); assert(logs.empty());
    diagnostics=true; FakeClock::ticks=30000000; recordPhoneLoadingPresentInterval(true);
    FakeClock::ticks=40000000; recordPhoneLoadingPresentInterval(false);
    assert(logs.size()==5 && value(record("frame_window",1),"elapsed_us")==10000000);
    std::thread other([] {
        FakeClock::ticks=0; recordPhoneLoadingPresentInterval(true); assert(logs.empty());
        FakeClock::ticks=10000000; recordPhoneLoadingPresentInterval(false);
        assert(logs.size()==5 && value(record("frame_window",1),"elapsed_us")==10000000);
    }); other.join();
    assert(logs.size()==5);
}
int main() {
    histogramBoundaries(); boundaryStall(); repeatsAndMissingAnchor(); optInAndThreadLocal();
    std::cout << "PASS actual presentation telemetry: histogram boundaries/quantiles/overflow, cross-window stalls, repeats/new-gap/new-age, opt-in and thread-local isolation\n";
}
'''


def main():
    source=SOURCE.read_text()
    start=source.index('struct PhoneLoadingIntervalHistogram {')
    end=source.index('\n}\n}',source.index('void recordPhoneLoadingPresentInterval(',start))+2
    body=source[start:end]
    alias='using Clock = std::chrono::steady_clock;'
    assert body.count(alias)==1
    body=body.replace(alias,'using Clock = FakeClock;')
    with tempfile.TemporaryDirectory(prefix='overte-present-intervals-') as directory:
        cpp=Path(directory)/'test.cpp'; exe=Path(directory)/'test'
        cpp.write_text(ADAPTERS+body+TESTS)
        subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-O2','-pthread',str(cpp),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
    swap=source.index('void OpenGLDisplayPlugin::swapBuffers()')
    assert source.index('context->swapBuffers();',swap) < source.index('recordPhoneLoadingPresentInterval(_phonePresentHasNewFrame);',swap)
    print('LIMIT: fake clock/logging; swap-return timing only, no EGL or physical scanout validation.')


if __name__=='__main__': main()
