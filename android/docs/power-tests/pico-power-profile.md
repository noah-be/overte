# Pico Overte power profile

The experimental Pico power profile bundles several Interface-side rendering
changes so their combined effect can be measured in a single battery run. It
does not change Pico OS settings, display refresh rate, or render resolution.

The profile applies:

- forward rendering;
- shadows, haze, bloom, and ambient occlusion disabled;
- local lights disabled while ambient and key light remain available;
- procedural material shaders disabled;
- temporal and fast approximate anti-aliasing disabled;
- recursive world-mirror views disabled; and
- the existing low-detail automatic LOD target.

Fixed foveated rendering is retained as a separate experiment and is disabled
by default. This keeps its result independent from the bundled profile.

## Test control

Set the profile before starting Overte:

```bash
adb shell setprop debug.overte.power_profile 1
adb shell setprop debug.overte.foveation off
```

Disable it for a baseline run and restart Overte:

```bash
adb shell setprop debug.overte.power_profile 0
```

The disabled state explicitly restores the known Pico baseline (forward
rendering, haze, local lights, and procedural materials enabled; antialiasing
disabled). This prevents settings persisted by a previous profile run from
contaminating the next A/B baseline.

The application log prints `PICO_POWER_PROFILE` with every applied component.
New power-test CSV files also store the `power_profile` and `foveation` values
in every row.
