# iOS semantic tablet contract

The shared Appium adapter can reduce an iOS accessibility tree to Tablet
Contract v1 without retaining arbitrary labels or page source. This document
covers only that device-free contract boundary.

The accepted native marker forms are:

- `OverteTabletScreen.<screen-id>` for the one visible screen;
- `OverteTabletControl.<control-id>` for visible controls;
- `OverteTabletReady.<screen-id>` when that visible screen is ready.

Every suffix must occur in `tests/device/tablet-ui-contract.json`. Unknown text
is ignored, two simultaneous known screens are rejected, and activation
requires a visible enabled element. Product expectations remain separate in
`ios-flat-touch-policy.json`; the adapter does not inject that policy into the
application.

The checked-in target is disabled. This shared package does not provide
device identity, signing, artifact, process, or probe verification and does
not claim that a real device is ready. Those concerns must be supplied by an
independently reviewed platform package before a physical target can start a
session. Private target configuration must live outside the repository, be a
regular non-symlink file owned by the current account, and have mode `0600`.

Run the current contract checks from the repository root:

```bash
python3 -m unittest tests.device.self_tests.test_appium_adapter
python3 tests/device/verify_adapter.py --help
```

These commands exercise schema and parser behavior only; they do not contact
an Appium server or a device.
