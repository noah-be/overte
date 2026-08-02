#!/usr/bin/env python3
"""Summarize CSV recordings produced by pico4-power-test.sh."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path


def number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        result = float(value)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def column_numbers(rows: list[dict[str, str]], key: str) -> list[float]:
    return [value for row in rows if (value := number(row.get(key))) is not None]


def minimum(values: list[float]) -> float | None:
    return min(values) if values else None


def maximum(values: list[float]) -> float | None:
    return max(values) if values else None


@dataclass
class Summary:
    path: Path
    label: str
    power_profile: str
    foveation: str
    samples: int
    duration_s: float
    level_start: float | None
    level_end: float | None
    voltage_v: float | None
    current_a: float | None
    power_w: float | None
    energy_wh: float | None
    charge_power_w: float | None
    temp_start_c: float | None
    temp_max_c: float | None
    app_present_pct: float
    charging_samples: int
    power_method: str
    brightness_vr_min: float | None
    brightness_vr_max: float | None
    brightness_actual_min: float | None
    brightness_actual_max: float | None
    mcu_brightness_min: float | None
    mcu_brightness_max: float | None
    auto_brightness_values: set[str]
    refresh_min_hz: float | None
    refresh_max_hz: float | None
    fan_state_min: float | None
    fan_state_max: float | None
    fan_rpm_min: float | None
    fan_rpm_median: float | None
    fan_rpm_max: float | None
    fan_duty_min: float | None
    fan_duty_max: float | None
    cpu_temp_max_c: float | None
    gpu_temp_max_c: float | None
    skin_temp_max_c: float | None
    thermal_status_max: float | None
    cpu0_median_mhz: float | None
    cpu4_median_mhz: float | None
    cpu7_median_mhz: float | None
    gpu_median_mhz: float | None


def scaled_voltage(raw: float | None) -> float | None:
    if raw is None:
        return None
    absolute = abs(raw)
    if absolute > 100_000:
        return raw / 1_000_000
    if absolute > 100:
        return raw / 1_000
    return raw


def scaled_current(raw: float | None) -> float | None:
    if raw is None:
        return None
    # Android BatteryManager CURRENT_NOW and power_supply current_now use uA.
    return raw / 1_000_000


def scaled_charge(raw: float | None) -> float | None:
    if raw is None:
        return None
    # Android BatteryManager CHARGE_COUNTER and power_supply charge_now use uAh.
    return raw / 1_000_000


def scaled_temperature(raw: float | None) -> float | None:
    if raw is None:
        return None
    # Both dumpsys battery and power_supply temp report tenths of a degree C.
    return raw / 10


def integrate_power(rows: list[dict[str, str]]) -> tuple[float | None, float | None]:
    points: list[tuple[float, float]] = []
    for row in rows:
        timestamp = number(row.get("epoch_s"))
        voltage = scaled_voltage(number(row.get("voltage_raw")))
        current = scaled_current(number(row.get("current_raw")))
        if timestamp is not None and voltage is not None and current is not None:
            points.append((timestamp, abs(voltage * current)))
    if len(points) < 2:
        return None, None
    energy_ws = sum(
        (previous[1] + current[1]) * 0.5 * (current[0] - previous[0])
        for previous, current in zip(points, points[1:])
        if 0 < current[0] - previous[0] < 60
    )
    elapsed = points[-1][0] - points[0][0]
    if elapsed <= 0:
        return None, None
    return energy_ws / elapsed, energy_ws / 3600


def summarize(path: Path) -> Summary:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error) as error:
        raise ValueError(f"cannot read {path}: {error}") from error
    if not rows:
        raise ValueError(f"{path}: no samples")

    required = {"epoch_s", "label", "level_pct", "voltage_raw", "current_raw"}
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")

    times = [value for row in rows if (value := number(row.get("epoch_s"))) is not None]
    if len(times) < 2:
        raise ValueError(f"{path}: fewer than two valid timestamps")
    levels = [number(row.get("level_pct")) for row in rows]
    valid_levels = [value for value in levels if value is not None]
    voltages = [
        value
        for row in rows
        if (value := scaled_voltage(number(row.get("voltage_raw")))) is not None
    ]
    currents = [
        abs(value)
        for row in rows
        if (value := scaled_current(number(row.get("current_raw")))) is not None
    ]
    temperatures = [
        value
        for row in rows
        if (value := scaled_temperature(number(row.get("temp_raw")))) is not None
    ]
    charges = [
        value
        for row in rows
        if (value := scaled_charge(number(row.get("charge_raw")))) is not None
    ]

    charging_samples = sum(
        (row.get("plugged") or "").strip() not in {"", "0"} for row in rows
    )
    power_w, energy_wh = integrate_power(rows)
    method = "voltage x current (trapezoidal integration)" if power_w is not None else "unavailable"
    duration_s = max(times) - min(times)
    voltage_v = median(voltages)
    current_a = median(currents)

    charge_energy_wh = (
        abs(charges[-1] - charges[0]) * voltage_v
        if len(charges) >= 2 and voltage_v is not None
        else None
    )
    charge_power_w = (
        charge_energy_wh * 3600 / duration_s
        if charge_energy_wh is not None and duration_s
        else None
    )
    if energy_wh is None and charge_energy_wh is not None:
        energy_wh = charge_energy_wh
        power_w = charge_power_w
        method = "charge-counter delta x median voltage"

    if charging_samples:
        power_w = None
        energy_wh = None
        charge_power_w = None
        method = "invalid while external power is connected"

    app_samples = sum(bool((row.get("app_pid") or "").strip()) for row in rows)
    brightness_vr = column_numbers(rows, "brightness_vr")
    brightness_actual = column_numbers(rows, "brightness_actual")
    mcu_brightness = column_numbers(rows, "mcu_brightness")
    refresh_rates = column_numbers(rows, "refresh_hz")
    fan_states = column_numbers(rows, "fan_state")
    fan_rpms = column_numbers(rows, "fan_rpm")
    fan_duties = column_numbers(rows, "fan_duty")
    cpu_temperatures = [value / 1000 for value in column_numbers(rows, "cpu_temp_max_mC")]
    gpu_temperatures = [value / 1000 for value in column_numbers(rows, "gpu_temp_max_mC")]
    skin_temperatures = column_numbers(rows, "skin_temp_c")
    thermal_statuses = column_numbers(rows, "thermal_status")
    cpu0_frequencies = [value / 1000 for value in column_numbers(rows, "cpu_policy0_khz")]
    cpu4_frequencies = [value / 1000 for value in column_numbers(rows, "cpu_policy4_khz")]
    cpu7_frequencies = [value / 1000 for value in column_numbers(rows, "cpu_policy7_khz")]
    gpu_frequencies = [value / 1_000_000 for value in column_numbers(rows, "gpu_hz")]
    auto_brightness_values = {
        value
        for row in rows
        if (value := (row.get("auto_brightness") or "").strip())
    }
    return Summary(
        path=path,
        label=(rows[0].get("label") or path.stem).strip(),
        power_profile=(rows[0].get("power_profile") or "not recorded").strip(),
        foveation=(rows[0].get("foveation") or "not recorded").strip(),
        samples=len(rows),
        duration_s=duration_s,
        level_start=valid_levels[0] if valid_levels else None,
        level_end=valid_levels[-1] if valid_levels else None,
        voltage_v=voltage_v,
        current_a=current_a,
        power_w=power_w,
        energy_wh=energy_wh,
        charge_power_w=charge_power_w,
        temp_start_c=temperatures[0] if temperatures else None,
        temp_max_c=max(temperatures) if temperatures else None,
        app_present_pct=app_samples * 100 / len(rows),
        charging_samples=charging_samples,
        power_method=method,
        brightness_vr_min=minimum(brightness_vr),
        brightness_vr_max=maximum(brightness_vr),
        brightness_actual_min=minimum(brightness_actual),
        brightness_actual_max=maximum(brightness_actual),
        mcu_brightness_min=minimum(mcu_brightness),
        mcu_brightness_max=maximum(mcu_brightness),
        auto_brightness_values=auto_brightness_values,
        refresh_min_hz=minimum(refresh_rates),
        refresh_max_hz=maximum(refresh_rates),
        fan_state_min=minimum(fan_states),
        fan_state_max=maximum(fan_states),
        fan_rpm_min=minimum(fan_rpms),
        fan_rpm_median=median(fan_rpms),
        fan_rpm_max=maximum(fan_rpms),
        fan_duty_min=minimum(fan_duties),
        fan_duty_max=maximum(fan_duties),
        cpu_temp_max_c=maximum(cpu_temperatures),
        gpu_temp_max_c=maximum(gpu_temperatures),
        skin_temp_max_c=maximum(skin_temperatures),
        thermal_status_max=maximum(thermal_statuses),
        cpu0_median_mhz=median(cpu0_frequencies),
        cpu4_median_mhz=median(cpu4_frequencies),
        cpu7_median_mhz=median(cpu7_frequencies),
        gpu_median_mhz=median(gpu_frequencies),
    )


def display(value: float | None, precision: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{precision}f}"


def display_range(low: float | None, high: float | None, precision: int = 1) -> str:
    if low is None or high is None:
        return "n/a"
    if low == high:
        return display(low, precision)
    return f"{display(low, precision)} -> {display(high, precision)}"


def print_summary(summary: Summary) -> None:
    hours = summary.duration_s / 3600
    level_delta = (
        summary.level_start - summary.level_end
        if summary.level_start is not None and summary.level_end is not None
        else None
    )
    discharge_rate = level_delta / hours if level_delta is not None and hours else None
    print(f"\n{summary.label} ({summary.path})")
    print(f"  Overte power profile:    {summary.power_profile}")
    print(f"  OpenXR foveation:        {summary.foveation}")
    print(f"  Samples / duration:       {summary.samples} / {summary.duration_s:.0f} s")
    print(
        "  Battery level:           "
        f"{display(summary.level_start, 0)}% -> {display(summary.level_end, 0)}%"
    )
    print(f"  Discharge rate:          {display(discharge_rate)} %/h")
    print(f"  Median voltage:          {display(summary.voltage_v, 3)} V")
    print(f"  Median |current|:        {display(summary.current_a, 3)} A")
    print(f"  Average power:           {display(summary.power_w, 3)} W")
    print(f"  Charge-counter check:    {display(summary.charge_power_w, 3)} W")
    print(f"  Measured energy:         {display(summary.energy_wh, 4)} Wh")
    print(
        "  Battery temperature:     "
        f"{display(summary.temp_start_c, 1)} C -> max {display(summary.temp_max_c, 1)} C"
    )
    print(f"  Overte process present:  {summary.app_present_pct:.1f}% of samples")
    print(f"  Power calculation:       {summary.power_method}")
    print("  Display / cooling:")
    print(
        "    VR brightness:         "
        f"{display_range(summary.brightness_vr_min, summary.brightness_vr_max, 0)} / 255"
    )
    print(
        "    Reported panel level:  "
        f"{display_range(summary.brightness_actual_min, summary.brightness_actual_max, 0)} / 255"
    )
    print(
        "    MCU brightness:        "
        f"{display_range(summary.mcu_brightness_min, summary.mcu_brightness_max, 0)} / 100"
    )
    auto_brightness = ", ".join(sorted(summary.auto_brightness_values)) or "n/a"
    print(f"    Auto brightness:       {auto_brightness}")
    print(
        "    Refresh rate:          "
        f"{display_range(summary.refresh_min_hz, summary.refresh_max_hz, 2)} Hz"
    )
    print(
        "    Fan state (not RPM):   "
        f"{display_range(summary.fan_state_min, summary.fan_state_max, 0)}"
    )
    print(
        "    Fan RPM min/med/max:   "
        f"{display(summary.fan_rpm_min, 0)} / {display(summary.fan_rpm_median, 0)} / "
        f"{display(summary.fan_rpm_max, 0)}"
    )
    print(
        "    Fan duty:              "
        f"{display_range(summary.fan_duty_min, summary.fan_duty_max, 0)} / 100"
    )
    print(
        "    Max CPU/GPU/skin temp: "
        f"{display(summary.cpu_temp_max_c, 1)} / {display(summary.gpu_temp_max_c, 1)} / "
        f"{display(summary.skin_temp_max_c, 1)} C"
    )
    print(f"    Max thermal status:    {display(summary.thermal_status_max, 0)}")
    print(
        "    Median CPU MHz:        "
        f"{display(summary.cpu0_median_mhz, 0)} / {display(summary.cpu4_median_mhz, 0)} / "
        f"{display(summary.cpu7_median_mhz, 0)}"
    )
    print(f"    Median GPU MHz:        {display(summary.gpu_median_mhz, 0)}")
    if summary.charging_samples:
        print(f"  WARNING: external power appeared in {summary.charging_samples} samples")
    if (
        summary.power_w is not None
        and summary.charge_power_w is not None
        and summary.power_w > 0
        and abs(summary.charge_power_w - summary.power_w) / summary.power_w > 0.15
    ):
        difference = abs(summary.charge_power_w - summary.power_w) / summary.power_w * 100
        print(f"  WARNING: current and charge estimates differ by {difference:.1f}%")
    if summary.duration_s < 1200:
        print("  WARNING: runs shorter than 20 minutes are useful only for setup checks")
    if summary.brightness_vr_min != summary.brightness_vr_max:
        print("  WARNING: VR brightness changed during the run")
    if summary.mcu_brightness_min != summary.mcu_brightness_max:
        print("  WARNING: MCU display brightness changed during the run")
    if summary.refresh_min_hz != summary.refresh_max_hz:
        print("  WARNING: refresh rate changed during the run")
    if len(summary.auto_brightness_values) > 1:
        print("  WARNING: auto-brightness state changed during the run")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="+", type=Path, help="recorded power-test CSV")
    args = parser.parse_args()
    try:
        summaries = [summarize(path) for path in args.csv]
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    for summary in summaries:
        print_summary(summary)
    if len(summaries) > 1:
        measurable = [summary for summary in summaries if summary.power_w is not None]
        print("\nPower comparison")
        if measurable:
            baseline = measurable[0]
            print(f"  Baseline: {baseline.label} ({baseline.power_w:.3f} W)")
            for summary in measurable[1:]:
                difference = summary.power_w - baseline.power_w
                print(f"  {summary.label}: {summary.power_w:.3f} W ({difference:+.3f} W)")
        else:
            print("  Absolute comparison unavailable: no run exposed current or charge data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
