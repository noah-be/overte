# Pico 4 Overte Hub baseline

Test date: 2026-08-02

Device: Pico 4 A8110 running Android 10

This baseline uses the first seven minutes from each of the first two test
recordings. The common 420-second window ends before run 2 changed to Pico
Seethrough at approximately 7 minutes 14 seconds.

The third recording is excluded completely.

## Scenario and method

- Overte package: `org.overte.pico`
- Scene: `hifi://overte_hub/155.084,-98.5,-397.328`
- Avatar stationary at the established Hub test spawn
- Headset stationary but kept in the worn and awake XR state
- Wireless ADB
- MCU display brightness fixed at 100%
- Fan fixed at 100% duty
- Automatic brightness disabled
- Display refresh rate fixed at 72 Hz
- Scene loading and active Overte rendering verified before each recording
- 180-second controlled warm-up after applying brightness and fan settings
- First 420 seconds of each recording used for the baseline
- Power integrated from Android voltage and current telemetry
- Charge-counter delta used as an independent cross-check

Although a cable may have remained physically connected during one test, every
sample in both selected windows reported `plugged=0`. The battery charge counter
also decreased throughout both windows. The headset was therefore not receiving
measurable charging power during either selected baseline window.

## Results

| Metric | Run 1, first 420 s | Run 2, first 420 s |
| --- | ---: | ---: |
| Samples | 398 | 412 |
| Integrated mean power | 13.434 W | 13.206 W |
| Charge-counter cross-check | 13.524 W | 13.263 W |
| Measured energy | 1.5673 Wh | 1.5407 Wh |
| Battery gauge | 78% to 58% | 77% to 58% |
| Median voltage | 3.509 V | 3.500 V |
| Median discharge current | 3.825 A | 3.840 A |
| Battery temperature | 32.5 to 36.5 C | 33.2 to 37.0 C |
| Maximum CPU/GPU/skin temperature | 90.4/72.5/61.0 C | 90.3/72.1/60.7 C |
| Median fan RPM | 14,127 | 14,123 |
| External-power samples | 0 | 0 |

## Baseline

| Summary | Result |
| --- | ---: |
| Mean of the two run means | **13.320 W** |
| Sample SD of the run means | 0.161 W |
| Run-to-run difference | 0.228 W (1.70%) |
| Mean charge-counter cross-check | 13.394 W |

The two independent power methods agree closely, and the two selected runs
differ by less than 2%. For subsequent tests using the same Hub scene, 100%
display brightness, 100% fan duty, and the same 420-second analysis window,
**13.320 W** is the working total-headset baseline.

## Validity and limitations

- Only the first 420 seconds of each source recording belong to this baseline.
- Run 2 after 420 seconds is excluded. Pico Seethrough took XR focus at
  approximately 434 seconds after a tracking-service restart.
- Run 3 is excluded in full.
- Both selected windows remained above the 21% battery threshold.
- The result measures the complete headset, not Overte in isolation.
- Two runs are sufficient for a working engineering baseline but not a
  laboratory-grade statistical estimate.

Future Overte recordings use an XR-focus watchdog that aborts if Seethrough,
Boundary, or another application takes focus. The recorder also aborts below
21% battery.

The source CSV files remain local under `android/power-results/` and are
excluded from Git.
