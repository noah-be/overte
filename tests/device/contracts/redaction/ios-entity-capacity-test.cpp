#include <QtCore/QCoreApplication>
#include "libraries/shared/src/shared/IOSRuntimeLogging.h"
#include <cassert>

static void invalidated() {
    const auto snapshot = iosRuntimeEntityEvidenceSnapshot();
    assert(!snapshot.armed && !snapshot.committed);
    assert(snapshot.expected == 0 && snapshot.renderables == 0 && snapshot.scene == 0 && snapshot.drawn == 0);
#if !TEST_BASELINE
    assert(snapshot.capacityExceeded);
#endif
    assert(iosRuntimeEntityEvidenceGeneration() == 0);
    assert(commitIOSRuntimeEntityEvidence().isEmpty());
}

int main(int argc, char** argv) {
    QCoreApplication application(argc, argv);
    constexpr int limit = 4096;
#if !TEST_BASELINE
    static_assert(IOS_RUNTIME_MAX_OBSERVED_ENTITIES == limit);
    static_assert(IOS_RUNTIME_MAX_ENTITY_KEY_CHARACTERS == 128);
#endif
    for (int path = 0; path < 4; ++path) {
        beginIOSRuntimeEntityEvidence();
        const auto generation = iosRuntimeEntityEvidenceGeneration();
        auto record = [&](const QString& key) {
            switch (path) {
                case 0: recordIOSRuntimeTreeEntity(key); break;
                case 1: recordIOSRuntimeRenderableEntity(key); break;
                case 2: recordIOSRuntimeSceneEntity(key, generation); break;
                case 3: recordIOSRuntimeDrawnEntity(key); break;
            }
        };
        for (int i = 0; i < limit; ++i) record(QString::number(i));
        const auto full = iosRuntimeEntityEvidenceSnapshot();
        assert(full.armed);
        assert((path == 0 ? full.expected : path == 1 ? full.renderables : path == 2 ? full.scene : full.drawn) == limit);
        record("0"); // Duplicate at capacity does not overflow or lose observation.
        assert(iosRuntimeEntityEvidenceSnapshot().armed);
        record("one-past-limit");
        invalidated();
        record("after-invalidation");
        invalidated();
        beginIOSRuntimeEntityEvidence();
        assert(iosRuntimeEntityEvidenceGeneration() != generation);
        assert(!recordIOSRuntimeSceneEntity("old-generation", generation));
        record(QString(129, 'x'));
        // Scene recorder rejects stale generation without disarming the NEW one.
        if (path == 2) {
            assert(iosRuntimeEntityEvidenceSnapshot().armed);
            recordIOSRuntimeSceneEntity(QString(129, 'x'), iosRuntimeEntityEvidenceGeneration());
        }
        invalidated();
    }
    QStringList expected;
    for (int i = 0; i < limit; ++i) expected.append(QString::number(i));
    beginIOSRuntimeEntityEvidence();
    setExpectedIOSRuntimeEntities(expected);
    assert(iosRuntimeEntityEvidenceSnapshot().expected == limit);
    expected.append("one-past-limit");
    setExpectedIOSRuntimeEntities(expected);
    invalidated();
    beginIOSRuntimeEntityEvidence();
    setExpectedIOSRuntimeEntities({"initial", QString(129, 'x')});
    invalidated(); // No retained valid prefix masquerading as complete expectation.
    beginIOSRuntimeEntityEvidence();
    const QString exact(128, 'x');
    recordIOSRuntimeTreeEntity(exact);
    recordIOSRuntimeRenderableEntity(exact);
    assert(commitIOSRuntimeEntityEvidence() == exact);
    assert(commitIOSRuntimeEntityEvidence().isEmpty()); // Original once-only behavior.
    const auto generation = iosRuntimeEntityEvidenceGeneration();
    recordIOSRuntimeSceneEntity(exact, generation);
    recordIOSRuntimeDrawnEntity(exact);
    recordIOSRuntimeDrawnEntity(QString(129, 'y'));
    invalidated(); // Even after legacy marker emission, counters cannot keep growing.
    beginIOSRuntimeEntityEvidence();
    assert(iosRuntimeEntityEvidenceSnapshot().armed);
#if !TEST_BASELINE
    assert(!iosRuntimeEntityEvidenceSnapshot().capacityExceeded);
#endif
}
