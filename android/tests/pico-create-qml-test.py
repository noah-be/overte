#!/usr/bin/env python3
"""Device-free source contracts for native Pico Create properties."""

from pathlib import Path
import re
import unittest


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "scripts/system/create/qml/PicoProperties.qml"
).read_text(encoding="utf-8")


class PicoCreateQmlTest(unittest.TestCase):
    def test_numeric_properties_reject_nonfinite_values(self):
        helper = re.search(r"function finiteNumber\(.*?\n    \}", SOURCE, re.DOTALL)
        self.assertIsNotNone(helper)
        self.assertIn("isFinite(number) ? number : fallback", helper.group(0))
        self.assertIn("return finiteNumber(field.text, 0)", SOURCE)
        self.assertIn("finiteNumber(value, 0).toFixed(3)", SOURCE)

    def test_controller_adjustment_requires_one_discrete_step(self):
        adjust = re.search(
            r"function adjustFocusedNumber\(.*?\n    \}", SOURCE, re.DOTALL
        )
        self.assertIsNotNone(adjust)
        body = adjust.group(0)
        self.assertIn("direction !== -1 && direction !== 1", body)
        self.assertIn("finiteNumber(focusedNumericField.text, 0)", body)

    def test_focus_step_is_positive_and_finite(self):
        self.assertIn(
            "Math.max(0.001, finiteNumber(step, 0.01))",
            SOURCE,
        )


if __name__ == "__main__":
    unittest.main()
