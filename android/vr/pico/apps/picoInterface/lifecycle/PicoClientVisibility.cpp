// SPDX-License-Identifier: Apache-2.0
// Full-client-only JNI transport; the Shared owner retains the sole Gate.
#include "ApplicationLifecycle.h"
#include <QtCore/QCoreApplication>
#include <QtCore/QMetaObject>
#include <jni.h>
#include <limits>
#include <mutex>

namespace {
std::mutex visibilityMutex;
jlong newestGeneration { 0 };
bool newestForeground { false };
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_overte_pico_PicoClientVisibility_publish(
        JNIEnv*, jclass, jlong generation, jboolean foreground) {
    auto app = QCoreApplication::instance();
    if (!app || generation <= 0 || (foreground != JNI_FALSE && foreground != JNI_TRUE) ||
        (generation == std::numeric_limits<jlong>::max() && foreground != JNI_FALSE)) {
        return JNI_FALSE;
    }
    const bool active = foreground == JNI_TRUE;
    std::lock_guard<std::mutex> lock(visibilityMutex);
    if (generation < newestGeneration) { return JNI_TRUE; } // Discarded stale producer work.
    if (generation == newestGeneration) {
        return active == newestForeground ? JNI_TRUE : JNI_FALSE;
    }
    // Always queue on the one receiver under this lock. Retain accepted deny
    // barriers across rapid pause/resume so old HTTP work is cancelled. Only
    // stale allows are elided; a late already-obsolete submission was rejected
    // above and cannot insert a new deny behind a newer owner observation.
    const bool queued = QMetaObject::invokeMethod(app, [generation, active] {
        std::lock_guard<std::mutex> applyLock(visibilityMutex);
        if (active && generation != newestGeneration) { return; }
        overte::lifecycle::observeNativeVisibility(active);
    }, Qt::QueuedConnection);
    if (!queued) { return JNI_FALSE; }
    newestGeneration = generation;
    newestForeground = active;
    return JNI_TRUE;
}
