# iOS/iPadOS semantic tablet E2E

This is the product runbook for Tablet E2E Contract v1. iPhone and iPad share
the checked-in `ios.flat-touch` policy. Geometry and safe-area behavior may
differ, but neither form factor exposes HMD preferences, controller settings,
or VR render-resolution controls.

## Product mapping

| Contract ID | Observed iOS product control |
| --- | --- |
| `app.settings` | Settings `TabletButton` created by `settings.js` |
| `settings.general` | visible General row in `Settings.qml` |
| `settings.graphics` | visible Graphics row in `Settings.qml` |
| `settings.audio` | visible Audio row in `Settings.qml` |
| `settings.security` | visible Security row in `Settings.qml` |
| `settings.controllers` | Controls row, absent under the iOS touch profile |
| `settings.hmd-preferences` | HMD preference section, absent under the iOS touch profile |
| `settings.vr-render-resolution` | legacy product render-scale control projected to the common ID and absent on iOS |
| `nav.back` | visible Settings header or iOS screen-space Back control |
| `nav.home` | visible iOS screen-space Home control |
| `nav.close` | visible tablet or iOS screen-space Close control |

The native E2E bridge uses `OverteTabletScreen.`, `OverteTabletReady.`, and
`OverteTabletControl.` only inside `OVERTE_IOS_E2E_TEST_BUILD`. Each native
control is placed over the corresponding visible QML frame. Its activation
invokes the control's production `activate()` handler or its QML Accessible
press action, the same path used by direct touch and assistive input. The
bridge receives no product policy and cannot route directly to a screen.
Ordinary Release builds contain none of these native semantic markers.

## Hardware-free validation

Run from the repository root:

```bash
python3 -m unittest tests.device.self_tests.test_appium_adapter -v
python3 ios/tests/e2e-accessibility-identifiers-test.py
python3 ios/tests/e2e-test-build-contract-test.py
tests/device/qml/run-qml-tests.sh
target_config="$(mktemp)"
trap 'rm -f -- "$target_config"' EXIT
printf '%s\n' '{"schemaVersion":1,"targets":[]}' > "$target_config"
chmod 0600 "$target_config"
OVERTE_APPIUM_TARGETS="$target_config" \
python3 tests/device/verify_adapter.py \
  --adapter-manifest tests/device/adapters/appium/ios.json
```

The verifier with this ephemeral empty private configuration proves only the
manifest/protocol surface. It is not physical acceptance.

## Physical acceptance

Use only the private receipt-bound target configuration and immutable Appium,
RemoteXPC, WDA, DDI, and signing flow documented in `tests/device/ios/README.md`.
Keep shell tracing disabled and never put a selector, UDID, bundle/team value,
or credential in a command line or archived result.

The strict suite is:

```bash
python3 tests/device/run.py \
  --adapter-manifest tests/device/adapters/appium/ios.json \
  --catalog tests/device/catalog.json \
  --suite tablet-e2e \
  --tablet-policy tests/device/adapters/appium/ios-flat-touch-policy.json \
  --target "$OVERTE_DEVICE_TARGET_SELECTOR" \
  --output-dir /absolute/private/result-directory \
  --require-complete
```

The local Jenkins pipeline supplies the selector as a Secret Text credential,
prewarms the protected XCUITest session, and runs this suite under the same
exclusive device lock as `e2e-core`. A pass proves one process performed:
closed → Tablet Home ready → Settings → every policy screen → Back → Home →
closed. Record iPhone and iPad independently; never infer one form factor from
the other. Screenshots and raw page sources remain private diagnostics and are
not pass evidence.
