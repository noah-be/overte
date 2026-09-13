"""Execute real submit telemetry with a captured os_log transport, no GPU proof."""
import os
import resource
from pathlib import Path
import subprocess
import tempfile

resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

ROOT = Path(__file__).resolve().parents[2]
baseline = os.environ.get("OVERTE_SUBMIT_PROGRESS_BASELINE")
path = "libraries/gpu-vk/src/gpu/vk/VKBackend.cpp"
source = subprocess.check_output(["git", "show", baseline + ":" + path], cwd=ROOT, text=True) if baseline else (ROOT / path).read_text()
start = source.index("void VKBackend::persistIOSDiagnosticSubmit(")
brace = source.index("{", start)
end, depth = brace + 1, 1
while depth:
    depth += (source[end] == "{") - (source[end] == "}")
    end += 1
method = source[start:end]
code = r'''
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstdint>
#include <set>
#include <string>
#include <thread>
#include <vector>
#include <iostream>
std::vector<std::string> logs;
template<class... Args> void capture(int,const char* format,Args... args) {
    std::string f=format;
    for(size_t pos;(pos=f.find("%{public}"))!=std::string::npos;) f.replace(pos,9,"%");
    char output[2048]; int n=std::snprintf(output,sizeof(output),f.c_str(),args...);
    assert(n>=0 && size_t(n)<sizeof(output)); logs.emplace_back(output);
}
#define OS_LOG_DEFAULT 0
#define os_log_info(...) capture(__VA_ARGS__)
namespace overte { namespace security {
enum class DiagnosticEvent { Redacted };
const char* diagnosticEvent(DiagnosticEvent) { return "OVT_REDACTED"; }
}}
struct Evidence {
    bool armed=true,committed=false;
    int expected=10,renderables=9,scene=8,drawn=7;
    bool capacityExceeded=false;
    uint64_t acceptedPresentCalls=33,rejectedPresentCalls=2;
    uint32_t lastPresentedFrame=44;
};
Evidence evidence;
Evidence iosRuntimeEntityEvidenceSnapshot() { return evidence; }
bool iosRuntimeRenderDiagnosticsEnabled() { return true; }
struct Settings {
    template<class T> void setValue(const char*,const T&) {}
    void sync() {}
};
Settings iosVulkanDiagnosticSettings() { return {}; }
const std::set<std::string>& toQStringList(const std::set<std::string>& s) { return s; }
struct QString { static std::string number(uint64_t n) { return std::to_string(n); } };
struct VKBackend {
    uint64_t _frameCounter=55;
    uint64_t _iosScissorEnabledDraws=12,_iosScissorDisabledDraws=13,_iosScissorInvalidDraws=14;
    std::set<std::string> _iosCurrentUntrustedPipelines {"PRIVATE_PIPELINE:https://secret.invalid/private-content"};
    std::set<std::string> _iosSubmittedUntrustedPipelines;
    bool _iosPersistSubmitCandidates=true;
    void persistIOSDiagnosticSubmit(uint64_t);
};
METHOD
std::vector<std::string> progress() {
    std::vector<std::string> result;
    for(const auto& line:logs) {
        assert(line.find("PRIVATE_PIPELINE")==std::string::npos);
        assert(line.find("https:")==std::string::npos);
        if(line.find("OVT_IOS_RENDER_SUBMIT_V1 ")==0) result.push_back(line);
        else assert(line=="OVT_REDACTED");
    }
    return result;
}
int main() {
    VKBackend backend;
    backend.persistIOSDiagnosticSubmit(1);
    auto lines=progress();
    assert(lines.size()==1 && "missing numerical submit progress");
    assert(lines[0]=="OVT_IOS_RENDER_SUBMIT_V1 submit=1 frame=55 presentAccepted=33 presentRejected=2 lastPresentedFrame=44 scissorEnabled=12 scissorDisabled=13 scissorInvalid=14 evidenceArmed=1 evidenceCommitted=0 expected=10 renderables=9 scene=8 drawn=7 capacityExceeded=0");
    assert(backend._iosScissorEnabledDraws==0 && backend._iosScissorDisabledDraws==0 && backend._iosScissorInvalidDraws==0);
    backend.persistIOSDiagnosticSubmit(2);
    assert(progress().size()==1 && "submit logs are not rate limited");
    std::this_thread::sleep_for(std::chrono::milliseconds(5100));
    evidence={}; evidence.armed=false; evidence.capacityExceeded=true;
    backend._iosCurrentUntrustedPipelines.clear();
    backend.persistIOSDiagnosticSubmit(UINT64_MAX);
    lines=progress(); assert(lines.size()==2);
    assert(lines.back().find("submit=18446744073709551615 ")!=std::string::npos);
    assert(lines.back().find("scissorEnabled=0 scissorDisabled=0 scissorInvalid=0")!=std::string::npos);
    assert(lines.back().find("evidenceArmed=0")!=std::string::npos);
    assert(lines.back().find("capacityExceeded=1")!=std::string::npos);
    std::cout << "PASS: production numeric submit progress; exact schema; uint64 width; 5s rate limit; reset counters; private pipeline redaction\n";
}
'''.replace("METHOD", method)
with tempfile.TemporaryDirectory(prefix="overte-submit-progress-") as temp:
    cpp = Path(temp) / "test.cpp"
    cpp.write_text(code)
    binary = Path(temp) / "test"
    subprocess.run(["c++", "-std=c++17", "-O1", "-g", str(cpp), "-o", str(binary)], check=True, timeout=40)
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
    if baseline:
        assert result.returncode != 0 and "missing numerical submit progress" in result.stderr, result.stderr
        print("EXPECTED BASELINE FAILURE: redaction-only submit progress")
    else:
        assert result.returncode == 0, result.stderr
        print(result.stdout.strip())
