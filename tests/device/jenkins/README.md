# Local Jenkins device lab

This directory adds scheduling, exclusive device reservations, credential
binding, time limits, and result publication around the universal device
runner. Jenkins does not contain test scenarios or target automation; those
remain in `tests/device/catalog.json`, `tests/device/modules`, and
`tests/device/adapters`.

The intended deployment has the Jenkins controller and three logical agents on
the same trusted computer. Each agent owns one scheduling role while the host
owns the attached devices and their local transport services:

```text
Jenkins controller (no executors)
  -> overte-device-ipad  (one executor, private remote root)
  -> overte-device-phone (one executor, private remote root)
  -> overte-device-pico  (one executor, private remote root)
       -> role-specific Pipeline -> device lock -> adapter -> physical target
```

Do not run device transports inside the controller container. Keep the agent in
the same trusted host context that owns ADB, Appium, USB access, and any
RemoteXPC service used by the selected physical target.

## Open-source Jenkins components

Use the exact Jenkins LTS, Plugin Installation Manager, and plugin closure in
[`../toolchain.lock.json`](../toolchain.lock.json) and
[`plugins.lock.txt`](plugins.lock.txt). `plugins.txt` contains the smaller set
of direct reasons for those dependencies:

- Pipeline and Declarative Pipeline
- Lockable Resources
- Credentials Binding and Plain Credentials
- JUnit
- Configuration as Code
- Git

Jenkins and these plugins are open source. No cloud device service or
proprietary Jenkins plugin is required. The complete lock was resolved for the
pinned core, including transitives. Install it with Plugin Installation Manager
and `--latest=false`; allowing the update center to select newer dependencies
would defeat the reproducible lab setup. Validate the lock offline before use:

```bash
python3 tests/device/validate_toolchain_lock.py
```

Install the locked stack into user-owned directories and create private,
disabled target templates with:

```bash
python3 tests/device/jenkins/local_lab.py install \
  --install-root "$HOME/.local/share/overte-device-lab" \
  --config-root "$HOME/.config/overte-device-lab" \
  --java /absolute/path/to/jdk-21/bin/java
python3 tests/device/jenkins/prepare_private_targets.py \
  --config-root "$HOME/.config/overte-device-lab"
```

On Linux, the bootstrap can install and start a loopback-only controller,
three separate inbound agents, and isolated Android/iOS Appium servers as
graphical user services:

```bash
python3 tests/device/jenkins/local_lab.py install-systemd-user-services \
  --config-root "$HOME/.config/overte-device-lab"
python3 tests/device/jenkins/local_lab.py status \
  --config-root "$HOME/.config/overte-device-lab"
```

The controller listens on `127.0.0.1:8080`, has zero executors and no anonymous
access. Its generated administrator password, JCasC file, Appium state, and
target configurations stay outside the checkout with private permissions.
Every generated target starts disabled; add its private selector and enable it
only after completing the corresponding hardware gate. On Windows and macOS,
run the `controller` and `agent` subcommands from the logged-in lab account or
translate them into that OS's user-session service mechanism.

The controller's built-in executor count remains zero. Each role agent has
exactly one executor and its own remote root. The Android and iOS Appium
services listen only on loopback at separate endpoints; their target
capabilities also reserve explicit UiAutomator2 `systemPort` and XCUITest
`wdaLocalPort` values. Keep the controller on localhost or a trusted LAN,
enable authentication, and do not expose it directly to the Internet.
The Phone node retains the legacy `overte-device-interactive` compatibility
label so previously defined jobs remain schedulable; new device jobs must use
only their exact role label.

## Register one physical target

1. In **Manage Jenkins -> Credentials**, create a **Secret text** credential.
   Its secret is the adapter's private target selector (ADB serial or Appium
   target alias). A useful credential ID is
   `overte-android-phone-01-selector`.
2. In **Manage Jenkins -> Lockable Resources**, create a resource such as
   `android-phone-01`. Do not use the serial number as the resource name.
3. Create a Pipeline job from SCM and select
   `tests/device/jenkins/Jenkinsfile` as its script path. The Pipeline maps the
   selected profile to exactly one of the three role labels.
4. Set `DEVICE_RESOURCE`, `TARGET_SELECTOR_CREDENTIAL_ID`, and the matching
   `TARGET_PROFILE` when starting the job.

