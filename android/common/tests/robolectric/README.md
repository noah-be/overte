# Shared Android JVM host harness

Run `android/common/tests/robolectric/run-tests.sh` with Java 21. The harness
compiles the real available Phone Activity and hosts, shared Web/Snapshot/
Documents Java, and the existing launcher dependencies. Its AndroidX WebKit
1.12.1 and Core 1.1.0 AAR API inputs match the application and are pinned in
`gradle.lockfile`; their actual `classes.jar` files are extracted for javac.

Only the Qt Activity/lifecycle boundary is replaced. There is no native Qt
owner, and asking it to publish native lifecycle state fails explicitly. Web,
snapshot and document implementations are compiled from production sources.
Robolectric launcher coverage is not a native WebView, provider, media, or
physical-device qualification.

To qualify this parent-owned harness against a separate downstream checkout
without copying its implementation into the parent, invoke the same Gradle
entry point with `-PoverteProductSourceRoot=/absolute/path/to/checkout`:

```sh
android/common/gradlew --no-daemon \
  -c android/common/tests/robolectric/settings.gradle \
  -b android/common/tests/robolectric/build.gradle \
  -PoverteProductSourceRoot=/absolute/path/to/checkout test
```

That override selects the real Phone source and test directories and their
production Qt utility, security, and embedded feature dependencies. The shared
harness and its locked JVM API configuration remain the owning parent's files.
No product-specific source is promoted through this test override.
