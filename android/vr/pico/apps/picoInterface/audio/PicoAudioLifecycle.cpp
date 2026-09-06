// SPDX-License-Identifier: Apache-2.0
#include "../../../../../../libraries/audio-client/src/AudioLifecycleGate.h"
#include <jni.h>
namespace {
overte::audio::AudioLifecycleGate gate;
}
extern "C" JNIEXPORT void JNICALL
Java_org_overte_pico_PicoAudioLifecycle_foreground(JNIEnv*, jclass, jboolean active) {
    gate.foreground(active == JNI_TRUE);
}
extern "C" JNIEXPORT jboolean JNICALL
Java_org_overte_pico_PicoAudioLifecycle_begin(JNIEnv*, jclass, jboolean permission) {
    gate.interruption(false);
    gate.requestStart();
    gate.permission(permission == JNI_TRUE ? overte::audio::Permission::Granted : overte::audio::Permission::Denied);
    return gate.outcome() == overte::audio::Outcome::Capturing ? JNI_TRUE : JNI_FALSE;
}
extern "C" JNIEXPORT jboolean JNICALL
Java_org_overte_pico_PicoAudioLifecycle_mayCapture(JNIEnv*, jclass) {
    return gate.outcome() == overte::audio::Outcome::Capturing ? JNI_TRUE : JNI_FALSE;
}
extern "C" JNIEXPORT void JNICALL
Java_org_overte_pico_PicoAudioLifecycle_revoke(JNIEnv*, jclass) { gate.permission(overte::audio::Permission::Revoked); }
extern "C" JNIEXPORT void JNICALL
Java_org_overte_pico_PicoAudioLifecycle_invalidate(JNIEnv*, jclass) { gate.interruption(true); }
extern "C" JNIEXPORT void JNICALL
Java_org_overte_pico_PicoAudioLifecycle_failed(JNIEnv*, jclass) { gate.fail(); }
extern "C" JNIEXPORT void JNICALL
Java_org_overte_pico_PicoAudioLifecycle_stopCompleted(JNIEnv*, jclass, jboolean success) {
    if (success == JNI_TRUE) gate.stop(); else gate.fail();
}
