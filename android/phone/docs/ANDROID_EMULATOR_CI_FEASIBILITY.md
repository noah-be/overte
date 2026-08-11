# Android emulator CI feasibility

This note records the device-free instrumentation investigation performed on
2026-08-09. It deliberately does not add an emulator job: the current product
artifact cannot run on the accelerated emulator architecture available to the
standard CI lane, and a test-only substitute would duplicate Robolectric while
skipping the boundary that instrumentation is meant to prove.

## Current artifact boundary

- `phoneInterface` applies `ndk { abiFilters 'arm64-v8a' }` and every packaged
  Qt plugin and native client library is named and built for ARM64.
- The measured debug APK is 231,345,137 bytes. It contains 106 ARM64 native
  entries totalling 354,921,152 uncompressed bytes and no `x86_64` ABI.
- The instrumentation APK is 1,891,657 bytes, but it is installed alongside
  and targets the 231 MB product APK; its small size does not remove the
  product ABI requirement.
- The verified Qt and non-Qt Conan trees used to create that APK occupy about
  2.4 GB each locally. They are build inputs, not present in a clean checkout.
- With all dependencies and outputs already present, an incremental
  `assembleDebug assembleDebugAndroidTest` still took 47.49 seconds
  (76 tasks, 72 up-to-date). This is a lower bound, not a clean-build result.

Standard `ubuntu-24.04` GitHub-hosted runners are x64. KVM acceleration is
available there, but it accelerates x86/x86_64 Android system images. Installing
the ARM64-only product APK on such an image fails ABI matching; software ARM
emulation would discard KVM's benefit and is not a bounded, reliable lane for
this large Qt application. GitHub also offers ARM64 hosted runner variants, but
using an ARM64 Android system image there still needs a proven image/KVM/tooling
combination and does not solve acquisition and verification of the 4.8 GB
native dependency graph.

## Why no launcher-only instrumentation application was added

It is technically possible to build a small x86_64-independent Android test
application that compiles the production `PermissionsActivity`, deep-link
classes and policies, then supplies a test stub named
`PhoneInterfaceActivity`. That application could exercise framework Intent,
permission and Activity APIs on a fast x86_64 emulator.

It would not execute the production manifest/package boundary or the real
`PhoneInterfaceActivity`: the latter extends Qt's `QtActivity`, preloads native
crypto/SSL libraries and starts the native client. Replacing it is precisely
the important boundary. The existing Robolectric harness already compiles the
same production launcher source with a bounded destination stub and covers API
26/35 lifecycle, saved state, permissions, intents and exactly-once launch.
A second stub application would therefore add SDK/emulator downloads and boot
flakiness without materially stronger product evidence.

## Realistic future lane

Add emulator CI only after one of these prerequisites is deliberately funded:

1. Build and verify a complete `x86_64` Phone Qt/Conan/native graph and publish
   it as a checksum-addressed CI artifact. Produce a multi-ABI or dedicated
   x86_64 debug APK from the normal production module, never a copied launcher.
2. Alternatively, qualify an ARM64 hosted runner with an ARM64 KVM system image
   and measure cold boot, install and test time over repeated scheduled runs.
3. Cache only immutable SDK/system-image and dependency artifacts keyed by
   their checksums; keep a cold-cache scheduled run to detect hidden inputs.
4. Run the existing `connectedDebugAndroidTest` suite first on API 26 and the
   current target API. Upload AndroidTest JUnit, logcat restricted to the app
   process and emulator diagnostics on every failure.
5. Require bounded emulator boot/test time, explicit shutdown and repeated-run
   flake evidence before making the lane a pull-request gate.

Until then, the current separation is honest: Robolectric and host tests cover
the hardware-free launcher logic, the instrumentation APK is compile-checked,
and the real ARM64 package remains a prepared emulator/device-lab concern.
