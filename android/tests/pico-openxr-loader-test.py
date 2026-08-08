#!/usr/bin/env python3
"""Device-free lifecycle contracts for the Pico OpenXR JNI loader."""

from pathlib import Path
import re
import unittest


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "android/apps/picoInterface/src/main/cpp/OpenXRLoader.cpp"
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


if __name__ == "__main__":
    unittest.main()
