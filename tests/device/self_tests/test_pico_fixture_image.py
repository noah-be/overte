"""The scene image gate must reject empty views and unrelated visible worlds."""
from io import BytesIO
import unittest
from PIL import Image, ImageDraw
from tests.device.adapters.pico4.fixture_image import inspect_fixture_image


def png(frame):
    encoded = BytesIO()
    frame.save(encoded, format="PNG")
    return encoded.getvalue()


class FixtureImageTest(unittest.TestCase):
    def fixture(self):
        frame = Image.new("RGB", (800,400), "black")
        draw = ImageDraw.Draw(frame)
        for start in (0,400):
            draw.rectangle((start+60,60,start+340,300), fill=(190,190,190))
            draw.rectangle((start+120,120,start+280,200), fill=(180,80,180))
            draw.rectangle((start+180,100,start+220,140), fill=(255,150,40))
        return frame

    def test_authored_geometry_is_visible_in_both_eyes(self):
        self.assertTrue(inspect_fixture_image(png(self.fixture()))["fixtureVisible"])

    def test_black_and_blue_horizon_are_not_loaded_worlds(self):
        frame = Image.new("RGB", (800,400), "black")
        ImageDraw.Draw(frame).rectangle((0,190,800,210), fill=(30,100,230))
        self.assertFalse(inspect_fixture_image(png(frame))["fixtureVisible"])

    def test_one_working_eye_does_not_hide_a_missing_world(self):
        frame = self.fixture()
        ImageDraw.Draw(frame).rectangle((400,0,800,400), fill="black")
        self.assertFalse(inspect_fixture_image(png(frame))["fixtureVisible"])

    def test_system_toolbar_colors_do_not_count_as_fixture_geometry(self):
        frame = Image.new("RGB", (800,400), "gray")
        draw = ImageDraw.Draw(frame)
        draw.rectangle((0,350,800,365), fill=(180,80,180))
        draw.rectangle((0,365,800,400), fill=(255,150,40))
        self.assertFalse(inspect_fixture_image(png(frame))["fixtureVisible"])

    def test_malformed_image_is_an_infrastructure_failure(self):
        with self.assertRaises(Exception):
            inspect_fixture_image(b"not a screenshot")


if __name__ == "__main__":
    unittest.main()
