// SPDX-License-Identifier: Apache-2.0
// Original whole updateInScene and Shared state. Only renderer dependencies are stubs.
#include <QtCore/QtCore>
#include <cassert>
#include <functional>
#include <memory>
#include <vector>
#if TEST_IOS
#define OVERTE_IOS 1
#endif
#include "libraries/shared/src/shared/IOSRuntimeLogging.h"
#define DETAILED_PROFILE_RANGE(...)
static int usecTimestampNow() { return 19; }
struct Position { float x {}, y {}, z {}; };
struct Entity {
    QUuid getID() { return QUuid("291a3b49-ff8f-4b6b-8f49-38a20a9f5f26"); }
    Position getWorldPosition() { return {}; }
    int getType() { return 0; }
};
struct EntityTypes { static const char* getEntityTypeName(int) { return "Entity"; } };
struct PayloadProxyInterface {};
using ScenePointer = int;
struct Transaction {
    std::vector<std::function<void(PayloadProxyInterface&)>> pending;
    template<class T, class F> void updateItem(int, F callback) { pending.push_back(callback); }
    void flush() {
        auto callbacks = std::move(pending);
        pending.clear();
        PayloadProxyInterface payload;
        for (auto& callback : callbacks) { callback(payload); }
    }
};
struct EntityRenderer {
    bool valid { true };
    int synchronous {}, asynchronous {}, _updateTime {}, _renderItemID { 1 };
    std::shared_ptr<Entity> _entity { std::make_shared<Entity>() };
    bool isValidRenderItem() { return valid; }
    void doRenderUpdateSynchronous(const ScenePointer&, Transaction&, std::shared_ptr<Entity>) { ++synchronous; }
    void doRenderUpdateAsynchronous(std::shared_ptr<Entity>) { ++asynchronous; }
    void updateInScene(const ScenePointer&, Transaction&);
};
#include "scene-method.inc"
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    EntityRenderer renderer;
    Transaction transaction;
#if TEST_IOS
#if !TEST_BASELINE
    assert(iosRuntimeEntityEvidenceGeneration() == 0);
#endif
    renderer.updateInScene(0, transaction); // Queued while unarmed.
    beginIOSRuntimeEntityEvidence();
    transaction.flush();
    assert(iosRuntimeEntityEvidenceSnapshot().scene == 0);
#if !TEST_BASELINE
    const auto first = iosRuntimeEntityEvidenceGeneration();
#endif
    renderer.updateInScene(0, transaction);
    beginIOSRuntimeEntityEvidence(); // New world before the old render-thread callback.
#if !TEST_BASELINE
    assert(iosRuntimeEntityEvidenceGeneration() != first);
#endif
    transaction.flush();
    assert(iosRuntimeEntityEvidenceSnapshot().scene == 0);
    renderer.updateInScene(0, transaction);
    transaction.flush();
    assert(iosRuntimeEntityEvidenceSnapshot().scene == 1);
    renderer.updateInScene(0, transaction);
    transaction.flush();
    assert(iosRuntimeEntityEvidenceSnapshot().scene == 1); // Duplicate bounded by entity key.
    assert(renderer.synchronous == 4 && renderer.asynchronous == 4);
#if !TEST_BASELINE
    assert(!recordIOSRuntimeSceneEntity("foreign-private-canary", first));
    assert(!recordIOSRuntimeSceneEntity("foreign-private-canary", 0));
#endif
    beginIOSRuntimeEntityEvidence();
    renderer.updateInScene(0, transaction);
    renderer.valid = false;
    transaction.flush();
    assert(iosRuntimeEntityEvidenceSnapshot().scene == 0 && renderer.asynchronous == 4);
    renderer.updateInScene(0, transaction);
    assert(transaction.pending.empty() && renderer.synchronous == 5);
#if !TEST_BASELINE
    auto& state = iosRuntimeEntityEvidenceState();
    { std::lock_guard<std::mutex> lock(state.mutex); state.generation = std::numeric_limits<std::uint64_t>::max(); }
    beginIOSRuntimeEntityEvidence();
    assert(iosRuntimeEntityEvidenceGeneration() == 0 && !iosRuntimeEntityEvidenceSnapshot().armed);
    beginIOSRuntimeEntityEvidence();
    assert(iosRuntimeEntityEvidenceGeneration() == 0); // No wraparound revival.
#endif
#else
    renderer.updateInScene(0, transaction);
    transaction.flush();
    assert(renderer.synchronous == 1 && renderer.asynchronous == 1);
#endif
}
