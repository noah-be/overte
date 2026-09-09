#!/usr/bin/env python3
"""Exercise production frame ownership and retirement across iOS swapchain resizes."""
from pathlib import Path
import argparse
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--source-ref', help='Read an older implementation for a negative regression check')
parser.add_argument('--expect-exhaustion', action='store_true')
args = parser.parse_args()

def source(path):
    if args.source_ref:
        return subprocess.check_output(['git', 'show', f'{args.source_ref}:{path}'], cwd=ROOT, text=True)
    return (ROOT / path).read_text()

def function(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

backend = source('libraries/gpu-vk/src/gpu/vk/VKBackend.cpp')
plugin = source('libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.cpp')
start = plugin.index('// Retire the previous frame as a fence/command-buffer pair')
end = plugin.index('VkCommandBufferBeginInfo commandBufferBeginInfo', start)
retire = plugin[start:end]
# Compile the actual backend methods and caller block; only Vulkan/Qt effects
# are replaced with checked GPU-completion and resource-lifetime stand-ins.
cpp = r'''
#include <cassert>
#include <deque>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <vector>
#include <iostream>
#define Q_ASSERT(...) ((void)0) // Release behavior: the original empty front() is unguarded.
#define VK_CHECK_RESULT(x) do { if ((x) != 0) throw std::runtime_error("GPU failure"); } while (0)
#define VK_NULL_HANDLE 0
#define VK_TRUE 1
#define DEFAULT_FENCE_TIMEOUT 1
#define OS_LOG_DEFAULT 0
#define os_log_info(...) ((void)0)
namespace vks { namespace debugutils {} }
auto qDebug() { return std::ostringstream{}; }
struct Batch {};
struct Frame { std::vector<std::shared_ptr<Batch>> batches; };
using FramePointer = std::shared_ptr<Frame>;
struct FrameData {
    bool inFlight = false;
    int cleaned = 0;
    int _bufferTransferCounterTransferPass=0, _bufferTransferCounterRenderPass=0;
    int _uniformBufferTransferCounter=0, _vertexBufferTransferCounter=0;
    int _indexBufferTransferCounter=0, _resourceBufferTransferCounter=0;
    int _bufferCreationCounter=0, _bufferResizeCounter=0, _bufferTransferredBytes=0;
    void cleanup() { if (inFlight) throw std::runtime_error("recycled before GPU completion"); ++cleaned; }
};
struct ReusableFrames : std::deque<std::shared_ptr<FrameData>> {
    auto& front() {
        if (empty()) throw std::runtime_error("frame-pool-exhausted");
        return std::deque<std::shared_ptr<FrameData>>::front();
    }
};
struct Transfer { void manageMemory() {} };
struct VKBackend {
    bool _isInitialized=false;
    int _frameCounter=0;
    std::vector<int> _iosCurrentUntrustedPipelines;
    std::vector<std::shared_ptr<FrameData>> _framePool;
    ReusableFrames _framesToReuse;
    std::shared_ptr<FrameData> _currentFrame, _currentlyRenderedFrame, _previouslyRenderedFrame;
    struct { std::shared_ptr<Transfer> _transferEngine=std::make_shared<Transfer>(); } _textureManagement;
    VKBackend() {
        for (int i=0; i<3; ++i) {
            _framePool.push_back(std::make_shared<FrameData>());
            _framesToReuse.push_back(_framePool.back());
        }
    }
    void initBeforeFirstFrame() {}
    void perFrameCleanup() {}
    void render(const Batch&) {}
    void releaseFrameData() { _currentFrame.reset(); }
    void retireIOSDiagnosticSubmit() {}
    void acquireFrameData();
    void recyclePreviousFrame();
    void executeFrame(const FramePointer&);
};
'''
for name in ['acquireFrameData()', 'recyclePreviousFrame()', 'executeFrame(const FramePointer& frame)']:
    cpp += '\n' + function(backend, 'void VKBackend::' + name) + '\n'
cpp += r'''
struct Window { int _previousFrameFence=0, _previousCommandBuffer=0; };
VKBackend* activeBackend = nullptr;
bool failWait = false;
int completedWaits = 0;
void completeGPU() { for (auto& frame : activeBackend->_framePool) frame->inFlight=false; }
int vkWaitForFences(int, int, int* fence, int, int) {
    assert(*fence != 0);
    if (failWait) return -1;
    completeGPU(); ++completedWaits; return 0;
}
void vkDestroyFence(int, int, void*) {}
int vkResetCommandBuffer(int buffer, int) { assert(buffer != 0); return 0; }
void retire(Window* _vkWindow, VKBackend* vkBackend) {
    int vkDevice=1;
    bool _iosPresentFenceReported=false;
'''
cpp += retire
cpp += r'''
}
int main() {
  try {
    VKBackend backend; activeBackend=&backend;
    Window window;
    auto frame=std::make_shared<Frame>();
    auto present = [&] {
        retire(&window, &backend);
        backend.executeFrame(frame);
        backend._currentlyRenderedFrame->inFlight=true;
        window._previousFrameFence=1; window._previousCommandBuffer=1;
        assert(backend._framePool.size()==3);
    };
    // First frame and uninterrupted presentation preserve the bounded pool.
    for (int i=0; i<32; ++i) present();
    const auto before=backend._framesToReuse.size();
    // Fence failures must abort before any resource is recycled.
    failWait=true;
    try { present(); assert(false); } catch (const std::runtime_error& e) {
        assert(std::string(e.what())=="GPU failure");
        assert(backend._framesToReuse.size()==before);
    }
    failWait=false;
#ifdef Q_OS_IOS
    // VKWindow::resizeFramebuffer waits for device idle and clears the fence.
    // Repeated keyboard/safe-area/orientation resizes must not drain FrameData.
    for (int i=0; i<128; ++i) {
        completeGPU();
        window._previousFrameFence=0; window._previousCommandBuffer=0;
        present();
        assert(backend._framesToReuse.size()<=1);
    }
    assert(backend._framesToReuse.size()==1);
#endif
    for (int i=0; i<32; ++i) present();
    std::cout << "bounded pool and GPU completion ordering passed\n";
    return 0;
  } catch (const std::runtime_error& e) {
    std::cerr << e.what() << '\n'; return 2;
  }
}
'''
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp)
    (path / 'test.cpp').write_text(cpp)
    for ios in [True, False]:
        binary = path / ('ios-test' if ios else 'desktop-test')
        subprocess.run(['c++', '-std=c++17', '-O2', *(['-DQ_OS_IOS'] if ios else []),
                        str(path / 'test.cpp'), '-o', str(binary)], check=True, timeout=45)
        run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
        if ios and args.expect_exhaustion:
            assert run.returncode == 2 and 'frame-pool-exhausted' in run.stderr, run
            print('Original iOS caller reproduces frame-pool exhaustion after resize')
        else:
            assert run.returncode == 0, run.stderr
            print(('iOS' if ios else 'Desktop') + ': ' + run.stdout.strip())
