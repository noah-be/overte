# Pico 4 display-brightness power test results

Test date: 2026-08-02

Device: Pico 4 A8110 running Android 10

These results estimate how the Pico display brightness affects total headset
power in a controlled idle state. They do not represent Overte's application
power. Overte was stopped so its variable rendering load would not obscure the
display's effect.

## Method

- Wireless ADB; USB and external power disconnected
- Pico Home active and headset stationary
- MCU display brightness fixed at 0%, 50%, or 100%
- Fan fixed at 50% duty (approximately 7,900-8,000 RPM)
- Automatic brightness disabled and display refresh rate fixed at 72 Hz
- CPU median clocks approximately 1805/1766/2074 MHz
- GPU median clock 442 MHz
- Three runs per brightness setting, using a rotated setting order
- 15-second stabilization before each 60-second recording
- Original 30% MCU brightness and automatic fan control restored and verified
  after every run
- Power integrated once per second from Android voltage and current telemetry
- Charge-counter delta used as an independent cross-check

The valid run files were kept locally under the ignored
`android/power-results/` directory. Setup and smoke-test recordings were
excluded.

## Results

| MCU brightness | Power runs | Mean power | Sample SD | Charge-counter mean |
| ---: | --- | ---: | ---: | ---: |
| 0% | 4.844, 4.698, 4.712 W | 4.751 W | 0.081 W | 4.714 W |
| 50% | 6.072, 6.061, 6.049 W | 6.061 W | 0.012 W | 6.054 W |
| 100% | 7.155, 7.204, 7.104 W | 7.154 W | 0.050 W | 7.207 W |

| Comparison | Total-headset power difference |
| --- | ---: |
| 50% versus 0% | +1.309 W (+27.6%) |
| 100% versus 50% | +1.094 W (+18.0%) |
| 100% versus 0% | +2.403 W (+50.6%) |

## Interpretation and limitations

In this idle configuration, raising the MCU display brightness from its minimum
to maximum increased total headset power by about 2.40 W. The measured effect
is large and repeatable, so display brightness is an important control variable
for future Pico power comparisons.

The 0% MCU setting did not turn the display pipeline off: the headset continued
to report an active 72 Hz display mode and a panel level of 10/255. It therefore
represents the lowest accepted MCU backlight setting, not a powered-off display.

These are short engineering tests using Pico Home, not a measurement of Overte
itself. Longer recordings and an equivalent series with a fixed Overte scene
would be needed to quantify brightness impact under sustained application load.
