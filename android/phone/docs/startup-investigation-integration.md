# Phone startup investigation integration

The Phone startup investigation is integrated into `android-phone`. Reusable
prerequisites follow the parent ownership hierarchy; the investigation branch
is not a permanent synchronization target.

## Enabled improvements

Phone startup schedules compressed KTX processing and model parsing ahead of raw
texture encoding, loads shader sources lazily, and avoids unused tablet prewarm.
The integration also preserves rectangular ETC mip handling, resource-priority
locking, explicit startup-link selection, and cancellation of superseded
navigation. Platform guards keep Phone scheduling and startup choices scoped to
the Phone build.

Integration preserves the current shared authentication, consent-lifetime, and
device-test security checks. Incomplete Pico capture-policy hooks from the
investigation were removed because the current Java implementation does not
provide their required callbacks. Existing capture behavior is retained, while
raw microphone WAV capture remains disabled and JNI exception details remain
suppressed. The independent Phone voice-test buffer is retained.

## Optional experiments

Animation-curve shortcuts, KTX header-first probing, and collision-priority
experiments remain disabled by default. The measured ETC RGBA fast archive is an
optional, hash-bound build override; the canonical dependency recipe and lock
are unchanged. Diagnostic cache namespaces allow isolated trials without
discarding the normal cache.

The production download baseline remains two concurrent requests. Diagnostic
overrides do not establish a generally faster default.

## Evidence and validation

The committed evidence under `../tests/evidence/startup-20260914/` records the
historical measurements and their limits. See also
[the scheduling investigation](loading-priority-investigation.md). Earlier
texture handoff is not proof that the complete world finishes loading sooner;
the measurements do not establish a universal cold-start or warm-start gain.

Run the device-free startup regressions with:

```sh
python3 android/phone/tests/phone-startup-host-test.py
bash android/phone/tests/phone-static-regression-test.sh
```

The startup runner requires the native host tools documented by the individual
tests. Its optional `--etc-source` argument enables the rectangular-mip check
against the pinned codec sources. Host tests and native compilation do not
replace APK packaging or physical-device acceptance. The separate Phone startup
flash and earlier intermittent QML assertion still require their own evidence;
this integration does not declare either resolved.
