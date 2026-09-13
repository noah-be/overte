"""Exercise production notification/queue/drain code on a host, not native acceptance.

The scene fixture rejects off-owner access deterministically. The old production
callback can be selected with OVERTE_RENDER_CALLBACK_BASELINE=<commit> to prove
the regression. OVERTE_RENDER_CHANGE_TSAN=1 adds ThreadSanitizer.
"""
import os
from pathlib import Path
import shlex
import re
import sys
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'libraries/entities-renderer/src'


def body(source, signature):
    start = source.index('{', source.index(signature))
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start + 1:end - 1]


tree = (SRC / 'EntityTreeRenderer.cpp').read_text()
header = (SRC / 'EntityTreeRenderer.h').read_text()
callback_source = (SRC / 'RenderableEntityItem.cpp').read_text()
renderer_header = (SRC / 'RenderableEntityItem.h').read_text()
header_baseline = os.environ.get('OVERTE_RENDER_HEADER_BASELINE')
if header_baseline:
    renderer_header = subprocess.check_output([
        'git', 'show', header_baseline + ':libraries/entities-renderer/src/RenderableEntityItem.h'
    ], cwd=ROOT, text=True)
# Preserve actual C++ access control in the fixture, not an always-public mock.
needs_declaration = renderer_header.index('virtual bool needsRenderUpdate() const;')
renderer_access = re.findall(r'^\s*(public|protected|private):',
                            renderer_header[:needs_declaration], re.MULTILINE)[-1]
baseline = os.environ.get('OVERTE_RENDER_CALLBACK_BASELINE')
if baseline:
    callback_source = subprocess.check_output([
        'git', 'show', baseline + ':libraries/entities-renderer/src/RenderableEntityItem.cpp'
    ], cwd=ROOT, text=True)
