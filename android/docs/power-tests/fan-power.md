# Pico 4 fan power test results

Test date: 2026-08-02

Device: Pico 4 A8110 running Android 10

These results estimate how fixed fan duty affects total headset power in a
controlled idle state. They do not represent Overte's application power. Overte
was stopped so its variable rendering load would not hide the fan's effect.

## Method

- Wireless ADB; USB and external power disconnected
- Pico Home active and headset stationary
- VR brightness 86/255; automatic brightness disabled
- 72 Hz display mode
- CPU median clocks approximately 1805/1766/2074 MHz
- GPU median clock 442 MHz
- Three runs per fan setting
- 15-second fan stabilization before each 60-second recording
- Automatic fan control restored and verified after every run
- Power integrated once per second from Android voltage and current telemetry
- Charge-counter delta used as an independent cross-check

The valid run files were kept locally under the ignored
`android/power-results/` directory. Interrupted setup runs and smoke tests were
excluded.

## Results

| Fan duty | Median RPM, mean | Power runs | Mean power | Sample SD | Charge-counter mean |
| ---: | ---: | --- | ---: | ---: | ---: |
| 25% | 4,298 | 5.498, 5.641, 5.118 W | 5.419 W | 0.271 W | 5.468 W |
| 50% | 8,003 | 5.612, 5.831, 5.900 W | 5.781 W | 0.150 W | 5.805 W |
| 100% | 14,056 | 7.000, 7.043, 6.639 W | 6.894 W | 0.222 W | 7.006 W |

| Comparison | Total-headset power difference |
| --- | ---: |
| 50% versus 25% | +0.362 W (+6.7%) |
| 100% versus 50% | +1.113 W (+19.2%) |
| 100% versus 25% | +1.474 W (+27.2%) |

A simple linear fit across the nine runs gives approximately 0.020 W per duty
percentage point with R² = 0.916. The relationship should not be assumed to
remain linear outside these three measured settings.

Higher fan duty reduced component temperatures. Mean run-maximum CPU/GPU
temperatures were 60.4/55.4 C at 25%, 58.6/54.8 C at 50%, and 56.1/50.9 C at
100%.

## Interpretation and limitations

In this idle configuration, raising the fan from 25% to 100% increased total
headset power by about 1.47 W. This is the system-level effect, not necessarily
the fan motor's electrical input alone: stronger cooling can also alter SoC
leakage, temperature-dependent control behavior, and background activity.

The one-minute recordings are substantially better than single instantaneous
readings, and the independent charge-counter results agree closely with the
integrated values. However, they remain short engineering tests. Longer runs,
more repetitions, and randomized ordering would be needed for a precise fan
power curve. An equivalent series with a fixed Overte scene would answer the
separate question of how fan duty affects power and throttling under sustained
application load.
