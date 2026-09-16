"""Run actual Vulkan framebuffer blit code against a recording Vulkan boundary.

Tests valid color-attachment transfers; no native GPU acceptance. The historical
color-only/depth blit contract is outside this regression's scope. An optional
OVERTE_BLIT_BASELINE revision executes the same checks against older source.
"""
import os
from pathlib import Path
import resource
import shutil
import subprocess
import tempfile

resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
ROOT = Path(__file__).resolve().parents[2]
path = 'libraries/gpu-vk/src/gpu/vk/VKBackend.cpp'
baseline = os.environ.get('OVERTE_BLIT_BASELINE')
source = (subprocess.check_output(['git', 'show', baseline + ':' + path], cwd=ROOT, text=True)
          if baseline else (ROOT / path).read_text())

def function(text, marker):
    start = text.index(marker)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

method = function(source, 'void VKBackend::blitToFramebuffer(')
helper = function((ROOT / 'libraries/vk/src/vk/VulkanTools.cpp').read_text(),
                  'void insertImageMemoryBarrier(')
header = (ROOT / 'libraries/gpu-vk/src/gpu/vk/VKBackend.h').read_text()
start = header.index('void blitToFramebuffer(')
declaration = header[start:header.index(';', start) + 1]

code = r'''
#include <vulkan/vulkan.h>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <vector>
struct Barrier { VkImageMemoryBarrier value; VkPipelineStageFlags src, dst; };
std::vector<Barrier> barriers;
std::vector<VkImageBlit> blits;
std::map<VkImage, VkImageLayout> actualLayouts;
bool validateOldLayouts = true;
unsigned rejectionReports = 0;
void qWarning(const char*, unsigned) { ++rejectionReports; }
VKAPI_ATTR void VKAPI_CALL vkCmdPipelineBarrier(VkCommandBuffer,
    VkPipelineStageFlags src, VkPipelineStageFlags dst, VkDependencyFlags,
    uint32_t, const VkMemoryBarrier*, uint32_t, const VkBufferMemoryBarrier*,
    uint32_t count, const VkImageMemoryBarrier* values) {
    for (uint32_t i = 0; i < count; ++i) {
        const auto& b = values[i];
        if (validateOldLayouts && b.oldLayout != VK_IMAGE_LAYOUT_UNDEFINED) {
            assert(actualLayouts.at(b.image) == b.oldLayout);
        }
        actualLayouts[b.image] = b.newLayout;
        barriers.push_back({b, src, dst});
    }
}
VKAPI_ATTR void VKAPI_CALL vkCmdBlitImage(VkCommandBuffer, VkImage src,
    VkImageLayout srcLayout, VkImage dst, VkImageLayout dstLayout,
    uint32_t count, const VkImageBlit* regions, VkFilter filter) {
    if (validateOldLayouts) {
        assert(actualLayouts.at(src) == srcLayout);
        assert(actualLayouts.at(dst) == dstLayout);
    }
    assert(filter == VK_FILTER_LINEAR);
    for (uint32_t i = 0; i < count; ++i) blits.push_back(regions[i]);
}
namespace vks {
namespace initializers {
VkImageMemoryBarrier imageMemoryBarrier() {
    VkImageMemoryBarrier b{}; b.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
    b.srcQueueFamilyIndex = b.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    return b;
}
}
namespace tools { HELPER }
}
struct Vec4i { int x, y, z, w; };
struct VKAttachmentTexture { VkImage _vkImage; VkImageLayout _vkImageLayout; };
struct VKBackend {
    VkCommandBuffer _currentCommandBuffer{};
    DECLARATION
};
METHOD
int main(int argc, char** argv) {
    assert(argc == 2);
    const std::string name = argv[1];
    VKBackend backend;
    VKAttachmentTexture src{reinterpret_cast<VkImage>(uintptr_t(1)), VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
    VKAttachmentTexture dst{reinterpret_cast<VkImage>(uintptr_t(2)), VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
    if (name == "shader_readable_source") src._vkImageLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
    if (name == "general_destination") dst._vkImageLayout = VK_IMAGE_LAYOUT_GENERAL;
    if (name == "fresh_destination") dst._vkImageLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    if (name == "undefined_source") src._vkImageLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    if (name == "preinitialized_source") src._vkImageLayout = VK_IMAGE_LAYOUT_PREINITIALIZED;
    if (name == "preinitialized_destination") dst._vkImageLayout = VK_IMAGE_LAYOUT_PREINITIALIZED;
    if (name == "same_image") dst._vkImage = src._vkImage;
    if (name == "null_image") src._vkImage = VK_NULL_HANDLE;
    const bool rejected = name == "undefined_source" || name == "preinitialized_source" ||
        name == "preinitialized_destination" || name == "same_image" || name == "null_image";
    actualLayouts[src._vkImage] = src._vkImageLayout;
    actualLayouts[dst._vkImage] = dst._vkImageLayout;
    const auto beforeSource = src._vkImageLayout;
    const auto beforeDestination = dst._vkImageLayout;
    const Vec4i from{2, 3, 14, 15}, to{7, 8, 21, 24};
    backend.blitToFramebuffer(src, from, dst, to);
    if (rejected) {
        assert(blits.empty() && barriers.empty());
        assert(src._vkImageLayout == beforeSource && dst._vkImageLayout == beforeDestination);
        assert(rejectionReports == 1);
        for (int i = 0; i < 20; ++i) backend.blitToFramebuffer(src, from, dst, to);
        assert(rejectionReports == 8);
        assert(blits.empty() && barriers.empty());
        std::cout << name << " PASS\n";
        return 0;
    }
    assert(rejectionReports == 0);
    assert(blits.size() == 1);
    if (name == "destination_rectangle") {
        const auto& b = blits[0];
        assert(b.srcOffsets[0].x == 2 && b.srcOffsets[0].y == 3);
        assert(b.srcOffsets[1].x == 14 && b.srcOffsets[1].y == 15);
        assert(b.dstOffsets[0].x == 7 && b.dstOffsets[0].y == 8);
        assert(b.dstOffsets[1].x == 21 && b.dstOffsets[1].y == 24);
    } else if (name == "source_restored" || name == "shader_readable_source") {
        assert(actualLayouts[src._vkImage] == beforeSource);
        assert(src._vkImageLayout == actualLayouts[src._vkImage]);
    } else if (name == "repeat_source") {
        backend.blitToFramebuffer(src, from, dst, to);
        assert(blits.size() == 2);
        assert(actualLayouts[src._vkImage] == src._vkImageLayout);
    } else if (name == "general_destination") {
        assert(barriers[1].value.oldLayout == VK_IMAGE_LAYOUT_GENERAL);
        assert(dst._vkImageLayout == beforeDestination);
        assert(actualLayouts[dst._vkImage] == beforeDestination);
    } else if (name == "partial_destination_preserved") {
        assert(barriers[1].value.oldLayout == beforeDestination);
        assert(barriers[1].value.oldLayout != VK_IMAGE_LAYOUT_UNDEFINED);
    } else if (name == "fresh_destination") {
        assert(barriers[1].value.oldLayout == VK_IMAGE_LAYOUT_UNDEFINED);
        assert(barriers[1].value.srcAccessMask == 0);
        assert(dst._vkImageLayout == VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL);
    } else if (name == "access_dependencies") {
        assert(barriers.size() == 4);
        assert(barriers[0].value.srcAccessMask & VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT);
        assert(barriers[0].value.dstAccessMask & VK_ACCESS_TRANSFER_READ_BIT);
        assert(barriers[0].src & VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT);
        assert(barriers[1].value.dstAccessMask & VK_ACCESS_TRANSFER_WRITE_BIT);
        assert(barriers[2].value.srcAccessMask & VK_ACCESS_TRANSFER_READ_BIT);
        assert(barriers[3].value.srcAccessMask & VK_ACCESS_TRANSFER_WRITE_BIT);
        assert(barriers[3].value.dstAccessMask & VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT);
    } else { assert(false); }
    std::cout << name << " PASS\n";
}
'''.replace('HELPER', helper).replace('DECLARATION', declaration).replace('METHOD', method)
cases = ['destination_rectangle', 'source_restored', 'repeat_source',
         'shader_readable_source', 'general_destination',
         'partial_destination_preserved', 'fresh_destination', 'access_dependencies',
         'undefined_source', 'preinitialized_source', 'preinitialized_destination',
         'same_image', 'null_image']
with tempfile.TemporaryDirectory(prefix='overte-blit-regression-') as directory:
    cpp, exe = Path(directory) / 'test.cpp', Path(directory) / 'test'
    cpp.write_text(code)
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        raise SystemExit('A C++ compiler is required')
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', str(cpp), '-o', str(exe)],
                   check=True, timeout=60)
    failed = []
    for case in cases:
        result = subprocess.run([str(exe), case], capture_output=True, text=True, timeout=10)
        print(case + (' PASS' if result.returncode == 0 else ' FAIL'))
        if result.returncode:
            failed.append(case)
    if failed:
        raise SystemExit(f'{len(failed)}/{len(cases)} checks failed')
    print(f'{len(cases)} production blit checks PASS; native GPU acceptance not performed')