registration = callback_source[callback_source.index('_changeHandlerId = entity->registerChangeHandler'):]
registration = registration[:registration.index('\n    });') + len('\n    });')]
drain = body(tree, 'void EntityTreeRenderer::updateChangedEntities(')
drain = drain[:drain.index('    float expectedUpdateCost')]
members = header[header.index('    ReadWriteLockable _changedEntitiesGuard;'):]
members = members[:members.index('    std::unordered_map<EntityItemID, EntityItemWeakPointer>')]
program = r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#define PROFILE_RANGE_EX(...) ((void)0)
struct PerformanceTimer { explicit PerformanceTimer(const char*) {} };
using EntityItemID = int;
const auto ownerThread = std::this_thread::get_id();
void requireOwner() { assert(std::this_thread::get_id() == ownerThread && "off-owner scene access"); }
struct ReadWriteLockable {
    std::mutex mutex;
    template<class F> void withWriteLock(F f) { std::lock_guard<std::mutex> lock(mutex); f(); }
};
struct Renderable {
    bool dirty = false;
    int checks = 0;
    std::function<void()> duringCheck;
RENDERER_ACCESS:
    bool needsRenderUpdate() {
        requireOwner(); ++checks;
        if (duringCheck) { auto callback = std::move(duringCheck); duringCheck = {}; callback(); }
        return dirty;
    }
};
using EntityRendererPointer = std::shared_ptr<Renderable>;
struct EntityTreeRenderer {
    MEMBERS
    EntityRendererPointer renderableForEntityId(const EntityItemID& id) const {
        requireOwner(); LOOKUP
    }
    void onEntityChanged(const EntityItemID& id, bool forceRenderUpdate = true) { ENQUEUE }
    void drain() { requireOwner(); DRAIN }
};
std::shared_ptr<EntityTreeRenderer> tree;
struct DependencyManager {
    template<class T> static std::shared_ptr<T> get() { return tree; }
};
struct Entity {
    std::function<void(const EntityItemID&)> callback;
    int registerChangeHandler(std::function<void(const EntityItemID&)> f) { callback = std::move(f); return 1; }
};
void registerProductionCallback(Entity* entity) { int _changeHandlerId; REGISTRATION (void)_changeHandlerId; }
int main() {
    tree = std::make_shared<EntityTreeRenderer>();
    Entity entity; registerProductionCallback(&entity);
    auto renderer = std::make_shared<Renderable>();
    tree->_entitiesInScene[1] = renderer;
    // The old callback fails here, before attempting a racy hash-table lookup.
    std::thread render([&] { entity.callback(1); }); render.join();
    assert(renderer->checks == 0);
    tree->drain(); assert(renderer->checks == 1 && tree->_renderablesToUpdate.empty());
    renderer->dirty = true;
    for (int i = 0; i != 100; ++i) entity.callback(1);
    tree->drain(); assert(renderer->checks == 2 && tree->_renderablesToUpdate.count(renderer));
    tree->_renderablesToUpdate.clear(); renderer->dirty = false;
    // Forced requests must win in either arrival order, even for clean renderers.
    for (bool forcedFirst : {false, true}) {
        if (forcedFirst) tree->onEntityChanged(1);
        entity.callback(1);
        if (!forcedFirst) tree->onEntityChanged(1);
        tree->drain(); assert(tree->_renderablesToUpdate.count(renderer));
        tree->_renderablesToUpdate.clear();
    }
    // Resolve at drain time: an entity removed since notification is harmless.
    entity.callback(1); tree->_entitiesInScene.erase(1);
    tree->drain(); assert(tree->_renderablesToUpdate.empty());
    // A queued ID holds no renderer alive after scene removal.
    tree->_entitiesInScene[1] = renderer; entity.callback(1);
    std::weak_ptr<Renderable> weak = renderer;
    tree->_entitiesInScene.clear(); renderer.reset(); assert(weak.expired());
    tree->drain(); assert(tree->_renderablesToUpdate.empty());
    // A notification raised during the check must be deferred, not deadlock/lost.
    renderer = std::make_shared<Renderable>(); tree->_entitiesInScene[1] = renderer;
    renderer->duringCheck = [&] { tree->onEntityChanged(1); };
    entity.callback(1); tree->drain(); assert(tree->_renderablesToUpdate.empty());
    tree->drain(); assert(tree->_renderablesToUpdate.count(renderer));
    tree->_renderablesToUpdate.clear();
    // Concurrent producers while the owner inserts, rehashes, clears and drains.
    std::atomic<bool> start {false};
    std::vector<std::thread> producers;
    for (int t = 0; t != 4; ++t) producers.emplace_back([&] {
        while (!start.load()) std::this_thread::yield();
        for (int i = 0; i != 20000; ++i) entity.callback(i % 257);
    });
    start = true;
    for (int i = 0; i != 1000; ++i) {
        tree->_entitiesInScene[i % 257] = renderer;
        if (i % 17 == 0) tree->_entitiesInScene.clear();
        tree->drain(); tree->_renderablesToUpdate.clear();
    }
    for (auto& producer : producers) producer.join();
    tree->drain(); assert(tree->_changedEntities.empty());
    // A late notification after dependency shutdown is a no-op.
    tree.reset(); entity.callback(1);
}
'''
for token, value in {
    'RENDERER_ACCESS': renderer_access,
    'MEMBERS': members,
    'LOOKUP': body(tree, 'EntityRendererPointer EntityTreeRenderer::renderableForEntityId('),
    'ENQUEUE': body(tree, 'void EntityTreeRenderer::onEntityChanged('),
    'DRAIN': drain,
    'REGISTRATION': registration,
}.items():
    program = program.replace(token, value)
with tempfile.TemporaryDirectory(prefix='overte-entity-change-') as scratch:
    source = Path(scratch) / 'test.cpp'
    binary = Path(scratch) / 'test'
    source.write_text(program)
    sanitizer = ['-fsanitize=thread'] if os.environ.get('OVERTE_RENDER_CHANGE_TSAN') == '1' else []
    compiler = shlex.split(os.environ.get('CXX', 'c++'))
    compiled = subprocess.run([*compiler, '-std=c++17', '-O1', '-g', '-pthread', *sanitizer,
                    str(source), '-o', str(binary)], capture_output=True, text=True, timeout=40)
    if header_baseline:
        assert compiled.returncode != 0 and 'protected' in compiled.stderr, compiled.stderr
        print('EXPECTED BASELINE FAILURE: actual renderer access control rejects scene-owner caller')
        sys.exit(0)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
    if baseline:
        assert result.returncode != 0 and 'off-owner scene access' in result.stderr, result.stderr
        print('EXPECTED BASELINE FAILURE: production callback accesses scene off-owner')
    else:
        assert result.returncode == 0, result.stderr
        print('PASS: production callback/queue/drain; owner confinement; conditional/forced '
              'coalescing; removal/lifetime; reentrancy; 80000 concurrent notifications; shutdown')
