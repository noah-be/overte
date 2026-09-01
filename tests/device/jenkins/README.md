# Fedora iOS Jenkins device lab

This local Jenkins pipeline reserves one physical iOS/iPadOS device and uses
one of three explicit handoffs: observed Personal Team installations (the
primary path), retained and verified Personal Team signed IPAs, or an optional
protected-producer run. It
serves the repository fixture on a fixed device-reachable LAN origin, and runs
the shared `e2e-core` and iOS `tablet-e2e` suites with `--require-complete`.
The tablet suite always uses the checked-in `ios.flat-touch` product policy.
It never publishes a
UDID, platform version, target selector, receipt, target configuration, IPA,
provisioning profile, raw accessibility tree, or Appium server log.

## Pinned user-side bootstrap

Use Java 21. The bootstrap rejects another Java major and installs Jenkins LTS
2.568.2 plus the exact plugin lock. Its Appium staging tree comes only from
`../ios/package-lock.json` via `npm ci --ignore-scripts`; it is not a runtime
dependency after root provisioning.

```sh
python3 tests/device/validate_toolchain_lock.py
python3 tests/device/jenkins/local_lab.py install \
  --install-root /absolute/private/overte-ios-lab/software \
  --config-root /absolute/private/overte-ios-lab/config \
  --java /absolute/path/to/java-21/bin/java
```

Review and run the one root provisioning command exactly once (substitute only
the absolute staging path printed by the previous command):

```sh
sudo python3 tests/device/ios/remotexpc_tunnel.py install-unit \
  --appium-home /absolute/private/overte-ios-lab/software/appium
```

That command installs the versioned, root-owned, non-writable RemoteXPC and
Appium runtime. The user service invokes only its attest-and-exec wrapper; it
never executes `software/appium/node_modules/.bin/appium`. The bootstrap also
creates `<config-root>/appium-state` outside the checkout with mode 0700. The
generated unit passes it as the mandatory `--state-root`, grants write access
only to that path, and the wrapper creates/removes a private temporary
`APPIUM_HOME` for each server process.

```sh
python3 tests/device/ios/remotexpc_tunnel.py status
python3 tests/device/jenkins/local_lab.py install-systemd-user-services \
  --config-root /absolute/private/overte-ios-lab/config
python3 tests/device/jenkins/local_lab.py status \
  --config-root /absolute/private/overte-ios-lab/config
```

## Private Jenkins configuration

Configure a Secret Text credential for the private target selector. Keep the
private Appium target JSON outside every checkout at mode 0600. Its disabled
template is `../adapters/appium/targets.example.json`; enable it only after the
signed receipt updates `appId`, `bundleId`, IPA paths and WDA bundle ID.

Set `IOS_DDI_ROOT` to the absolute external mode-0700 directory containing the
exact lock-pinned `Image.dmg`, `BuildManifest.plist`, and
`Image.dmg.trustcache`, each mode 0600. This Apple payload is operator-supplied:
the repository neither publishes nor automatically downloads it. While holding
the same exclusive device lock used by the suite, Jenkins verifies every byte,
mounts it when necessary, binds the mounted image signature directly to the
pinned SHA-384, and requires both XCTest services before starting Appium.

`IOS_ARTIFACT_SOURCE=personal-team-preinstalled` is the default. See
`docs/ios/PERSONAL_TEAM_E2E.md` on the `apple-ios` branch for instructions to
install Overte and WDA manually with Sideloadly, then supply the private,
short-lived `IOS_PREINSTALLED_ATTESTATION`. Jenkins performs no signing or
installation. Under the exclusive device lock, Fedora's immutable helper
observes either both fixed IDs or one explicitly accepted, uniquely
marker-selected Sideloadly-remapped pair. It verifies the Overte test markers,
WDA 16.8.0/XCUITest 12.8.0 markers, valid profiles, application identifiers and
a common signer/team before it writes the weak
`none-device-observed` receipt. That receipt deliberately has no IPA byte hash
or derivation claim, and this mode rejects `appium:prebuiltWDAPath`.

