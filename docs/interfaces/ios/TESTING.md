# Test Overte for iOS

## Host contracts

Linux and macOS can run:

```bash
./ios/tests/run-tests.sh
python3 -m py_compile ios/tools/*.py ios/tests/*.py ios/conanfile.py
bash -n ios/build-ios.sh ios/ci/*.sh ios/tests/run-tests.sh
```

`foreground-watchdog-test.py` exercises the production suspension gate with a
controlled clock and a concurrent resume/check interleaving. The watchdog remains
active for genuine foreground timeouts and independent graphics pause/resume
cannot override the background gate. This host check must be followed by real
short and greater-than-120-second background/foreground and lock/unlock trials.

`application-background-transition-test.py` executes the actual Qt state handler
with resource-operation spies. It covers Active -> Inactive -> Hidden/Suspended,
repeated notifications, temporary inactivity without background entry, startup
completion while hidden, and shutdown. Visibility and completed resource pause
are tracked independently so each stop has exactly one matching restart.

The Full Client bundle validator also rejects missing or portrait-enabled iPad
orientation declarations. On-device tests must launch while held upright, rotate
with the tablet and keyboard visible, and return from background: the client
must retain landscape geometry and usable controls.

These checks do not prove an Apple build or launch.

## Simulator

Ordinary pull requests use one iPhone simulator. Touch-relevant changes, pushes,
and manual bootstrap runs use one iPhone and one iPad; see
[Continuous integration](CI.md). For local release evidence, build and run the
bootstrap separately on both device families. Follow
[`docs/ios/XCODE_FIRST_RUN.md`](../../ios/XCODE_FIRST_RUN.md) and retain the
source revision, Xcode and SDK versions, bundle verification, crash report,
console excerpt, and screenshot when a gate fails.

## Physical devices

A simulator result cannot satisfy a device-only case. Run every case in
`ios/tests/device-acceptance.json` on at least one supported iPhone and one
supported iPad and validate the results with the checked-in schema. The complete
procedure is in
[Signing and physical-device tests](../../ios/SIGNING_AND_DEVICE_TESTS.md).

The shared touch UI has additional layout, safe-area, keyboard, text-scaling,
external-input, and accessibility cases in the
[iOS touch UI validation matrix](TOUCH_UI.md). Bootstrap smoke results do not
replace integrated-client or physical-device acceptance for those cases.
