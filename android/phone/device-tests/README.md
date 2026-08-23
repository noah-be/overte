# Android Phone device adapter

This target adapter maps the universal harness operations to ADB for the
regular `org.overte.phone` client. Discovery accepts only authorized physical
ARM64 touchscreen phones with Android API 26+, OpenGL ES 3.0+, and rejects
emulators, watches, TVs, automotive, VR, Pico, and ByteDance targets.

Run the portable smoke suite against the only connected eligible phone:

```bash
python3 tests/device/run.py \
  --adapter-manifest android/phone/device-tests/adapter.json \
  --catalog tests/device/catalog.json \
  --suite smoke
```

Stability duration and cycle controls are shared across platforms:

```bash
OVERTE_DEVICE_LIFECYCLE_CYCLES=20 \
OVERTE_DEVICE_IDLE_SECONDS=1800 \
python3 tests/device/run.py \
  --adapter-manifest android/phone/device-tests/adapter.json \
  --catalog tests/device/catalog.json \
  --suite stability --output-dir /tmp/overte-phone-stability
```

The Phone APK must already be installed. Installation and APK provenance remain
an explicit preparation gate rather than a hidden side effect of every module.
