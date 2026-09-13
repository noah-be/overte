"""Execute the production framebuffer updater with a recording Vulkan boundary.

No native/GPU acceptance. Set OVERTE_FRAMEBUFFER_BASELINE to a git revision for
an old-source negative control; each case runs separately to expose each defect.
"""
import os
from pathlib import Path
import shutil
import resource
import subprocess
import tempfile

# Negative controls intentionally assert; do not create crash/core artifacts.
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
ROOT = Path(__file__).resolve().parents[2]
path = 'libraries/gpu-vk/src/gpu/vk/VKFramebuffer.cpp'
baseline = os.environ.get('OVERTE_FRAMEBUFFER_BASELINE')
source = (subprocess.check_output(['git', 'show', baseline + ':' + path], cwd=ROOT, text=True)
          if baseline else (ROOT / path).read_text())
start = source.index('void gpu::vk::VKFramebuffer::update()')
brace = source.index('{', start)
end, depth = brace + 1, 1
while depth:
    depth += (source[end] == '{') - (source[end] == '}')
    end += 1
update = source[start:end]

code = r'''
#include <vulkan/vulkan.h>
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <memory>
#include <set>
#include <string>
#include <vector>
#define Q_ASSERT(x) assert(x)
#define VK_CHECK_RESULT(x) assert((x) == VK_SUCCESS)
using Handle = uintptr_t;
template<class T> T handle(Handle value) { return reinterpret_cast<T>(value); }
template<class T> Handle number(T value) { return reinterpret_cast<Handle>(value); }
Handle nextHandle = 100;
std::set<Handle> alive;
template<class T> T createHandle() { alive.insert(++nextHandle); return handle<T>(nextHandle); }
void destroy(Handle h) { assert(alive.erase(h) == 1); }
void vkDestroyFramebuffer(VkDevice, VkFramebuffer f, const VkAllocationCallbacks*) { destroy(number(f)); }
namespace gpu {
enum class TextureUsageType { RENDERBUFFER };
struct Texture {
    unsigned id, slices = 1; VkImageViewType target = VK_IMAGE_VIEW_TYPE_2D;
    TextureUsageType getUsageType() const { return TextureUsageType::RENDERBUFFER; }
    unsigned getWidth() const { return 32; }
    unsigned getHeight() const { return 32; }
    unsigned getNumSlices() const { return slices; }
    VkFormat getTexelFormat() const { return VK_FORMAT_R8G8B8A8_UNORM; }
};
using TexturePointer = std::shared_ptr<Texture>;
struct Framebuffer {
    struct View { TexturePointer _texture; uint32_t _subresource = 0; };
    std::vector<View> colors; TexturePointer depth; uint32_t depthSlice = 0;
    std::vector<unsigned> colorStamps {1}; unsigned depthStamp = 1;
    bool hasColor() const { return std::any_of(colors.begin(), colors.end(), [](const View& v){return bool(v._texture);}); }
    bool hasDepthStencil() const { return bool(depth); }
    const std::vector<View>& getRenderBuffers() const { return colors; }
    const TexturePointer& getDepthStencilBuffer() const { return depth; }
    uint32_t getDepthStencilBufferSubresource() const { return depthSlice; }
    const std::vector<unsigned>& getColorStamps() const { return colorStamps; }
    unsigned getDepthStamp() const { return depthStamp; }
};
namespace vk {
struct VKTexture { Texture& _gpuObject; VkImageViewType _target; };
struct Recycler {
    std::vector<Handle> framebuffers, passes, views;
    void trashVkFramebuffer(VkFramebuffer h) { framebuffers.push_back(number(h)); }
    void trashVkRenderPass(VkRenderPass h) { passes.push_back(number(h)); }
    void trashVkImageView(VkImageView h) { views.push_back(number(h)); }
    void retire(bool fenceSignaled) {
        assert(fenceSignaled);
        for (auto h : framebuffers) destroy(h);
        for (auto h : passes) destroy(h);
        for (auto h : views) destroy(h);
        framebuffers.clear(); passes.clear(); views.clear();
    }
};
struct Context { struct Device { VkDevice logicalDevice {}; } dev; Device* device = &dev; Recycler recycler; };
VkFormat evalTexelFormatInternal(VkFormat f, Context&) { return f; }
struct VKBackend {
    Context context;
    struct Frame { std::vector<VkRenderPass> _renderPasses; } frame;
    Frame* _currentFrame = &frame;
    std::vector<std::unique_ptr<VKTexture>> textures;
    Context& getContext() { return context; }
    VKTexture* syncGPUObject(const TexturePointer& t) {
        textures.emplace_back(new VKTexture{*t, t->target}); return textures.back().get();
    }
};
struct VKFramebuffer {
    std::weak_ptr<VKBackend> _backend; Framebuffer& _gpuObject;
    VkRenderPass vkRenderPass {}; VkFramebuffer vkFramebuffer {};
    struct Attachment { VkImageView view; unsigned texture, slice; VkImageUsageFlags usage; };
    std::vector<Attachment> attachments;
    std::vector<unsigned> _colorStamps; unsigned _depthStamp = 0;
    struct VKAttachmentCreateInfo {
        uint32_t width, height, layerCount; VkFormat format;
        VkImageUsageFlags usage; VkSampleCountFlagBits imageSampleCount;
    };
    VKFramebuffer(const std::shared_ptr<VKBackend>& b, Framebuffer& f) : _backend(b), _gpuObject(f) {}
    void update();
    uint32_t addAttachment(VKAttachmentCreateInfo ci, VKTexture* t, uint32_t slice = 0) {
        attachments.push_back({createHandle<VkImageView>(), t->_gpuObject.id, slice, ci.usage});
        return attachments.size()-1;
    }
    VkResult createFramebuffer() {
        vkRenderPass = createHandle<VkRenderPass>(); vkFramebuffer = createHandle<VkFramebuffer>();
        return VK_SUCCESS;
    }
};
}}
'''
main = r'''
using namespace gpu;
using namespace gpu::vk;
int main(int argc, char** argv) {
    assert(argc == 2); std::string mode = argv[1];
    auto backend = std::make_shared<VKBackend>();
    auto c1 = std::make_shared<Texture>(Texture{1}); auto c2 = std::make_shared<Texture>(Texture{2});
    auto d1 = std::make_shared<Texture>(Texture{3}); auto d2 = std::make_shared<Texture>(Texture{4});
    Framebuffer f; f.colors = {{c1, 0}}; f.depth = d1;
    VKFramebuffer vk(backend, f); vk.update();
    assert(vk.attachments.size() == 2);
    const auto old = alive;
    const auto oldFramebuffer = number(vk.vkFramebuffer);
    if (mode == "color" || mode == "lifetime") { f.colors[0]._texture = c2; ++f.colorStamps[0]; }
    else if (mode == "depth") { f.depth = d2; ++f.depthStamp; }
    else if (mode == "remove-depth") { f.depth.reset(); ++f.depthStamp; }
    else if (mode == "remove-color") { f.colors[0]._texture.reset(); ++f.colorStamps[0]; }
    else if (mode == "remove-both-change-color") {
        f.depth.reset(); ++f.depthStamp; f.colors[0]._texture = c2; ++f.colorStamps[0];
    } else if (mode == "array") {
        c2->slices = 4; c2->target = VK_IMAGE_VIEW_TYPE_2D_ARRAY;
        d2->slices = 4; d2->target = VK_IMAGE_VIEW_TYPE_2D_ARRAY;
        f.colors[0] = {c2, 2}; f.depth = d2; f.depthSlice = 1;
        ++f.colorStamps[0]; ++f.depthStamp;
    } else { return 2; }
    vk.update();
    if (mode == "lifetime") {
        // A recorded draw keeps all old handles alive before the submission
        // fence. The next frame's cleanup is represented by explicit retire.
        for (auto h : old) assert(alive.count(h) == 1);
        assert(alive.count(oldFramebuffer) == 1);
        // A second update in the same recorded frame must retain both old
        // generations and retire each exactly once after completion.
        const auto secondGeneration = alive;
        f.depth = d2; ++f.depthStamp; vk.update();
        for (auto h : secondGeneration) assert(alive.count(h) == 1);
        backend->context.recycler.retire(true);
        for (auto h : secondGeneration) assert(alive.count(h) == 0);
        for (auto h : old) assert(alive.count(h) == 0);
        assert(alive.count(number(vk.vkFramebuffer)) == 1);
        assert(alive.count(number(vk.vkRenderPass)) == 1);
        for (const auto& a : vk.attachments) assert(alive.count(number(a.view)) == 1);
        backend->context.recycler.retire(true); // No duplicate destruction.
    } else {
        std::vector<unsigned> expected;
        for (const auto& c : f.colors) if (c._texture) expected.push_back(c._texture->id);
        if (f.depth) expected.push_back(f.depth->id);
        assert(vk.attachments.size() == expected.size());
        for (size_t i = 0; i < expected.size(); ++i) assert(vk.attachments[i].texture == expected[i]);
        if (mode == "array") { assert(vk.attachments[0].slice == 2); assert(vk.attachments[1].slice == 1); }
        if (f.depth) assert(vk.attachments.back().usage == VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT);
    }
    assert(vk._colorStamps == f.colorStamps); assert(vk._depthStamp == f.depthStamp);
    std::cout << mode << " PASS\n";
}
'''
cases = ['color', 'depth', 'remove-depth', 'remove-color', 'remove-both-change-color', 'array', 'lifetime']
compiler = os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++')
if not compiler:
    raise SystemExit('C++ compiler required')
with tempfile.TemporaryDirectory(prefix='overte-framebuffer-test-') as directory:
    temp = Path(directory)
    cpp, binary = temp/'test.cpp', temp/'test'
    cpp.write_text(code + '\n' + update + '\n' + main)
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', str(cpp), '-o', str(binary)], check=True, timeout=60)
    failures = []
    for case in cases:
        result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=10)
        if result.returncode:
            failures.append(case)
            print(case + ' FAIL: ' + result.stderr.strip())
        else:
            print(result.stdout.strip())
    if failures:
        raise SystemExit('Failed production cases: ' + ', '.join(failures))
print('Framebuffer attachment and fence-retirement regression PASS (host mock, not GPU acceptance)')
