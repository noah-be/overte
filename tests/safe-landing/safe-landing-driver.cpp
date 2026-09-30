// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
static auto renderer() { return QSharedPointer<EntityTreeRenderer>::create(); }
static void retired(SafeLanding& landing, const QSharedPointer<EntityTreeRenderer>& r) {
    assert(!landing.isTracking());
    int before = r->tree->lookups;
    emit r->tree->addingEntity(2);
    assert(r->tree->lookups == before);
    assert(EntityTreeRenderer::priority(EntityItem{}) == 7.0f);
}

int main(int argc, char** argv) {
    QCoreApplication core(argc, argv);
    qRegisterMetaType<EntityItemID>("EntityItemID");
    assert(argc == 2);
    std::string test = argv[1];
    SafeLanding landing;
    auto r = renderer();
    landing.startTracking(r);
    if (test == "callback-stop" || test == "callback-reset" || test == "callback-restart") {
        QSemaphore entered, release;
        std::thread script([&] {
            TestMutex::beforeLock = [&] { entered.release(); release.acquire(); };
            emit r->tree->addingEntity(1);
            TestMutex::beforeLock = {};
        });
        assert(entered.tryAcquire(1, 5000));
        auto next = renderer();
        if (test == "callback-stop") landing.stopTracking();
        else landing.reset();
        if (test == "callback-restart") landing.startTracking(next);
        release.release(); script.join();
        assert(r->tree->lookups == 0 && next->tree->lookups == 0);
        assert(landing.loadingStatus().trackedEntityCount == 0);
        if (test == "callback-restart") {
            emit next->tree->addingEntity(1);
            assert(next->tree->lookups == 1);
            assert(landing.loadingStatus().trackedEntityCount == 1);
            landing.stopTracking();
        }
        retired(landing, r);
    } else if (test == "queued-delete") {
        std::thread script([&] { emit r->tree->deletingEntity(1); });
        script.join(); // The AutoConnection callback is queued on the owner.
        landing.reset(); landing.startTracking(r);
        emit r->tree->addingEntity(1);
        assert(landing.loadingStatus().trackedEntityCount == 1);
        QCoreApplication::sendPostedEvents(&landing, QEvent::MetaCall);
        assert(landing.loadingStatus().trackedEntityCount == 1);
        emit r->tree->deletingEntity(1);
        assert(landing.loadingStatus().trackedEntityCount == 0);
        landing.stopTracking(); retired(landing, r);
    } else if (test == "repeated-start-reset") {
        for (int i = 0; i < 50; ++i) {
            landing.startTracking(r); // Idempotent while active.
            int before = r->tree->lookups;
            emit r->tree->addingEntity(1);
            assert(r->tree->lookups == before + 1);
            landing.addToSequence(4); landing.finishSequence(4, 5);
            landing.reset(); retired(landing, r);
            assert(!landing.trackingIsComplete());
            auto status = landing.loadingStatus();
            assert(status.trackedEntityCount == 0 && status.receivedSequenceCount == 0);
            assert(!status.completionReceived && status.maximumTrackedEntityCount == 0);
            landing.startTracking(r);
        }
        landing.stopTracking(); retired(landing, r);
    } else if (test == "readiness-and-gaps") {
        r->tree->entity->physicsReady = false;
        emit r->tree->addingEntity(1);
        landing.addToSequence(4); landing.finishSequence(4, 6);
        landing.updateTracking(); assert(landing.isTracking());
        r->tree->entity->physicsReady = true;
        landing.updateTracking(); assert(landing.isTracking()); // Missing packet 5.
        landing.addToSequence(5); landing.updateTracking();
        assert(landing.trackingIsComplete()); retired(landing, r);
        landing.addToSequence(6); // Retired sessions do not accept late packets.
        assert(landing.loadingStatus().receivedSequenceCount == 2);
    } else if (test == "empty-scene") {
        landing.updateTracking(); assert(landing.isTracking()); // No completion yet.
        landing.finishSequence(SafeLanding::INVALID_SEQUENCE, 0);
        landing.updateTracking(); assert(landing.trackingIsComplete()); retired(landing, r);
        landing.reset(); assert(!landing.trackingIsComplete());
    } else if (test == "visual-readiness") {
        r->tree->entity->visualReady = false;
        emit r->tree->addingEntity(1);
        landing.finishSequence(SafeLanding::INVALID_SEQUENCE, 0);
        landing.updateTracking();
#ifdef ANDROID_APP_PICO_INTERFACE
        assert(landing.trackingIsComplete()); // Keep Pico's playable handoff.
#else
        assert(landing.isTracking());
        r->tree->entity->visualReady = true;
        landing.updateTracking(); assert(landing.trackingIsComplete());
#endif
        retired(landing, r);
    } else if (test == "concurrent-start") {
        landing.reset();
        QSemaphore entered, release;
        auto start = [&] {
            TestMutex::beforeLock = [&] { entered.release(); release.acquire(); };
            landing.startTracking(r);
            TestMutex::beforeLock = {};
        };
        std::thread a(start), b(start);
        assert(entered.tryAcquire(2, 5000));
        release.release(2); a.join(); b.join();
        emit r->tree->addingEntity(1);
        assert(r->tree->lookups == 1);
        landing.stopTracking(); retired(landing, r);
    } else if (test == "update-retired") {
        for (bool reset : { false, true }) {
            landing.startTracking(r);
            QSemaphore entered, release;
            std::thread update([&] {
                TestMutex::beforeLock = [&] { entered.release(); release.acquire(); };
                landing.updateTracking();
                TestMutex::beforeLock = {};
            });
            assert(entered.tryAcquire(1, 5000));
            if (reset) landing.reset(); else landing.stopTracking();
            release.release(); update.join();
            retired(landing, r);
        }
    } else if (test == "sequence-restart") {
        r->tree->entity->physicsReady = false;
        emit r->tree->addingEntity(1);
        landing.addToSequence(4); landing.finishSequence(4, 5);
        landing.restartSequenceTracking();
        auto status = landing.loadingStatus();
        assert(landing.isTracking() && !status.completionReceived);
        assert(status.receivedSequenceCount == 0 && status.trackedEntityCount == 1);
        emit r->tree->addingEntity(2); assert(r->tree->lookups == 2);
        r->tree->entity->physicsReady = true;
        landing.updateTracking(); assert(landing.isTracking());
        landing.finishSequence(8, 9);
        landing.updateTracking(); assert(landing.isTracking());
        landing.addToSequence(8); landing.updateTracking();
        assert(landing.trackingIsComplete()); retired(landing, r);
        landing.restartSequenceTracking();
        assert(landing.trackingIsComplete()); // Retired restart is a no-op.
        landing.reset();
        landing.addToSequence(20); landing.finishSequence(20, 21);
        assert(landing.loadingStatus().receivedSequenceCount == 0);
        assert(!landing.loadingStatus().completionReceived);
    } else if (test == "completion-callback") {
        landing.finishSequence(SafeLanding::INVALID_SEQUENCE, 0);
        TestMutex::afterUnlock = [&] {
            TestMutex::afterUnlock = {};
            r->tree->entity->physicsReady = false;
            emit r->tree->addingEntity(1);
        };
        landing.updateTracking();
        TestMutex::afterUnlock = {};
        // A completion must not retire an admitted, physics-blocked entity.
        assert(landing.isTracking() || landing.loadingStatus().trackedEntityCount == 0);
        landing.stopTracking(); retired(landing, r);
    } else if (test == "completion-legacy-gap") {
        landing.finishSequence(SafeLanding::INVALID_SEQUENCE, 0);
        int releases = 0;
        TestMutex::afterUnlock = [&] {
            // Baseline release 1: entity pass; release 2: stop decision.
            // The fixed update has a single release after session retirement.
            if (++releases == 2) {
                TestMutex::afterUnlock = {};
                r->tree->entity->physicsReady = false;
                emit r->tree->addingEntity(1);
            }
        };
        landing.updateTracking();
        TestMutex::afterUnlock = {};
        assert(landing.isTracking() || landing.loadingStatus().trackedEntityCount == 0);
        landing.stopTracking(); retired(landing, r);
    } else if (test == "null-start") {
        landing.reset();
        landing.startTracking({}); assert(!landing.isTracking());
        auto invalid = renderer(); invalid->tree.reset();
        landing.startTracking(invalid); assert(!landing.isTracking());
        assert(EntityTreeRenderer::priority(EntityItem{}) == 7.0f);
        landing.startTracking(r); landing.stopTracking(); retired(landing, r);
    } else if (test == "interstitial-disabled") {
        DependencyManager::get<NodeList>()->getDomainHandler().enabled = false;
        r->tree->entity->visualReady = false;
        emit r->tree->addingEntity(1);
        assert(landing.loadingStatus().visuallyBlockedEntityCount == 0);
        landing.finishSequence(SafeLanding::INVALID_SEQUENCE, 0);
        landing.updateTracking(); assert(landing.trackingIsComplete()); retired(landing, r);
    } else if (test == "status-race") {
        std::atomic<bool> running { true };
        std::thread reader([&] {
            while (running.load()) {
                landing.isTracking(); landing.trackingIsComplete();
                landing.loadingProgressPercentage(); landing.loadingStatus();
            }
        });
        for (int i = 0; i < 200; ++i) {
            landing.reset(); landing.startTracking(r);
            emit r->tree->addingEntity(1);
            landing.addToSequence(4); landing.finishSequence(4, 5);
            landing.restartSequenceTracking();
        }
        running = false; reader.join();
        landing.reset(); retired(landing, r);
    } else {
        assert(false && "unknown test");
    }
}
