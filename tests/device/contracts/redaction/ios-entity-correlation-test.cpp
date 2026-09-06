#include <QtCore/QCoreApplication>
#include "libraries/shared/src/shared/IOSRuntimeLogging.h"
#include <cassert>

int main(int argc, char** argv) {
    QCoreApplication application(argc, argv);
    beginIOSRuntimeEntityEvidence();
    const auto generation = iosRuntimeEntityEvidenceGeneration();
    setExpectedIOSRuntimeEntities({"world-a", "world-b"});
    recordIOSRuntimeRenderableEntity("unrelated");
    recordIOSRuntimeSceneEntity("unrelated", generation);
    recordIOSRuntimeDrawnEntity("unrelated");
    auto state = iosRuntimeEntityEvidenceSnapshot();
    assert(state.expected == 2 && state.renderables == 0 && state.scene == 0 && state.drawn == 0);
    assert(commitIOSRuntimeEntityEvidence().isEmpty());
    assert(recordIOSRuntimeRenderableEntity("world-a") == "world-a");
    recordIOSRuntimeSceneEntity("world-a", generation);
    recordIOSRuntimeDrawnEntity("world-a");
    state = iosRuntimeEntityEvidenceSnapshot();
    assert(state.committed && state.renderables == 1 && state.scene == 1 && state.drawn == 1);
    // Legacy first-handoff emission must not freeze later bounded observations.
    assert(recordIOSRuntimeRenderableEntity("world-b").isEmpty());
    recordIOSRuntimeSceneEntity("world-b", generation);
    recordIOSRuntimeDrawnEntity("world-b");
    state = iosRuntimeEntityEvidenceSnapshot();
    assert(state.renderables == 2 && state.scene == 2 && state.drawn == 2);
    assert(recordIOSRuntimeTreeEntity("world-c").isEmpty());
    assert(recordIOSRuntimeRenderableEntity("world-c").isEmpty());
    assert(iosRuntimeEntityEvidenceSnapshot().expected == 3);
    assert(iosRuntimeEntityEvidenceSnapshot().renderables == 3);
    // Replacement expectation recomputes intersections, not monotonic raw totals.
    setExpectedIOSRuntimeEntities({"world-b", "world-d"});
    state = iosRuntimeEntityEvidenceSnapshot();
    assert(state.expected == 2 && state.renderables == 1 && state.scene == 1 && state.drawn == 1);
    assert(commitIOSRuntimeEntityEvidence().isEmpty());
    beginIOSRuntimeEntityEvidence();
    recordIOSRuntimeSceneEntity("future", iosRuntimeEntityEvidenceGeneration());
    recordIOSRuntimeDrawnEntity("future");
    recordIOSRuntimeRenderableEntity("future");
    state = iosRuntimeEntityEvidenceSnapshot();
    assert(state.expected == 0 && state.renderables == 0 && state.scene == 0 && state.drawn == 0);
    recordIOSRuntimeTreeEntity("future"); // Handoff-before-tree ordering remains supported.
    state = iosRuntimeEntityEvidenceSnapshot();
    assert(state.expected == 1 && state.renderables == 1 && state.scene == 1 && state.drawn == 1);
    assert(commitIOSRuntimeEntityEvidence() == "future");
    assert(!recordIOSRuntimeSceneEntity("old", generation));
}
