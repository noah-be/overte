# SPDX-License-Identifier: Apache-2.0
import pathlib
import subprocess
import tempfile
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[4]
SOURCE = ROOT / 'libraries/audio-client/src/AudioClient.cpp'

def body(signature):
    text = SOURCE.read_text().split(signature, 1)[1]
    start = text.index('{')
    level = 0
    for index in range(start, len(text)):
        if text[index] == '{': level += 1
        if text[index] == '}': level -= 1
        if not level: return text[start:index + 1]
    raise AssertionError('missing function body')

class PicoPolicyTests(unittest.TestCase):
    def compile_run(self, source, temporary):
        binary = temporary / 'test'
        subprocess.run(['c++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-pthread', '-I', str(ROOT),
                        str(source), '-o', str(binary)], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=10)

    def test_real_policy_epoch_concurrency(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.compile_run(pathlib.Path(__file__).with_name('pico-policy-test.cpp'), pathlib.Path(temporary))

    def test_actual_native_policy_callback_closes_fifo_and_coalesces(self):
        callback = body('Java_org_overte_pico_AndroidAudioInput_nativePolicyChanged(')
        source = '''#include "libraries/audio-client/src/PicoCapturePolicy.h"
#include <cassert>
using jboolean = bool;
constexpr bool JNI_TRUE = true;
namespace Qt { constexpr int QueuedConnection = 1; }
struct AudioClient {};
struct Handle { explicit operator bool() const { return true; } AudioClient* data() { return nullptr; } };
struct DependencyManager { template<class T> static Handle get() { return {}; } };
static int clears = 0, queued = 0;
static bool invocationSucceeds = true;
void finishAndroidAudioDrain(bool discard) { assert(discard); ++clears; }
struct QMetaObject { static bool invokeMethod(AudioClient*, const char*, int) { ++queued; return invocationSucceeds; } };
static overte::audio::PicoCapturePolicy picoCapturePolicy;
static std::atomic<bool> picoAudioRefreshScheduled { false };
void callback(jboolean allowed) ''' + callback + '''
int main() {
 callback(false); assert(clears == 0 && queued == 0);
 callback(true); auto old = picoCapturePolicy.ticket(); assert(clears == 1 && queued == 1);
 callback(true); assert(clears == 1 && queued == 1);
 callback(false); assert(clears == 2 && queued == 1 && !picoCapturePolicy.accepts(old));
 callback(true); assert(clears == 3 && queued == 1 && !picoCapturePolicy.accepts(old));
 picoAudioRefreshScheduled.store(false); invocationSucceeds = false;
 callback(false); assert(!picoAudioRefreshScheduled.load() && !picoCapturePolicy.allows());
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / 'callback.cpp'
            path.write_text(source)
            self.compile_run(path, pathlib.Path(temporary))

    def test_actual_shared_call_sites_and_disabled_recording(self):
        mute = body('void AudioClient::setMuted(')
        self.assertIn('setAndroidAudioMuted(muted)', mute)
        self.assertIn('refreshAndroidAudioInput()', mute)
        refresh = body('void AudioClient::refreshAndroidAudioInput(')
        self.assertIn('switchInputToAudioDevice(HifiAudioDeviceInfo(), true)', refresh)
        self.assertIn('_inputRingBuffer.clear()', refresh)
        self.assertIn('_audioLifecycleRunning && !_isMuted && picoCapturePolicy.allows()', refresh)
        pcm = body('void AudioClient::processMicAudioInput(')
        self.assertIn('_picoInputPolicyTicket != policyTicket', pcm)
        self.assertGreaterEqual(pcm.count('picoCapturePolicy.accepts(policyTicket)'), 2)
        capture = body('static int picoMicCaptureSeconds(')
        self.assertIn('return 0;', capture)
        self.assertNotIn('__system_property_get', capture)
        self.assertNotIn('ExceptionDescribe()', SOURCE.read_text())

if __name__ == '__main__': unittest.main()
