# Shared Appium adapter

This directory provides one device-free Appium W3C transport for Android and
iOS. It uses only the Python standard library plus the checked-in device
contracts. The two manifests select a platform while sharing `adapter.py`.

The adapter supports common session creation, application installation and
launch, foreground observation, screenshots, touch gestures, and semantic
tablet controls. Capabilities are advertised only when the corresponding
control is configured. The semantic result contains only identifiers from
`tablet-ui-contract.json`; raw page source and arbitrary accessibility text are
never returned or persisted.

## Configuration

Copy `targets.example.json` outside the repository, make it account-private,
and set:

```bash
cp tests/device/adapters/appium/targets.example.json /absolute/private/targets.json
chmod 600 /absolute/private/targets.json
export OVERTE_APPIUM_TARGETS=/absolute/private/targets.json
```

The adapter rejects configurations inside the repository, symbolic links,
non-regular files, files owned by another account, and any group or other
permission bits. Plain HTTP Appium endpoints are accepted only on loopback;
remote endpoints must use HTTPS.

The checked-in examples are intentionally disabled, contain no device
selector, and are not evidence that any target is usable. Enable only a target
whose generic simulator/emulator capabilities and control identifiers have
been audited locally.

Physical targets fail closed in this shared layer. Their independent identity,
artifact, signing, process, and probe checks belong to later platform-specific
integrations and are not emulated here. Platform-only configuration fields are
rejected rather than accepted without their required checks.

## Semantic tablet contract

After auditing that Appium exposes the checked-in semantic IDs, opt in with:

```json
"semanticUi": {"contractVersion": 1}
```

Android accepts contract IDs from `resource-id` or `content-desc`. iOS accepts
the versioned `OverteTabletScreen.`, `OverteTabletControl.`, and
`OverteTabletReady.` prefixes. The ready suffix repeats the visible screen ID.
A snapshot must expose exactly one known screen.
Activation requires a currently visible, enabled element and uses its W3C
element identity.

Run the device-free checks from the repository root:

```bash
python3 -m unittest \
  tests.device.self_tests.test_appium_adapter \
  tests.device.self_tests.test_e2e_stack \
  tests.device.self_tests.test_portable_smoke_contract
python3 tests/device/verify_adapter.py --help
```