Choose `local-personal-team` only when the two exact signed IPA files were
retained. Supply the unsigned kit, signed handoff, Overte IPA, and WDA IPA as
absolute, current-user-owned mode-0600 files outside the checkout. The
open-source Fedora verifier prepares a cryptographically bound per-build copy
and receipt plus the extracted receipt-bound WDA Runner application before the
device lock. When the baseline takes the lock, the immutable device helper
replaces both installed applications from the receipt-bound IPAs before its
pre-session attestation. Jenkins still receives no Apple account, certificate,
profile, or Sideloadly credential.

For `protected-github`, additionally configure the GitHub Actions Secret Text
credential and age Secret File credential. An existing handoff requires both
the exact run ID and exact run attempt. Otherwise all audited dispatch inputs
are required; the pipeline never selects a merely "latest" run.

The Lockable Resources entry is a non-secret alias such as `ios-device-01`,
never a serial or UDID. `FIXTURE_PUBLIC_HOST` is a stable LAN DNS name or IPv4
address reachable from that one device. The pipeline always runs core; soaks
remain opt-in and start only after the baseline succeeds. The locked core stage
has a 45-minute outer timeout so the complete shared behavior suite and Appium
cleanup fit without weakening any module-level timeout.

The traceable stages are:

1. device-free contracts and toolchain validation;
2. root-runtime status plus the selected strong artifact handoff, if any;
3. for the primary path, installed-app observation and weak receipt creation
   under the device lock;
4. two stable privacy-safe thermal-headroom samples, the pinned Personalized
    DDI/XCTest gate, then the required `e2e-core` baseline under one
    uninterrupted locked Appium session;
5. required semantic `tablet-e2e` policy sequence in a fresh locked session;
6. optional accessibility audit after the baseline;
7. opt-in soaks;
8. target/session cleanup while still locked, private IPA/config deletion, and
   selector-scanned JUnit/diagnostic publication.

Per-build IPA copies/decoded IPAs, receipts, and the job-private target copy
stay outside the workspace and are deleted in `post { always { ... } }`,
including timeout/abort paths. Manually managed source files are never deleted.
Screenshots are off by default. Even when an operator explicitly enables a
failure screenshot, the raw image remains only in the private build tree and
is deleted after allowlisted staging; it is never published. Raw accessibility
XML and Appium logs are likewise never archived. Only the redacted allowlisted
results use Jenkins' seven-day/five-build artifact retention.

## Hardware gates

Do not install or launch until all gates are green:

- a trusted physical iOS/iPadOS 18+ device with Developer Mode enabled;
- host trust/pairing and an active, privacy-safe RemoteXPC status;
- the exact private lock-pinned Personalized DDI mounted with both XCTest
  services reachable;
- an unexpired receipt that either cryptographically binds both retained IPAs
  to exact provenance or honestly records only the locked installed-app
  observation without claiming byte provenance;
- device inclusion in both provisioning profiles and a launchable prebuilt WDA;
- exclusive Jenkins resource ownership for the target;
- two consecutive battery-temperature samples at or below the fixed 30.5 C
  preflight ceiling; raw diagnostics and the private device identity stay out
  of Jenkins output;
- a real accessibility audit proving `OverteTabletOpen` and
  `OverteTabletClose` appear as actionable nodes. Coordinate fallbacks are
  forbidden.

No hardware result is implied by the device-free tests in this directory.

## Android Phone target isolation

The canonical `android-device-e2e` job uses the same fixed profile and device
locks as each suite. Before its first session it copies only the selected,
enabled physical Android Phone entry from the long-lived private Appium file
into the build's private result root. Every Android suite and final cleanup use
that immutable copy; the copy and its marker are removed in `post` while the
selector-free staged evidence remains available. This prevents concurrent lab
provisioning from producing a mixed target contract and also prevents a Phone
job from selecting the Pico target.

For a hardware-acceptance run, enable `BUILD_INSTALL_ANDROID_E2E`. The job
builds the clean checked-out revision through `android_build_workspace.py` in
the Phone-specific isolated checkout and Conan home, records the APK SHA-256
and source revision in a private manifest, and calls the Appium adapter's
`app.install` only after both values are revalidated. Enable
`RUN_ANDROID_VISUAL_PREFLIGHT` to launch one fresh private session, validate a
real PNG screenshot and non-empty Appium screen recording, then delete both raw
captures and clean up the app/session. Neither the APK nor the captures enter
the workspace or archived Jenkins artifacts.
