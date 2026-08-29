# Pico universal device adapter

This adapter reuses the shared Android ADB transport and adds Pico identity,
XR-focus, Guardian/seethrough, and world-status operations. It intentionally
does not advertise phone-style background lifecycle support.

## Semantic tablet acceptance

The complete Tablet-E2E contract uses the product Pico profile in
`tests/device/adapters/android/pico.json`, not the legacy smoke-only manifest
in this directory. Its checked-in product policy is
`pico4-tablet-policy.json`.

Run hardware-free contract checks first:

```bash
python3 -m unittest tests.device.self_tests.test_tablet_e2e -v
python3 android/vr/pico/tests/pico-tablet-e2e-adapter-test.py
```

A physical run requires the E2E Debug APK, the qualified explicit OpenXR
layer, one Pico on the private isolated ADB server, and the private runtime
state directory documented in
`tests/device/openxr_input/PICO4_CONTROLLER_AUTOMATION.md`. With those gates
provided by the private lab environment, run:

```bash
python3 tests/device/run.py \
  --adapter-manifest tests/device/adapters/android/pico.json \
  --catalog tests/device/catalog.json --suite tablet-e2e \
  --tablet-policy android/vr/pico/device-tests/pico4-tablet-policy.json \
  --require-complete --output-dir /tmp/overte-pico-tablet-e2e
```

Do not put the private target selector, ADB server port, device serial, or
runtime directory in this command or in persisted reports. The lab wrapper
supplies them through its protected environment and device lock. A pass
requires the complete open → Home ready → visible Settings pointer activation
→ Settings ready → General/HMD and Graphics/render-resolution policy checks →
Home → close sequence in one process. The probe snapshots before and after the
tablet-focused sequence must also prove stable avatar position, velocity and
view orientation.
