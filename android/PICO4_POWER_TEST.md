# Measure Overte power use on Pico 4

This test setup records the battery telemetry exposed by the Pico Android
firmware and compares repeatable scenarios. It measures the complete headset,
not Overte in isolation. The difference between an idle baseline and an Overte
run is an estimate of the application's additional power cost.

> [!IMPORTANT]
> Internal battery telemetry is suitable for development comparisons, but it is
> not laboratory-grade measurement. Sensor availability, update rate, accuracy,
> and current-sign convention depend on the headset firmware.

## Quick check

Connect one Pico 4 via USB, enable USB debugging, accept the authorization
prompt in the headset, and run from `android/`:

```bash
./pico4-power-test.sh doctor
```

The check reports whether the firmware exposes voltage, current, charge, level,
and temperature. Select a device explicitly if several Android devices are
connected:

```bash
ANDROID_SERIAL=<serial> ./pico4-power-test.sh doctor
```

`PICO_ADB=/path/to/adb` can override ADB. Otherwise the script uses ADB from
`ANDROID_SDK_ROOT`, `$HOME/Android/Sdk`, or `PATH`.

The Pico 4 supplies power over a normal USB debugging connection. For an
unplugged measurement, switch ADB to the local Wi-Fi network while USB is still
connected:

```bash
adb tcpip 5555
adb shell ip route
adb connect <pico-ip-address>:5555
```

After `adb connect` succeeds, unplug USB and select the wireless device:

```bash
ANDROID_SERIAL=<pico-ip-address>:5555 ./pico4-power-test.sh doctor
```

Only enable network ADB on a trusted network. To stop listening on TCP port
5555, reconnect USB and run `adb usb`.

### Verified Pico 4 telemetry

On the tested Pico 4 A8110 with Android 10, direct reads from
`/sys/class/power_supply/` are permission-restricted. The public Android battery
properties service nevertheless exposes momentary current in microamperes and
remaining charge in microampere-hours. `dumpsys battery` supplies voltage in
millivolts, battery level, temperature, and external-power state. The tool uses
this verified combination automatically and retains all source values in the
CSV.

The same firmware exposes VR brightness, reported panel brightness, automatic
brightness state, active refresh rate, CPU-cluster clocks, GPU clock, Android
thermal status, and CPU/GPU/skin temperatures. Pico's `pxrfanservice` does not
publish fan RPM, but it does publish `mFanState`, the control value used by its
fan service. The recorder stores this as `fan_state` and never labels it as RPM.

## Test controls

Keep all conditions other than the tested scenario fixed:

- Start near the same battery level, preferably between 40% and 80%.
- Disconnect external power before recording.
- Use the same display brightness and refresh rate.
- Keep Wi-Fi, tracking, audio, and controllers in the same state.
- Use the same domain, avatar, position, view direction, and visible content.
- Prevent downloads, updates, and unrelated background activity.
- Keep the headset at a similar ambient temperature.
- Do not wear the headset in one run and leave it stationary in another.

Run each scenario at least three times. A 5-minute warm-up followed by a
30-minute recording is the default and provides a useful minimum. Longer runs
are necessary when the firmware exposes only whole battery percentages.

## Record a baseline

Close Overte and leave the headset in a documented, reproducible idle state.
The baseline deliberately disables the Overte-process check:

```bash
./pico4-power-test.sh record --label idle --no-app-check
```

Describe the exact idle screen and headset state in the test notes. Android's
launcher is not equivalent to an application rendering an immersive scene, so
the difference is an operational comparison rather than isolated app power.

## Record Overte

Start Overte, enter the test location, keep the chosen scene active, and run:

```bash
./pico4-power-test.sh record --label overte-simple
```

For a short setup validation before committing to a full run:

```bash
./pico4-power-test.sh record \
    --label smoke-test \
    --warmup 0 \
    --duration 60
```

Results are written under `android/power-results/`, which Git ignores. Each CSV
contains timestamps, device/build identity, battery values, charge status,
screen state, display configuration, fan state, thermal data, CPU/GPU clocks,
and the Overte process ID. Raw values are retained so firmware behavior can be
audited later.

The analyzer reports ranges for brightness, refresh rate, and fan state. It
also reports maximum CPU/GPU/skin temperatures and median clocks. A warning is
printed if brightness, automatic-brightness state, or refresh rate changes
during a run, because that makes comparisons less controlled.

The recorder refuses to run while external power is detected. The
`--allow-charging` option exists for diagnostics, but charging runs should not
be compared with battery-powered runs.

## Analyze and compare runs

Every recording is summarized automatically. Existing files can be analyzed
together:

```bash
./pico4-power-test.sh analyze \
    power-results/20260802T120000Z-idle.csv \
    power-results/20260802T130000Z-overte-simple.csv
```

The recorder first tries Android's public BatteryManager properties, then
readable power-supply sysfs values, and finally `dumpsys battery`. When voltage
and current are available, the analyzer integrates their product over time. If
current is unavailable but a charge counter exists, it uses the charge-counter
change and median voltage. Otherwise it reports battery-level discharge only
and does not invent an absolute watt value.

The first input file is the comparison baseline. Use recordings with matching
duration and conditions, and compare repeated-run averages rather than a single
pair. Temperature should also be inspected: rising temperature or thermal
throttling can change power and performance during a run.

## Limitations

- `current_now` sign differs across Android devices; the analyzer uses its
  magnitude for discharge power.
- The displayed charge-counter check is an independent estimate. Large
  disagreement with current integration indicates that the run or telemetry
  needs investigation.
- `fan_state` is a Pico vendor control value. It is useful for relative fan
  behavior, but it cannot be converted to RPM without a documented calibration.
- Collecting the extended telemetry has a small measurement cost. The same
  sampling interval and tool version must be used for every compared scenario.
- USB ADB can leave a physical power connection. If the Pico reports charging,
  use wireless ADB or a USB data connection that does not supply power.
- An inline USB-C meter measures charger input and charging losses, not headset
  consumption directly.
- Battery percentage is quantized and unsuitable for short absolute-power
  measurements.
- A calibrated power analyzer connected at the battery is required for
  laboratory-grade absolute results and should only be used by someone
  qualified to work safely with lithium batteries.
