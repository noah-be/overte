# Legacy Gradle dependency report

This harness reports Gradle's dependency graph for the committed legacy Android
source snapshot. It is not an APK build, SBOM or artifact checksum audit. The
obsolete GVR inputs have been removed from the legacy graph.

It requires the explicit JDK 8 installation at
`/usr/lib/jvm/java-8-temurin-jdk` by default. Override it only with
`OVERTE_LEGACY_JAVA_HOME`. Gradle 6.5 is downloaded from the official Gradle
distribution service and checked against the reviewed SHA-256 literal before
installation.

After bootstrapping the toolchain once with the explicit network mode, use the
dedicated wrapper for legacy Gradle commands:

```bash
python3 android/common/tests/legacy-gradle/run_dependency_report.py toolchain --network
../legacy/gradlew tasks
```

The wrapper always verifies the cached Gradle 6.5 distribution offline
before use. It never invokes the shared Gradle 8.13 Phone/Pico wrapper and never
downloads implicitly.

A resolve additionally requires an Android SDK through `ANDROID_HOME` or
`ANDROID_SDK_ROOT`, plus a legacy-compatible NDK directory. The harness uses
`$ANDROID_HOME/ndk-bundle` by default; set `OVERTE_LEGACY_NDK_HOME` for a
side-by-side NDK. It writes the resulting `sdk.dir` and `ndk.dir` only to the
disposable source snapshot, never to the checkout.

The four explicit modes are:

```bash
python3 android/common/tests/legacy-gradle/run_dependency_report.py toolchain --offline
python3 android/common/tests/legacy-gradle/run_dependency_report.py toolchain --network
python3 android/common/tests/legacy-gradle/run_dependency_report.py resolve --offline
python3 android/common/tests/legacy-gradle/run_dependency_report.py resolve --network
```

The isolated report uses fixed development metadata (`VERSION_CODE=1` and
`RELEASE_NUMBER=1.0`) only to configure the legacy application projects. These
values are not release evidence and the harness does not build an APK.

`result.json` distinguishes a successful Gradle command from a fully resolved
graph with `gradleCommandSucceeded` and `resolutionSucceeded`. Dependency-tree
entries that Gradle marks `FAILED` are listed in `unresolvedDependencies` with
their module and configuration. A failed or incomplete graph never receives a
`.complete` marker.

`toolchain` never resolves project dependencies. `--offline` never downloads
the distribution and passes Gradle's offline flag during a report. `--network`
is the only mode that permits network access.

Reports default to `build/reports/legacy-gradle-dependencies/current`. Gradle
runs in a disposable `git archive` snapshot with isolated home, project cache,
temporary directory, and `GRADLE_USER_HOME`; it never runs in the checkout.
Publication is locked and transactional. `.complete` exists only after a
successful Gradle exit whose output contains no unresolved-dependency marker.
Absolute staging, cache, source, and Java paths are redacted.

The report covers `qt`, `oculus`, `interface`, `questInterface`, `framePlayer`,
and `questFramePlayer`. `picoInterface` is explicitly excluded because it owns
a dedicated Gradle 8.13 graph. A successful report proves only that Gradle
produced the requested dependency graph metadata. It does not verify every
artifact's bytes, build an APK, or produce a resolved SBOM.
