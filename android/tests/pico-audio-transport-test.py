#!/usr/bin/env python3
"""Source contracts for Pico native microphone FIFO boundaries."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "libraries/audio-client/src/AudioClient.cpp").read_text(encoding="utf-8")
JAVA = (
    ROOT
    / "android/apps/picoInterface/src/main/java/org/overte/pico/AndroidAudioInput.java"
).read_text(encoding="utf-8")


class PicoAudioTransportTests(unittest.TestCase):
    def test_complete_start_and_stop_transactions_are_serialized(self):
        self.assertIn("public static synchronized boolean start(", JAVA)
        self.assertIn("public static synchronized void stop()", JAVA)
        start = JAVA.index("public static synchronized boolean start(")
        nested_stop = JAVA.index("stop();", start)
        create = JAVA.index("new AudioRecord(", nested_stop)
        publish = JAVA.index("recorder = newRecorder", create)
        self.assertLess(nested_stop, create)
        self.assertLess(create, publish)

    def test_jni_rejects_unconfigured_or_misaligned_callbacks_before_copy(self):
        callback = re.search(
            r"Java_org_overte_pico_AndroidAudioInput_nativeOnAudioData\((.*?)\n\}",
            SOURCE,
            re.DOTALL,
        )
        self.assertIsNotNone(callback)
        body = callback.group(0)
        validation = body.index("androidAudioCallbackSizeValid(bytesRead)")
        allocation = body.index("QByteArray audio(bytesRead")
        copy = body.index("GetByteArrayRegion")
        self.assertLess(validation, allocation)
        self.assertLess(validation, copy)

    def test_size_validation_uses_current_pcm_frame_and_active_capacity(self):
        validator = re.search(
            r"static bool androidAudioCallbackSizeValid\(.*?\n\}", SOURCE, re.DOTALL
        )
        self.assertIsNotNone(validator)
        body = validator.group(0)
        self.assertIn("androidAudioTransportMutex", body)
        self.assertIn("androidAudioMaxBufferBytes > 0", body)
        self.assertIn("bytes % androidAudioBytesPerFrame == 0", body)
        self.assertIn("androidAudioDroppedBytes += bytes;", body)

    def test_enqueue_rechecks_alignment_and_does_not_feed_watchdog(self):
        enqueue = re.search(
            r"static bool enqueueAndroidAudio\(.*?\n\}", SOURCE, re.DOTALL
        )
        self.assertIsNotNone(enqueue)
        body = enqueue.group(0)
        reject = body.index("audio.size() % androidAudioBytesPerFrame != 0")
        callback_count = body.index("++androidAudioCapturedCallbacksSinceWatchdog")
        self.assertLess(reject, callback_count)
        self.assertIn("androidAudioDroppedBytes += audio.size();", body)

    def test_drain_slice_is_pcm_frame_aligned(self):
        drain = re.search(
            r"static QByteArray takePendingAndroidAudio\(.*?\n\}", SOURCE, re.DOTALL
        )
        self.assertIsNotNone(drain)
        body = drain.group(0)
        self.assertIn("boundedBytes % androidAudioBytesPerFrame", body)
        self.assertIn("if (bytes <= 0)", body)

    def test_capture_thread_startup_rolls_back_recorder_state(self):
        start = JAVA.index("public static synchronized boolean start(")
        end = JAVA.index("public static synchronized void stop()", start)
        body = JAVA[start:end]
        create = body.index("newCaptureThread = new Thread")
        publish = body.index("recorder = newRecorder", create)
        thread_start = body.index("newCaptureThread.start()", publish)
        catch = body.index('Log.e(TAG, "Could not start microphone capture thread"', thread_start)
        clear_running = body.index("running = false", catch)
        clear_recorder = body.index("recorder = null", clear_running)
        clear_thread = body.index("captureThread = null", clear_recorder)
        release = body.index("stopAndRelease(newRecorder)", clear_thread)
        self.assertLess(create, publish)
        self.assertLess(publish, thread_start)
        self.assertLess(thread_start, catch)
        self.assertLess(catch, clear_running)
        self.assertLess(clear_running, clear_recorder)
        self.assertLess(clear_recorder, clear_thread)
        self.assertLess(clear_thread, release)
        self.assertIn("catch (RuntimeException | OutOfMemoryError exception)", body)

    def test_capture_priority_failure_is_contained(self):
        loop = JAVA.index("private static void captureLoop")
        loop_body = JAVA[loop:]
        self.assertIn("prioritizeCurrentThreadForAudio();", loop_body)
        self.assertNotIn("Process.setThreadPriority", loop_body)

    def test_unexpected_capture_exit_claims_cleanup_once(self):
        loop = JAVA.index("private static void captureLoop")
        loop_body = JAVA[loop:]
        self.assertIn("catch (RuntimeException | OutOfMemoryError exception)", loop_body)
        finally_block = loop_body.index("finally {")
        identity = loop_body.index("if (recorder == activeRecorder)", finally_block)
        stop_running = loop_body.index("running = false", identity)
        release = loop_body.index("stopAndRelease(activeRecorder)", stop_running)
        clear_recorder = loop_body.index("recorder = null", release)
        thread_identity = loop_body.index("captureThread == Thread.currentThread()", clear_recorder)
        claim = loop_body.index("releasedRecorder = true", thread_identity)
        self.assertLess(identity, stop_running)
        self.assertLess(stop_running, release)
        self.assertLess(release, clear_recorder)
        self.assertLess(clear_recorder, thread_identity)
        self.assertLess(thread_identity, claim)
        lock_start = loop_body.index("synchronized (LOCK)", finally_block)
        lock_end = loop_body.index("if (releasedRecorder)", claim)
        self.assertLess(lock_start, release)
        self.assertLess(release, lock_end)

    def test_capture_buffer_allocation_is_inside_oom_cleanup_boundary(self):
        loop = JAVA.index("private static void captureLoop")
        loop_body = JAVA[loop:]
        guarded = loop_body.index("try {")
        allocation = loop_body.index("new byte[callbackBytes]", guarded)
        catch = loop_body.index("catch (RuntimeException | OutOfMemoryError exception)", allocation)
        finally_block = loop_body.index("finally {", catch)
        release = loop_body.index("stopAndRelease(activeRecorder)", finally_block)
        self.assertLess(guarded, allocation)
        self.assertLess(allocation, catch)
        self.assertLess(catch, finally_block)
        self.assertLess(finally_block, release)

    def test_audio_stop_and_release_driver_errors_are_contained(self):
        stop_start = JAVA.index("public static synchronized void stop()")
        stop_end = JAVA.index("private static int androidAudioSource", stop_start)
        stop = JAVA[stop_start:stop_end]
        stop_call = stop.index("oldRecorder.stop()")
        stop_catch = stop.index("catch (RuntimeException exception)", stop_call)
        join = stop.index("oldThread.join(1000)", stop_catch)
        release_call = stop.index("oldRecorder.release()", join)
        release_catch = stop.index("catch (RuntimeException exception)", release_call)
        self.assertLess(stop_call, stop_catch)
        self.assertLess(stop_catch, join)
        self.assertLess(join, release_call)
        self.assertLess(release_call, release_catch)

        helper_start = JAVA.index("private static void stopAndRelease")
        helper_end = JAVA.index("private static void captureLoop", helper_start)
        helper = JAVA[helper_start:helper_end]
        helper_stop = helper.index("activeRecorder.stop()")
        helper_stop_catch = helper.index("catch (RuntimeException exception)", helper_stop)
        helper_release = helper.index("activeRecorder.release()", helper_stop_catch)
        helper_release_catch = helper.index("catch (RuntimeException exception)", helper_release)
        self.assertLess(helper_stop, helper_stop_catch)
        self.assertLess(helper_stop_catch, helper_release)
        self.assertLess(helper_release, helper_release_catch)


if __name__ == "__main__":
    unittest.main()
