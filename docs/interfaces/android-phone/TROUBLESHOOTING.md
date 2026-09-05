# Troubleshoot the Android Phone port

Start with:

```bash
cd android/phone
./build.sh doctor
```

## Dependencies are missing or stale

Use the normal `setup --download` path. Do not rebuild the multi-hour 16-KiB
graph unless you are intentionally producing dependencies. Run the detailed
verifier locally when `doctor` reports a stale readiness marker.

## No compatible JDK is found

Set `JAVA_HOME` to JDK 17 through 21. Direct Gradle commands do not use the build
wrapper's JDK discovery.

## ADB cannot find or authorize the phone

Enable USB debugging, unlock the device, accept the RSA prompt, and inspect
`adb devices`. Set `ANDROID_SERIAL` when more than one target is present.

## The APK does not start

From `android/phone/`, run
`ANDROID_SERIAL=<serial> ./tests/phone-device-test.sh`. Do not capture or
commit global Logcat output; it can contain unrelated application, account, and
user data.
