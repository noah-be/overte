#!/usr/bin/env python3
"""Execute actual observation producers with explicit host GPU/image seams."""
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
backend = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKBackend.cpp").read_text()
pipeline = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKPipelineCache.cpp").read_text()
web = (ROOT / "libraries/entities-renderer/src/RenderableWebEntityItem.cpp").read_text()
coverage = backend[backend.index("static std::string missingDescriptorBindings"):
                   backend.index("static uint64_t iosDiagnosticFingerprint")]
pixels = web[web.index("            quint64 alphaNonzeroPixels"):
             web.index("            QString capturePath;")]
attempt = pipeline[pipeline.index("    overte::ios::observeRender(overte::ios::RenderMetric::pipelineAttempts"):
                   pipeline.index("    os_log_info(OS_LOG_DEFAULT", pipeline.index("    const auto createDetails"))]
creation = pipeline[pipeline.index("    try {\n        result = builder.create();"):
                    pipeline.index("    builder.shaderStages.clear();")]
program = r'''
#include <shared/IOSRenderObservations.h>
#include <algorithm>
#include <cassert>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#define Q_OS_IOS
#define os_log_info(...)
#define os_log_fault(...)
using namespace overte::ios;
using quint64 = uint64_t;
struct Cache { using BindingMap = std::map<unsigned, unsigned>; };
struct VkWriteDescriptorSet { unsigned dstBinding, descriptorCount; };
bool iosRuntimeRenderDiagnosticsEnabled() { return true; }
COVERAGE
struct QColor {
    bool visible;
    int alpha() const { return visible ? 255 : 0; }
    int red() const { return visible ? 100 : 0; }
    int green() const { return 0; } int blue() const { return 0; }
};
struct Image {
    bool transparent;
    int width() const { return 257; } int height() const { return 511; }
    QColor pixelColor(int x, int y) const { return { !transparent && ((x+y)%2==0) }; }
};
void sample(bool transparent) { Image uploadImage { transparent }; PIXELS }
struct Bindings { std::vector<int> bindingDescriptions {1,2}; std::vector<int> attributeDescriptions {1,2,3}; };
struct Reflection { uint64_t descriptorCount() const { return 4; } };
struct Builder {
    bool fail;
    struct { unsigned topology {3}; } inputAssemblyState;
    Bindings vertexInputState;
    int create() { if (fail) { throw std::runtime_error("private shader name"); } return 1; }
};
void make(bool fail) {
    Builder builder {fail};
    struct { Reflection vertexReflection, fragmentReflection; } pipelineLayout;
    auto makePipelineDetails = [](const char*, const char*) { return std::string {}; };
    int result = 0;
    ATTEMPT
    CREATION
    assert(result == 1);
}
uint64_t get(RenderMetric metric) { return renderObservations()[static_cast<size_t>(metric)]; }
int main() {
    sample(true);
    assert(get(RenderMetric::qmlSamples)>0 && get(RenderMetric::qmlSamples)<=65536);
    assert(get(RenderMetric::qmlAlphaSamples)==0 && get(RenderMetric::qmlNonBlackSamples)==0);
    sample(false);
    assert(get(RenderMetric::qmlAlphaSamples)>0 && get(RenderMetric::qmlAlphaSamples)<=get(RenderMetric::qmlSamples));
    reportDescriptorCoverage("fixture", {{0,0},{2,0}}, {{0,1}}, 1);
    assert(get(RenderMetric::descriptorExpected)==2 && get(RenderMetric::descriptorWritten)==1);
    assert(get(RenderMetric::descriptorMissing)==1 && get(RenderMetric::descriptorInvalid)==1);
    reportDescriptorCoverage("fixture", {{0,0},{2,0}}, {{0,1},{2,1}}, 0);
    assert(get(RenderMetric::descriptorMissing)==0 && get(RenderMetric::descriptorInvalid)==0);
    make(false);
    try { make(true); assert(false); } catch (const std::runtime_error&) {}
    assert(get(RenderMetric::pipelineAttempts)==2 && get(RenderMetric::pipelineCreated)==1 && get(RenderMetric::pipelineFailed)==1);
    assert(get(RenderMetric::pipelineVertexBindings)==2 && get(RenderMetric::pipelineVertexAttributes)==3);
    std::vector<std::thread> writers;
    for (int n=0;n<4;++n) { writers.emplace_back([] { for(int i=0;i<10000;++i) observeRender(RenderMetric::entityPackets); }); }
    for (auto& writer:writers) writer.join();
    assert(get(RenderMetric::entityPackets)==40000);
    auto before = renderObservations();
    observeRender(RenderMetric::Count);
    observeRender(RenderMetric::entityPackets, {{RenderMetric::Count, 123}});
    assert(before == renderObservations());
    { auto& state=renderObservationState(); std::lock_guard<std::mutex> lock(state.mutex);
      state.values[static_cast<size_t>(RenderMetric::entityPackets)] = UINT64_MAX; }
    observeRender(RenderMetric::entityPackets);
    assert(get(RenderMetric::entityPackets)==UINT64_MAX);
}
'''
for key, value in (("COVERAGE", coverage), ("PIXELS", pixels), ("ATTEMPT", attempt), ("CREATION", creation)):
    program = program.replace(key, value)
with tempfile.TemporaryDirectory(prefix="ios-render-observation-") as temporary:
    source = pathlib.Path(temporary) / "test.cpp"
    binary = pathlib.Path(temporary) / "test"
    source.write_text(program)
    subprocess.run(["c++", "-std=c++17", "-pthread", "-I" + str(ROOT / "libraries/shared/src"),
                    str(source), "-o", str(binary)], check=True, timeout=60)
    subprocess.run([str(binary)], check=True, timeout=20)
print("PASS actual descriptor/pipeline/pixel producers, bounded concurrent transport; host seams, not native GPU acceptance")