The Jenkins lock serializes jobs globally. The runner's hashed local lock stays
enabled as a second guard against direct concurrent invocations.

Android build jobs use two additional private agent roots generated in
`agent.env`: `OVERTE_ANDROID_BUILD_ROOT` and `OVERTE_CONAN_CACHE_ROOT`. Never
run Phone and Pico build entry points directly in the same SCM checkout. Wrap
the complete `all` command with `android_build_workspace.py` as documented in
[`CONAN_CACHE_ISOLATION.md`](CONAN_CACHE_ISOLATION.md). It clones the exact
clean commit into one job-private checkout and also isolates Gradle, temporary,
staging, and Conan state, so Phone and Pico may build concurrently without
mutating each other's output or the Jenkins checkout.

The selected adapter still needs its normal private host configuration. For
example, configure `OVERTE_ANDROID_ADB` or `OVERTE_APPIUM_TARGETS` in the agent
environment as documented by the adapter. Do not store a populated target file
in Git or in archived artifacts.

For `appium-ios` on Fedora, add a Secret Text credential named, for example,
`overte-ios-github-actions-token`. It needs Actions read/write on the producer
repository: write dispatches the protected workflow and read monitors the
exact returned run and downloads its artifacts. Jenkins never receives an
Apple signing secret or account credential; those remain in the protected
GitHub Environment on the macOS producer.

Also add the Fedora lab's age private identity as a Jenkins Secret File, for
example `overte-ios-age-identity`. Its public recipient is the fixed protected
producer Environment variable. The public repository stores only encrypted
payloads; provisioning-profile device identifiers never occur in a publicly
downloadable Actions artifact. Jenkins exposes the private identity only for
the synchronization step and never puts its contents or path in a command line.

Set the four audited Qt cache/artifact inputs when starting the job. The
`Fedora iOS runtime` stage first checks the root-owned immutable RemoteXPC
service copy (never the user-owned Appium install), then
dispatches and waits for the producer, downloads and verifies both signed IPAs,
and updates a mode-0600 per-build copy of the private Appium target file. That
copy, the receipt, and IPAs remain below Jenkins' external temporary result
root; result staging never archives them. The `post/always` cleanup removes the
decrypted IPAs, receipt, security-tool staging and target copy after target
cleanup, including aborted builds, and refuses paths outside the exact private
build root or through symlinks. `IOS_PRODUCER_RUN_ID` can instead
select an existing unexpired successful protected run. The adapter rehashes
the receipt-bound IPA paths before creating a session.

## Controlled fixture

Select `FIXTURE_MODE=embedded` for a debug Android Phone/Pico APK containing the
fixed repository scene and probe. No listener or public host is needed; the
shell-protected debug launcher copies those assets into application storage.

Select `FIXTURE_MODE=network` for a signed iOS E2E test build. In this mode
`e2e-core` starts `tests/device/fixture/serve.py` for
the duration of the suite. Set `FIXTURE_PUBLIC_HOST` to a DNS name or LAN IPv4
address of the agent that the physical device can reach. On a phone or tablet,
`127.0.0.1` points to that device instead of the Jenkins agent. Port `0` is
supported for iOS: after the
fixture binds, the helper atomically updates only the selected target's
`testBuild.fixtureOrigin` in the mode-0600 per-build target copy before the
adapter starts. The repository template and long-lived private source file are
never changed.

Port `0` lets the operating system choose a free ephemeral port, which permits
parallel devices. The firewall must allow the fixture server on the trusted
test network. If firewall policy requires one fixed port, set `FIXTURE_PORT`
and create a second Lockable Resource for that port before enabling concurrent
jobs.

The fixture has no external dependencies and sends `Cache-Control: no-store`.
The helper waits for its ready file, injects the public scene URL through
`OVERTE_E2E_SCENE_URL`, and stops the server in a `finally` block.

## Pipeline order and failure behavior

Every build follows this order:

1. validate parameters;
2. run all device-free contracts, including Conan isolation and iOS handoff;
3. for iOS, require RemoteXPC and synchronize the protected signed producer;
4. reserve the physical target and run `smoke`;
5. optionally run the independently reported `domain-smoke`, `asset-smoke`,
   `sound-smoke`, and Pico `vertical-locomotion` suites;
