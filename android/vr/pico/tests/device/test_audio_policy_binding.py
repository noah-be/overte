#!/usr/bin/env python3
"""Real native callback and Java consumer; fake Qt queue and Android audio driver."""
# SPDX-License-Identifier: Apache-2.0
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / 'android/vr/pico/apps/picoInterface'
JAVA = APP / 'src/main/java/org/overte/pico'
HERE = Path(__file__).parent


class AudioPolicyBindingTest(unittest.TestCase):
    def test_actual_java_and_native_policy_callback(self):
        spec = importlib.util.spec_from_file_location('original_pico_policy_test',
            ROOT / 'tests/device/contracts/audio/test_pico_policy.py')
        contract = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(contract)
        callback = contract.body('Java_org_overte_pico_AndroidAudioInput_nativePolicyChanged(')
        source = '''#include "libraries/audio-client/src/PicoCapturePolicy.h"
#include <jni.h>
namespace Qt { constexpr int QueuedConnection = 1; }
struct AudioClient {};
struct Handle { explicit operator bool() const { return true; } AudioClient* data() { return nullptr; } };
struct DependencyManager { template<class T> static Handle get() { return {}; } };
static std::atomic<int> clearCount { 0 }, queuedCount { 0 }, deliveredCount { 0 };
static bool failInitialization = false;
void finishAndroidAudioDrain(bool) { ++clearCount; }
struct QMetaObject { static bool invokeMethod(AudioClient*, const char*, int) { ++queuedCount; return true; } };
static overte::audio::PicoCapturePolicy picoCapturePolicy;
static std::atomic<bool> picoAudioRefreshScheduled { false };
extern "C" JNIEXPORT void JNICALL
Java_org_overte_pico_AndroidAudioInput_nativePolicyChanged(JNIEnv*, jclass, jboolean allowed) ''' + callback + '''
extern "C" JNIEXPORT void JNICALL Java_org_overte_pico_AndroidAudioInput_nativeInitialize(JNIEnv* env, jclass) {
    if (failInitialization) env->ThrowNew(env->FindClass("java/lang/IllegalStateException"), "PRIVATE_INITIALIZATION_CANARY");
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_pico_PicoAudioPolicyBindingTest_failInitialization(JNIEnv*, jclass, jboolean fail) { failInitialization = fail; }
extern "C" JNIEXPORT void JNICALL Java_org_overte_pico_AndroidAudioInput_nativeOnAudioData(JNIEnv*, jclass, jbyteArray, jint) { ++deliveredCount; }
extern "C" JNIEXPORT jboolean JNICALL Java_org_overte_pico_PicoAudioPolicyBindingTest_allowed(JNIEnv*, jclass) { return picoCapturePolicy.allows(); }
extern "C" JNIEXPORT jlong JNICALL Java_org_overte_pico_PicoAudioPolicyBindingTest_epoch(JNIEnv*, jclass) { return picoCapturePolicy.ticket(); }
extern "C" JNIEXPORT jint JNICALL Java_org_overte_pico_PicoAudioPolicyBindingTest_clears(JNIEnv*, jclass) { return clearCount; }
extern "C" JNIEXPORT jint JNICALL Java_org_overte_pico_PicoAudioPolicyBindingTest_queued(JNIEnv*, jclass) { return queuedCount; }
extern "C" JNIEXPORT jint JNICALL Java_org_overte_pico_PicoAudioPolicyBindingTest_delivered(JNIEnv*, jclass) { return deliveredCount; }
extern "C" JNIEXPORT void JNICALL Java_org_overte_pico_PicoAudioPolicyBindingTest_acknowledgeRefresh(JNIEnv*, jclass) { picoAudioRefreshScheduled.store(false); }
'''
        jdk = Path(shutil.which('javac')).resolve().parents[1]
        sdk = Path(os.environ.get('ANDROID_SDK_ROOT', str(Path.home() / 'Android/Sdk')))
        with tempfile.TemporaryDirectory(prefix='pico-live-audio-policy-') as temporary:
            scratch = Path(temporary)
            cpp = scratch / 'original-callback-with-test-boundaries.cpp'
            cpp.write_text(source)
            library = scratch / 'libpico-policy-test.so'
            subprocess.run(['c++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-pthread', '-shared', '-fPIC',
                '-I' + str(ROOT), '-I' + str(jdk / 'include'), '-I' + str(jdk / 'include/linux'),
                str(cpp), str(APP / 'audio/PicoAudioLifecycle.cpp'), '-o', str(library)], check=True, timeout=30)
            names = ['AndroidAudioInput.java', 'AndroidAudioInputPolicy.java', 'PicoAudioCaptureState.java',
                     'PicoAudioLifecycle.java', 'PicoAudioShutdown.java', 'RedactingDiagnostics.java']
            subprocess.run(['javac', '-cp', str(sdk / 'platforms/android-26/android.jar'), '-d', str(scratch),
                *[str(JAVA / name) for name in names],
                str(ROOT / 'security/redaction/java/org/overte/security/SafeDiagnostics.java'),
                *map(str, (HERE / 'audio-policy-stubs').rglob('*.java')),
                str(HERE / 'java-stubs/android/util/Log.java'),
                str(HERE / 'java/org/overte/pico/PicoAudioPolicyBindingTest.java')], check=True, timeout=30)
            subprocess.run(['java', '-cp', str(scratch), 'org.overte.pico.PicoAudioPolicyBindingTest', str(library)],
                check=True, timeout=15)
            # A mismatched old Shared binary must not turn Java capture on.
            cpp.write_text(source.replace('Java_org_overte_pico_AndroidAudioInput_nativePolicyChanged',
                                          'TestOnlyUnavailablePolicyChanged'))
            absent = scratch / 'libpico-policy-absent.so'
            subprocess.run(['c++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-pthread', '-shared', '-fPIC',
                '-I' + str(ROOT), '-I' + str(jdk / 'include'), '-I' + str(jdk / 'include/linux'),
                str(cpp), str(APP / 'audio/PicoAudioLifecycle.cpp'), '-o', str(absent)], check=True, timeout=30)
            subprocess.run(['java', '-cp', str(scratch), 'org.overte.pico.PicoAudioPolicyBindingTest', str(absent), 'missing'],
                check=True, timeout=10)

    def test_internal_effects_cannot_publish_reopen(self):
        source = (JAVA / 'AndroidAudioInput.java').read_text()
        stop = source.split('public static synchronized void stop()', 1)[1].split('public static synchronized void setForeground', 1)[0]
        self.assertNotIn('publishPolicy(', stop)
        self.assertNotIn('resumeRequest', source)
        self.assertEqual(source.count('publishPolicy(true)'), 0)
        policy = source.split('private static void updateExternalPolicy()', 1)[1].split('private static void publishPolicy', 1)[0]
        self.assertIn('foreground && !muted', policy)
        self.assertIn('microphonePermissionGranted() && SHUTDOWN.ready()', policy)
        self.assertLess(policy.index('publishPolicy(allowed)'), policy.index('stop()'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
