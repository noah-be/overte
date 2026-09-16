"""Execute production strict-upload barriers at a recording Vulkan boundary.

No native/GPU acceptance. OVERTE_TEXTURE_SYNC_BASELINE selects old source.
"""
import os
import resource
from pathlib import Path
import subprocess
import tempfile

resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

ROOT = Path(__file__).resolve().parents[2]
baseline = os.environ.get("OVERTE_TEXTURE_SYNC_BASELINE")
path = "libraries/gpu-vk/src/gpu/vk/VKTexture.cpp"
source = subprocess.check_output(["git", "show", baseline + ":" + path], cwd=ROOT, text=True) if baseline else (ROOT / path).read_text()


def function(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    end, depth = brace + 1, 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


transfer = function(source, "void VKStrictResourceTexture::transfer(")
# Execute the actual copy/barrier/submission/cleanup tail. Only CPU staging
# preparation is replaced; sampler and view creation use the complete method.
tail = transfer[transfer.index("    VkImageSubresourceRange subresourceRange"):]
post = function(source, "void VKStrictResourceTexture::postTransfer(")
ktx_release = function((ROOT / "libraries/gpu/src/gpu/Texture_ktx.cpp").read_text(), "void KtxStorage::releaseOpenKtxFiles(")
layout_helper = function((ROOT / "libraries/vk/src/vk/VulkanTools.cpp").read_text(), "void setImageLayout(")
# The recording boundary below models synchronous completion. Keep that model
# tied to the real submission helper and the shared-family queue identity.
flush = function((ROOT / "libraries/vk/src/vk/VulkanDevice.cpp").read_text(), "void VulkanDevice::flushCommandBuffer(")
assert flush.index("vkQueueSubmit(") < flush.index("vkWaitForFences(") < flush.index("vkFreeCommandBuffers(")
context = (ROOT / "libraries/vk/src/vk/Context.cpp").read_text()
for role in ("graphics", "transfer"):
    assert f"vkGetDeviceQueue(device->logicalDevice, device->queueFamilyIndices.{role}, 0, &{role}Queue)" in context
code = r'''
#include <vulkan/vulkan.h>
#include <cassert>
#include <cstdint>
#include <vector>
#include <iostream>
#include <cstring>
#include <memory>
#include <mutex>
struct Barrier { VkCommandBuffer command; VkPipelineStageFlags src,dst; VkImageMemoryBarrier image; };
std::vector<Barrier> barriers;
unsigned uploads=0, flushes=0, destroyed=0, freed=0, samplers=0, views=0, graphicsCommands=0;
bool uploadComplete=false;
uint32_t expectedMips=0, expectedLayers=0;
VkCommandBuffer copyHandle=reinterpret_cast<VkCommandBuffer>(1);
VkCommandBuffer graphicsHandle=reinterpret_cast<VkCommandBuffer>(2);
#define VK_CHECK_RESULT(x) assert((x)==VK_SUCCESS)
void vkCmdPipelineBarrier(VkCommandBuffer cmd,VkPipelineStageFlags src,VkPipelineStageFlags dst,VkDependencyFlags,
                          uint32_t,const VkMemoryBarrier*,uint32_t,const VkBufferMemoryBarrier*,uint32_t n,const VkImageMemoryBarrier* b) {
    assert(n==1); barriers.push_back({cmd,src,dst,*b});
    if(cmd==graphicsHandle) assert(uploadComplete);
}
void vkCmdCopyBufferToImage(VkCommandBuffer,VkBuffer,VkImage,VkImageLayout layout,uint32_t,const VkBufferImageCopy*) {
    assert(layout==VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL); ++uploads;
}
void vkDestroyBuffer(VkDevice,VkBuffer,const VkAllocationCallbacks*) { assert(uploadComplete); ++destroyed; }
void vkFreeMemory(VkDevice,VkDeviceMemory,const VkAllocationCallbacks*) { assert(uploadComplete); ++freed; }
VkResult vkCreateSampler(VkDevice,const VkSamplerCreateInfo* info,const VkAllocationCallbacks*,VkSampler*) {
    assert(uploadComplete); assert(info->maxLod==float(expectedMips-1)); ++samplers; return VK_SUCCESS;
}
VkResult vkCreateImageView(VkDevice,const VkImageViewCreateInfo* info,const VkAllocationCallbacks*,VkImageView*) {
    assert(uploadComplete); assert(info->subresourceRange.levelCount==expectedMips);
    assert(info->subresourceRange.layerCount==expectedLayers); ++views; return VK_SUCCESS;
}
namespace vks { namespace initializers {
VkImageMemoryBarrier imageMemoryBarrier() { VkImageMemoryBarrier b{}; b.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER; return b; }
} namespace tools { LAYOUT_HELPER } }
struct Device {
    struct { uint32_t transfer=0, graphics=0; } queueFamilyIndices;
    VkDevice logicalDevice{};
    VkCommandPool transferCommandPool{},graphicsCommandPool{};
    VkCommandBuffer createCommandBuffer(VkCommandPool,VkCommandBufferLevel,bool) { ++graphicsCommands; return graphicsHandle; }
    void flushCommandBuffer(VkCommandBuffer cmd,VkQueue,VkCommandPool) {
        if(cmd==copyHandle) uploadComplete=true;
        else assert(uploadComplete);
        ++flushes;
    }
};
struct VKBackend {
    struct Context { Device* device; VkQueue transferQueue{},graphicsQueue{}; } context;
    Context& getContext() { return context; }
};
namespace storage { struct FileStorage { std::vector<char> mappedOrFallbackBytes = std::vector<char>(4096); }; }
struct Texture {
    struct KtxStorage {
        static std::vector<std::pair<std::shared_ptr<storage::FileStorage>, std::shared_ptr<std::mutex>>> _cachedKtxFiles;
        static std::mutex _cachedKtxFilesMutex;
        static void releaseOpenKtxFiles();
    };
    enum { TEX_2D, TEX_CUBE };
    int type=TEX_2D;
    int getType() const { return type; }
    int getTexelFormat() const { return 0; }
};
using KtxStorage = Texture::KtxStorage;
std::vector<std::pair<std::shared_ptr<storage::FileStorage>, std::shared_ptr<std::mutex>>> KtxStorage::_cachedKtxFiles;
std::mutex KtxStorage::_cachedKtxFilesMutex;
KTX_RELEASE
VkImageViewType getVKTextureType(const Texture& t) { return t.type==Texture::TEX_CUBE ? VK_IMAGE_VIEW_TYPE_CUBE : VK_IMAGE_VIEW_TYPE_2D; }
VkFormat evalTexelFormatInternal(int,VKBackend::Context&) { return VK_FORMAT_R8G8B8A8_UNORM; }
struct VKStrictResourceTexture {
    Texture _gpuObject;
    struct { std::vector<int> mips; } _transferData;
    VkImage _vkImage=reinterpret_cast<VkImage>(3);
    VkImageLayout _vkImageLayout=VK_IMAGE_LAYOUT_UNDEFINED;
    VkSampler _vkSampler{};
    VkImageView _vkImageView{};
    void transfer(VKBackend&);
    void postTransfer(VKBackend&);
};
void VKStrictResourceTexture::transfer(VKBackend& backend) {
    auto device=backend.getContext().device;
    auto copyCmd=copyHandle;
    VkBuffer stagingBuffer{}; VkDeviceMemory stagingMemory{};
    std::vector<VkBufferImageCopy> bufferCopyRegions;
TRANSFER_TAIL
POST_METHOD
int main() {
    for(bool separate : {false,true}) for(bool cube : {false,true}) for(unsigned mips : {1,4}) {
        barriers.clear(); uploads=flushes=destroyed=freed=samplers=views=graphicsCommands=0;
        uploadComplete=false; expectedMips=mips; expectedLayers=cube?6:1;
        Device device; device.queueFamilyIndices={separate?1u:0u,0};
        VKBackend backend{{&device}};
        VKStrictResourceTexture texture; texture._gpuObject.type=cube?Texture::TEX_CUBE:Texture::TEX_2D;
        texture._transferData.mips.resize(mips);
        texture.transfer(backend);
        assert(uploads==1 && destroyed==1 && freed==1 && flushes==1);
        assert(texture._transferData.mips.size()==mips);
        auto mapped = std::make_shared<storage::FileStorage>();
        std::weak_ptr<storage::FileStorage> lifetime = mapped;
        // KtxStorage owns mappings globally, independently of copied transfer data.
        KtxStorage::_cachedKtxFiles.emplace_back(mapped, std::make_shared<std::mutex>());
        mapped.reset();
        assert(!lifetime.expired());
        texture.postTransfer(backend);
        assert(lifetime.expired() && KtxStorage::_cachedKtxFiles.empty());
        assert(samplers==1 && views==1 && texture._transferData.mips.empty());
        assert(texture._vkImageLayout==VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL);
        for(const auto& b : barriers) {
            assert(b.image.subresourceRange.levelCount==mips);
            assert(b.image.subresourceRange.layerCount==expectedLayers);
            assert(b.image.subresourceRange.baseMipLevel==0 && b.image.subresourceRange.baseArrayLayer==0);
            assert(b.image.image==texture._vkImage);
        }
        if(!separate) {
            assert(barriers.size()==2 && "shared queue performs duplicate layout transition");
            const auto& b=barriers.back();
            assert(b.src==VK_PIPELINE_STAGE_TRANSFER_BIT && b.dst==VK_PIPELINE_STAGE_ALL_GRAPHICS_BIT);
            assert(b.image.srcAccessMask==VK_ACCESS_TRANSFER_WRITE_BIT && b.image.dstAccessMask==VK_ACCESS_SHADER_READ_BIT);
            assert(b.image.srcQueueFamilyIndex==VK_QUEUE_FAMILY_IGNORED && b.image.dstQueueFamilyIndex==VK_QUEUE_FAMILY_IGNORED);
            assert(graphicsCommands==0 && flushes==1);
        } else {
            assert(barriers.size()==3 && graphicsCommands==1 && flushes==2);
            const auto& release=barriers[1]; const auto& acquire=barriers[2];
            assert(release.src==VK_PIPELINE_STAGE_TRANSFER_BIT && release.dst==VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT);
            assert(release.image.srcAccessMask==VK_ACCESS_TRANSFER_WRITE_BIT && release.image.dstAccessMask==0);
            assert(acquire.src==VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT && acquire.dst==VK_PIPELINE_STAGE_ALL_GRAPHICS_BIT);
            assert(acquire.image.srcAccessMask==0 && acquire.image.dstAccessMask==VK_ACCESS_SHADER_READ_BIT);
            assert(release.image.oldLayout==acquire.image.oldLayout && release.image.newLayout==acquire.image.newLayout);
            assert(release.image.srcQueueFamilyIndex==1 && acquire.image.srcQueueFamilyIndex==1);
            assert(release.image.dstQueueFamilyIndex==0 && acquire.image.dstQueueFamilyIndex==0);
        }
    }
    std::cout << "PASS: production strict texture upload; shared queue; dedicated transfer release/acquire; 2D/cube; mip chains; staging/sampler/view lifetime\n";
}
'''
code = code.replace("KTX_RELEASE", ktx_release).replace("LAYOUT_HELPER", layout_helper).replace("TRANSFER_TAIL", tail).replace("POST_METHOD", post)
with tempfile.TemporaryDirectory(prefix="overte-texture-sync-") as temp:
    cpp = Path(temp) / "test.cpp"
    cpp.write_text(code)
    binary = Path(temp) / "test"
    subprocess.run(["c++", "-std=c++17", "-O1", "-g", str(cpp), "-o", str(binary)], check=True, timeout=40)
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
    if baseline:
        assert result.returncode != 0 and "shared queue performs duplicate layout transition" in result.stderr, result.stderr
        print("EXPECTED BASELINE FAILURE: duplicate texture layout transition")
    else:
        assert result.returncode == 0, result.stderr
        print(result.stdout.strip())
        mutant = code.replace("    Texture::KtxStorage::releaseOpenKtxFiles();", "    // missing strict-upload retirement")
        assert mutant != code
        cpp.write_text(mutant)
        subprocess.run(["c++", "-std=c++17", "-O1", str(cpp), "-o", str(binary)], check=True, timeout=40)
        rejected = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
        assert rejected.returncode != 0 and "lifetime.expired()" in rejected.stderr, rejected.stderr
        print("PASS: missing strict KTX mapping retirement counterexample fails")
