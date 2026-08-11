# Android source layout

Android code is grouped by ownership rather than by build-system artifact type:

```text
android/
├── common/             shared Gradle, Conan, CMake, Qt, legacy, docs and tests
├── phone/              Android phone applications, build entry points, CI and tests
└── vr/
    ├── common/         code shared by multiple Android VR targets
    ├── pico/           Pico application, build entry points, CI, docs and tests
    └── quest/          Quest applications, Oculus integration, docs and tests
```

`common` is limited to infrastructure or implementation used by more than one
Android target. Target-specific code must stay with its target even when it is
invoked by shared tooling.

## Entry points

- Phone: `android/phone/build.sh`
- Pico: `android/vr/pico/build.sh`
- Legacy Phone and Quest Gradle graph: `android/common/legacy/gradlew`
- Shared test suite: `android/common/tests/run-tests.sh`

The repository-level `interface/`, `libraries/` and `scripts/` directories remain
cross-platform Overte code. They are intentionally outside this Android layout.
