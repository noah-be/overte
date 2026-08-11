# Meta Quest preview build

This is an early, hardware-unverified Meta Quest port. It packages Overte's
maintained Android ARM64 client and generic OpenXR plugin with Quest discovery
metadata. It does not use the broken, historical Quest 1/Oculus Mobile graph.

No headset is required to produce the debug APK:

```bash
cd android
./build-quest.sh doctor
./build-quest.sh all --stacktrace
```

After dependencies have been prepared, rebuild with:

```bash
./build-quest.sh build
```

Every build verifies the APK fail-closed: ZIP integrity, ARM64-only native
libraries, required OpenXR libraries, package ID, SDK levels, Quest manifest
metadata, four-byte ZIP alignment, and the APK signature. It also writes a
deterministic size report. Reports are stored below
`apps/picoInterface/build/reports/quest/`.

The default APK budget is 550 MiB. Override it deliberately when investigating
a known size change, for example `QUEST_APK_BUDGET_MIB=560 ./build-quest.sh
build`; do not raise the checked-in default merely to hide unexplained growth.

The output is
`apps/picoInterface/build/outputs/apk/debug/overte-quest-preview-debug.apk`.
It uses package ID `org.overte.quest.preview`, contains only ARM64 native
libraries, and is debug-signed by Android's normal development key.

## Known boundary

The APK is a build artifact, not yet a validated Quest release. Before calling
the port functional, test OpenXR session startup, Quest controller bindings,
tracking/recenter behavior, suspend/resume, microphone and spatial audio,
rendering in both eyes, thermal behavior, and clean shutdown on real hardware.

The Java and native target names still contain `Pico` because this first step
shares the maintained generic Android/OpenXR implementation. Separating neutral
Android XR names is follow-up refactoring and should not precede device proof.

## Current size baseline

The first debug APK is about 522 MiB. Its dominant compressed entries are
`libshaders.so` (about 166 MiB), `resources.rcc` (about 108 MiB), and
`libnode.so` (about 51 MiB). These three account for roughly 62% of the APK.
Consequently, removing small Qt modules without proving runtime reachability is
high risk and low reward. The useful follow-up investigations are shader
variant reduction, splitting optional/serverless resources, and whether the
full embedded Node runtime is required on standalone XR. Each needs runtime
coverage before it becomes a packaging change.

See [QUEST_HARDWARE_TEST_PLAN.md](QUEST_HARDWARE_TEST_PLAN.md) before the first
device session.
