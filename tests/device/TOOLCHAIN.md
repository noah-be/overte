# Pinned open-source device-lab toolchain

[`toolchain.lock.json`](toolchain.lock.json) is the machine-readable source of
truth for shared, directly downloadable automation artifacts used by the
physical-device E2E lab. It is a dated snapshot, resolved on 2026-08-25, rather
than a request for a package manager's moving `latest` tag. Its structure is
specified by
[`schemas/toolchain-lock.schema.json`](schemas/toolchain-lock.schema.json).

| Component | Pin | Compatibility decision |
| --- | --- | --- |
| Node.js / npm | 24.19.0 / 11.17.0 | One exact lab runtime satisfying all three npm packages' `^20.19.0 \|\| ^22.12.0 \|\| >=24.0.0` and npm `>=10` engines. |
| Appium Core | 3.7.0 | Shared Appium 3 server for both mobile drivers. |
| UiAutomator2 driver | 8.5.0 | Declares Appium peer `^3.0.0-rc.2`; used on Android. |
| XCUITest driver | 12.8.0 | Declares the same Appium peer; drives physical iOS/iPadOS from macOS or, with the pinned RemoteXPC path, Linux. |
| Appium iOS RemoteXPC | 5.15.3 | Exact Linux device-transport pin; replaces XCUITest's moving optional `^5.13.2` resolution and requires a root-owned TUN tunnel. |
| WebDriverAgent | 16.8.0 | Exact WDA source paired with XCUITest 12.8.0; built and signed on the protected macOS producer, then installed and launched by Fedora. |
| age | 1.2.1 | Encrypts signed IPA payloads to the Fedora lab before they enter public GitHub Actions artifact storage. The Linux archive and extracted executable are both hash-pinned. |
| Apple Codesign (`rcodesign`) | 0.29.0 | Open-source Linux verification of the embedded Mach-O code signature. The Linux archive and extracted executable are both hash-pinned. |
| Jenkins LTS | 2.568.2 | The LTS current on the resolution date; Jenkins documents Java 21 or 25 for this line. The lab standardizes on open-source Java 21. |
| Plugin Installation Manager | 2.15.0 | Resolves and installs the complete Jenkins plugin closure. |
| Jenkins plugins | 8 direct, 69 resolved | Direct pins include Pipeline, JUnit, device locking/credentials, JCasC, and Git. Every transitive is frozen in [`jenkins/plugins.lock.txt`](jenkins/plugins.lock.txt), with its URL and SHA-256 in [`jenkins/plugins.artifacts.lock.json`](jenkins/plugins.artifacts.lock.json). |

All listed automation components are open source: Appium and its drivers are
Apache-2.0; age is BSD-3-Clause; Apple Codesign is MPL-2.0; Jenkins, its
selected plugins, and the Plugin Installation Manager are published as
open-source projects. The lock records SPDX identifiers for the top-level
tools. Platform dependencies can impose a separate boundary:
real iOS artifacts still require Apple's Xcode, signing, and XCTest stack on a
macOS build host. For iOS 18 and newer, the physical test controller itself may
be Linux: the signed application and WDA are handed to the pinned RemoteXPC
runtime, while no Xcode process runs on the Fedora lab host.

## Offline validation

The normal validator uses only repository files. It neither discovers devices
nor contacts a registry:

```bash
python3 tests/device/validate_toolchain_lock.py
python3 tests/device/validate_toolchain_lock.py --list-artifacts
```

It checks exact versions, HTTPS URLs, non-placeholder SHA-256 values, npm engine
and Appium peer compatibility, Jenkins core/Plugin Manager coupling, and the
eight direct plugins against the full sorted plugin closure. It additionally
checks the exact age/Apple Codesign versions,
licenses, release archives, and extracted-executable hashes. It also rejects plugin-list drift between `plugins.txt`, the JSON
lock, and `plugins.lock.txt`.

After downloading an artifact, verify its bytes before installation:

```bash
python3 tests/device/validate_toolchain_lock.py \
  --artifact jenkins.lts=/path/to/jenkins.war
```

Artifact IDs and their exact URLs are emitted by `--list-artifacts`. The
validator never downloads on behalf of the caller, which keeps preflight
deterministic and makes network policy an installation concern.

## Jenkins plugin installation

Install the full lock, not the smaller direct list, and prevent the Plugin
Installation Manager from promoting dependencies:

```bash
java -jar jenkins-plugin-manager-2.15.0.jar \
  --jenkins-version 2.568.2 \
  --plugin-file tests/device/jenkins/plugins.lock.txt \
  --latest=false \
  --plugin-download-directory /path/to/JENKINS_HOME/plugins
```

[`jenkins/plugins.txt`](jenkins/plugins.txt) documents only the eight direct
requirements. It is useful while reviewing why a plugin exists, but it is not
the production installation input. The 69-entry lock was checked by asking
Plugin Installation Manager 2.15.0 to resolve it again with `--latest=false`;
the result was byte-for-byte the same plugin/version set.

## Provenance and update procedure

Versions and compatibility metadata come from primary project sources:

- [canonical npm registry](https://registry.npmjs.org/) package records for
  Appium Core, UiAutomator2, and XCUITest, including npm SHA-512 integrity;
- [Jenkins stable release metadata](https://updates.jenkins.io/stable/latestCore.txt),
  [Java support policy](https://www.jenkins.io/doc/book/platform-information/support-policy-java/),
  and [plugin version metadata](https://updates.jenkins.io/plugin-versions.json);
- the [Plugin Installation Manager 2.15.0 release](https://github.com/jenkinsci/plugin-installation-manager-tool/releases/tag/2.15.0);
- the [age 1.2.1 release](https://github.com/FiloSottile/age/releases/tag/v1.2.1);
- the [Apple Codesign 0.29.0 release](https://github.com/indygreg/apple-platform-rs/releases/tag/apple-codesign%2F0.29.0).

The npm SHA-256 values were calculated from the exact immutable version
tarballs and cross-checked against their registry SRI records. Jenkins WAR and
Plugin Manager hashes match the projects' published `.sha256` files. Direct
plugin hashes are the hexadecimal form of the SHA-256 values in Jenkins plugin
metadata; this covers all 69 direct and transitive HPIs. No checksum is inferred
from a filename or represented by a dummy value.

To update, change the whole compatible set in one review: resolve registry
versions, download and hash exact artifacts, select the Jenkins LTS and Java
pair, resolve every plugin with that core and the pinned Plugin Manager, then
update the JSON lock, both plugin files, resolution date, tests, and this table.
Run the offline validator and its unit tests before installing anything. A
newer individual driver or plugin is not accepted merely because it exists.
