# Test Overte for iOS

## Host contracts

Linux and macOS can run:

```bash
./ios/tests/run-tests.sh
python3 -m py_compile ios/tools/*.py ios/tests/*.py ios/conanfile.py
bash -n ios/build-ios.sh ios/ci/*.sh ios/tests/run-tests.sh
```

These checks do not prove an Apple build or launch.

## Simulator

Build and run the bootstrap separately on an iPhone and iPad simulator. Follow
[`docs/ios/XCODE_FIRST_RUN.md`](../../ios/XCODE_FIRST_RUN.md) and retain the
source revision, Xcode and SDK versions, bundle verification, crash report,
console excerpt, and screenshot when a gate fails.

## Physical devices

A simulator result cannot satisfy a device-only case. Run every case in
`ios/tests/device-acceptance.json` on at least one supported iPhone and one
supported iPad and validate the results with the checked-in schema. The complete
procedure is in
[Signing and physical-device tests](../../ios/SIGNING_AND_DEVICE_TESTS.md).
