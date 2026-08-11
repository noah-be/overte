#!/usr/bin/env python3

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ANALYZER = Path(__file__).parents[1] / "tools/analyze-pico4-power.py"
SPEC = importlib.util.spec_from_file_location("pico_power_analyzer", ANALYZER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AnalyzerTests(unittest.TestCase):
    fields = [
        "epoch_s",
        "label",
        "level_pct",
        "voltage_raw",
        "current_raw",
        "charge_raw",
        "temp_raw",
        "plugged",
        "app_pid",
        "brightness_vr",
        "brightness_actual",
        "auto_brightness",
        "refresh_hz",
        "fan_state",
        "cpu_temp_max_mC",
        "gpu_temp_max_mC",
        "skin_temp_c",
        "thermal_status",
        "cpu_policy0_khz",
        "cpu_policy4_khz",
        "cpu_policy7_khz",
        "gpu_hz",
        "fan_rpm",
        "fan_duty",
        "mcu_brightness",
    ]

    def recording(self, rows):
        temporary = tempfile.NamedTemporaryFile(
            mode="w", newline="", suffix=".csv", delete=False
        )
        with temporary:
            writer = csv.DictWriter(temporary, fieldnames=self.fields)
            writer.writeheader()
            writer.writerows(rows)
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        return Path(temporary.name)

    def test_integrates_voltage_and_current(self):
        path = self.recording(
            [
                {
                    "epoch_s": second,
                    "label": "current",
                    "level_pct": 80,
                    "voltage_raw": 4_000_000,
                    "current_raw": -2_000_000,
                    "charge_raw": "",
                    "temp_raw": 250,
                    "plugged": 0,
                    "app_pid": 123,
                }
                for second in (0, 10, 20)
            ]
        )
        summary = MODULE.summarize(path)
        self.assertAlmostEqual(summary.power_w, 8.0)
        self.assertAlmostEqual(summary.energy_wh, 8.0 * 20 / 3600)
        self.assertIsNone(summary.charge_power_w)

    def test_uses_charge_counter_delta(self):
        path = self.recording(
            [
                {
                    "epoch_s": second,
                    "label": "charge",
                    "level_pct": level,
                    "voltage_raw": 4_000,
                    "current_raw": "",
                    "charge_raw": charge,
                    "temp_raw": 250,
                    "plugged": 0,
                    "app_pid": 123,
                }
                for second, level, charge in ((0, 80, 4_000_000), (3600, 70, 3_500_000))
            ]
        )
        summary = MODULE.summarize(path)
        self.assertAlmostEqual(summary.energy_wh, 2.0)
        self.assertAlmostEqual(summary.power_w, 2.0)
        self.assertAlmostEqual(summary.charge_power_w, 2.0)

    def test_rejects_charging_power(self):
        path = self.recording(
            [
                {
                    "epoch_s": second,
                    "label": "charging",
                    "level_pct": 80,
                    "voltage_raw": 4_000,
                    "current_raw": "",
                    "charge_raw": charge,
                    "temp_raw": 250,
                    "plugged": 1,
                    "app_pid": "",
                }
                for second, charge in ((0, 3_500_000), (60, 3_600_000))
            ]
        )
        summary = MODULE.summarize(path)
        self.assertIsNone(summary.energy_wh)
        self.assertIsNone(summary.power_w)
        self.assertIsNone(summary.charge_power_w)
        self.assertIn("invalid", summary.power_method)

    def test_summarizes_display_and_thermal_telemetry(self):
        rows = []
        for second, brightness, fan_state, cpu_temp in (
            (0, 86, 40, 80_000),
            (60, 90, 45, 85_000),
        ):
            rows.append(
                {
                    "epoch_s": second,
                    "label": "telemetry",
                    "level_pct": 80,
                    "voltage_raw": 4_000,
                    "current_raw": -1_000_000,
                    "charge_raw": "",
                    "temp_raw": 250,
                    "plugged": 0,
                    "app_pid": 123,
                    "brightness_vr": brightness,
                    "brightness_actual": 10,
                    "auto_brightness": 0,
                    "refresh_hz": 72,
                    "fan_state": fan_state,
                    "cpu_temp_max_mC": cpu_temp,
                    "gpu_temp_max_mC": 75_000,
                    "skin_temp_c": 60,
                    "thermal_status": 0,
                    "cpu_policy0_khz": 1_804_800,
                    "cpu_policy4_khz": 2_419_200,
                    "cpu_policy7_khz": 2_841_600,
                    "gpu_hz": 587_000_000,
                    "fan_rpm": 7_000 + second * 10,
                    "fan_duty": fan_state,
                    "mcu_brightness": brightness,
                }
            )
        summary = MODULE.summarize(self.recording(rows))
        self.assertEqual(summary.brightness_vr_min, 86)
        self.assertEqual(summary.brightness_vr_max, 90)
        self.assertEqual(summary.mcu_brightness_min, 86)
        self.assertEqual(summary.mcu_brightness_max, 90)
        self.assertEqual(summary.fan_state_max, 45)
        self.assertEqual(summary.fan_rpm_median, 7_300)
        self.assertEqual(summary.fan_duty_max, 45)
        self.assertEqual(summary.cpu_temp_max_c, 85)
        self.assertEqual(summary.refresh_min_hz, summary.refresh_max_hz)
        self.assertEqual(summary.gpu_median_mhz, 587)


if __name__ == "__main__":
    unittest.main()
