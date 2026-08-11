#!/usr/bin/env python3
"""Device-free lifecycle contracts for the Pico OpenXR JNI loader."""

from pathlib import Path
import re
import unittest


SOURCE = (
    Path(__file__).resolve().parents[4]
    / "android/vr/pico/apps/picoInterface/src/main/cpp/OpenXRLoader.cpp"
).read_text(encoding="utf-8")
CONTEXT_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "android/vr/pico/apps/picoInterface/openxr/src/OpenXrContext.cpp"
).read_text(encoding="utf-8")


class OpenXrLoaderLifecycleTest(unittest.TestCase):
    def test_activity_recreation_reuses_process_loader(self):
        reuse = re.search(
            r"if \(loaderJavaVm == vm && loaderApplicationContext\) \{(.*?)\n    \}",
            SOURCE,
            re.DOTALL,
        )
        self.assertIsNotNone(reuse)
        body = reuse.group(1)
        self.assertIn("DeleteGlobalRef(loaderActivity)", body)
        self.assertIn("loaderActivity = newActivity", body)
        self.assertIn("return JNI_TRUE", body)

    def test_candidate_references_publish_only_after_loader_success(self):
        failure = SOURCE.index("if (XR_FAILED(result))")
        publish = SOURCE.index("loaderJavaVm = vm", failure)
        self.assertLess(failure, publish)
        failed_body = SOURCE[failure:publish]
        self.assertIn("DeleteGlobalRef(newApplicationContext)", failed_body)
        self.assertIn("DeleteGlobalRef(newActivity)", failed_body)
        self.assertNotIn("loaderApplicationContext = newApplicationContext", failed_body)

    def test_activity_class_local_reference_is_released(self):
        self.assertIn("DeleteLocalRef(activityClass)", SOURCE)

    def test_destroy_releases_only_the_matching_activity(self):
        release = re.search(
            r"PicoInterfaceActivity_releaseOpenXRActivity\((.*?)\n\}",
            SOURCE,
            re.DOTALL,
        )
        self.assertIsNotNone(release)
        body = release.group(1)
        self.assertIn("IsSameObject(loaderActivity, activity)", body)
        self.assertIn("DeleteGlobalRef(loaderActivity)", body)
        self.assertIn("loaderActivity = nullptr", body)

    def test_activity_consumers_receive_owned_global_references(self):
        self.assertIn("std::mutex loaderMutex", SOURCE)
        self.assertIn("std::lock_guard<std::mutex> guard(loaderMutex)", SOURCE)
        acquire = re.search(
            r'overtePicoOpenXRAcquireActivity\(JNIEnv\* env\) \{(.*?)\n\}',
            SOURCE,
            re.DOTALL,
        )
        self.assertIsNotNone(acquire)
        self.assertIn("env->NewGlobalRef(loaderActivity)", acquire.group(1))
        self.assertNotIn('overtePicoOpenXRActivity()', SOURCE)

    def test_instance_creation_holds_activity_reference_until_call_returns(self):
        acquire = CONTEXT_SOURCE.index("overtePicoOpenXRAcquireActivity(androidEnvironment)")
        create = CONTEXT_SOURCE.index("xrCreateInstance(&info, &_instance)", acquire)
        release = CONTEXT_SOURCE.index("DeleteGlobalRef(androidActivity)", create)
        self.assertLess(acquire, create)
        self.assertLess(create, release)
        self.assertIn("AttachCurrentThread", CONTEXT_SOURCE[acquire - 1200:create])
        self.assertIn("DetachCurrentThread", CONTEXT_SOURCE[release:release + 300])


if __name__ == "__main__":
    unittest.main()