6. run `e2e-core` only after smoke and the selected content suites pass;
7. optionally run the accessibility audit;
8. optionally run `stability` on every profile, followed by the separately
   reported `lifecycle-stability` suite on Android/iOS only.

Smoke is mandatory. For the Pico 4 lab, select `android-pico-adb`, set its
lockable resource and selector credential, then enable `RUN_DOMAIN_ENTER`,
`RUN_ASSET_LOAD`, and `RUN_SOUND_PLAYBACK`. All three require
`FIXTURE_PUBLIC_HOST` to be the agent's LAN address reachable from the headset.
Domain entry additionally requires absolute trusted build paths in
`DOMAIN_SERVER_EXECUTABLE` and `ASSIGNMENT_CLIENT_EXECUTABLE`. Asset and sound
start the repository HTTP fixture automatically and may be used with an
otherwise embedded Android fixture configuration.

Enable `RUN_VERTICAL_LOCOMOTION` only for `android-pico-adb` after provisioning
the debug-only OpenXR input layer and isolated ADB environment described in
[`../openxr_input/PICO4_CONTROLLER_AUTOMATION.md`](../openxr_input/PICO4_CONTROLLER_AUTOMATION.md).
The separately reported suite verifies one bounded jump and landing followed
by upward flight without replacing the running application process.

`RUN_CORE` defaults off for the first setup run because the
default ADB profile truthfully lacks touch/controller input. Enable core for a
complete Appium Android or iOS profile. Long health/lifecycle jobs
should start only after the same physical target has already passed repeatable
short core runs through its input-capable adapter. Telemetry is optional on
iOS and strict when advertised; PID-preserving lifecycle transitions
run only on Android/iOS.
Per-suite timeouts are 10 minutes for smoke, asset, and sound; 15 minutes for
domain and accessibility; 30 minutes for core, four hours for stability, and
one hour for lifecycle stability. They start after the device lock is acquired so
cleanup can run outside an expired suite timeout while the lock is still held.
The whole build, including time spent in the resource queue, has an eight-hour
ceiling.

The runner performs normal adapter cleanup. The Pipeline calls the adapter's
idempotent cleanup operation again inside the device lock even after failures,
interrupts, or per-suite timeouts. A Pipeline-level `post` fallback retries
cleanup under the same lock if an outer timeout interrupted that step. An
infrastructure failure is represented as a JUnit error; a failed Overte
expectation is a JUnit failure.

## Results and selector privacy

The runner first writes into Jenkins' temporary workspace sibling returned by
`pwd(tmp: true)`, never into the source checkout. After cleanup, `run_ci.py`
checks the complete result tree for the private selector in both contents and
file/directory names, rejects symbolic links and special files, then checks the
copied tree again. Only a safe tree is copied to `device-ci-artifacts/BUILD_NUMBER/SUITE`
and published with JUnit and `archiveArtifacts`.

If the runner is killed before creating JUnit, or if a selector leak is found,
the original files remain outside the published workspace and the helper
creates a private-safe synthetic infrastructure error. Jenkins masks the bound
credential in console output and the Pipeline fails after publishing that
diagnostic. The selector still exists briefly in local
process arguments because the current runner/adapter protocol uses `--target`;
therefore the agent machine must not be shared with untrusted operating-system
users.

Failure screenshots and native Accessibility XML are privacy-sensitive and are
disabled by default. Enable `CAPTURE_FAILURE_ARTIFACTS` only for a dedicated lab
account with an empty test profile. The runner requests one best-effort window
or device screenshot before cleanup when a module fails; a screenshot failure
never replaces the original outcome.

## Device-free verification

Run the exact preflight used by Jenkins without connecting to hardware:

```bash
OVERTE_CI_WORKSPACE="$PWD" \
  python3 tests/device/jenkins/run_ci.py self-check
```

This validates the fixture, all universal harness/adapter contracts, the
Jenkins helper, the full core scenario through the deterministic mock adapter,
cleanup behavior, secret quarantine, and the required Jenkinsfile safety
layers. It does not start ADB, Appium, or Overte.

After smoke and core are repeatable on demand, add a Jenkins cron trigger to the
job (for example a nightly `H H * * *`). Keep `RUN_SOAKS` off until short runs
are stable; then use a separate scheduled job with retention appropriate for
larger logs and videos.
