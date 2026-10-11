"""Reject wrong-process/stale XR frames and independently dark stereo eyes."""
from io import BytesIO
import unittest
from PIL import Image
from tests.device.adapters.pico4.render_observation import native_presentation, black_frame


class RenderObservationTest(unittest.TestCase):
    def setUp(self):
        self.sample = {"schemaVersion":1, "processId":123, "updatedEpochMs":10000,
                       "frameSequence":42, "backend":"OpenXR / OpenGL ES / Adreno",
                       "hardwareAccelerated":True, "surfaceVisible":True}

    def test_native_evidence_must_be_current_and_process_bound(self):
        self.assertEqual(self.sample, native_presentation(self.sample,123,10200))
        for mutation in ({"processId":124}, {"processId":True}, {"updatedEpochMs":10201},
                         {"updatedEpochMs":4000}, {"updatedEpochMs":float("nan")},
                         {"frameSequence":0}, {"frameSequence":True}, {"frameSequence":1.5},
                         {"schemaVersion":True}, {"hardwareAccelerated":1},
                         {"unexpected":True}):
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                native_presentation(self.sample | mutation,123,10200)

    def image(self,left,right):
        frame = Image.new("RGB", (400,200),left)
        frame.paste(right,(200,0,400,200))
        encoded=BytesIO();frame.save(encoded,format="PNG")
        return encoded.getvalue()

    def test_each_eye_must_contain_visible_world_pixels(self):
        self.assertFalse(black_frame(self.image("white","white")))
        for left,right in (("black","white"),("white","black"),("black","black")):
            with self.subTest(left=left,right=right):
                self.assertTrue(black_frame(self.image(left,right)))

    def test_a_bright_border_does_not_conceal_a_black_world(self):
        frame=Image.new("RGB",(400,200),"white")
        frame.paste("black",(20,20,180,180));frame.paste("black",(220,20,380,180))
        encoded=BytesIO();frame.save(encoded,format="PNG")
        self.assertTrue(black_frame(encoded.getvalue()))

if __name__ == "__main__":
    unittest.main()
