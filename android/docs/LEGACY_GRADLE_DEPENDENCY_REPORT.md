# Legacy Gradle dependency report

This harness reports Gradle's dependency graph for the committed legacy Android
source snapshot. It is not an APK build, SBOM, artifact checksum audit, or proof
that the Maven GVR 1.80.0 and native GVR 1.101.0 inputs are compatible.

It requires the explicit JDK 8 installation at
`/usr/lib/jvm/java-8-temurin-jdk` by default. Override it only with
`OVERTE_LEGACY_JAVA_HOME`. Gradle 4.10.1 is downloaded from the official Gradle
distribution service and checked against the reviewed SHA-256 literal before
installation.

A resolve additionally requires an Android SDK through `ANDROID_HOME` or
`ANDROID_SDK_ROOT`, plus a legacy-compatible NDK directory. The harness uses
`$ANDROID_HOME/ndk-bundle` by default; set `OVERTE_LEGACY_NDK_HOME` for a
side-by-side NDK. It writes the resulting `sdk.dir` and `ndk.dir` only to the
disposable source snapshot, never to the checkout.

The four explicit modes are:

```bash
python3 tests/legacy-gradle/run_dependency_report.py toolchain --offline
python3 tests/legacy-gradle/run_dependency_report.py toolchain --network
python3 tests/legacy-gradle/run_dependency_report.py resolve --offline
python3 tests/legacy-gradle/run_dependency_report.py resolve --network
```

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
