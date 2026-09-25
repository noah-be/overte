# Phone SH-004 installed-candidate adapter

This Phone-owned entry delegates device behavior to the original Shared Android
adapter. Its manifest retains `android-phone-adb`. The Shared Android and Appium
adapters are not modified and gain no installation claim from this wrapper.
Default configuration is diagnostic/unbound and emits no execution identity.

`appium.json` similarly delegates to the original Shared Android Appium adapter,
retaining `appium-android` and its actual Tablet/text/touch capabilities. Use the
same candidate arguments after `appium_adapter.py` in a private manifest. Bound
Appium mode requires an `io.github.noah_be.overte.phone` target with one explicit ADB/
Appium device mapping, `appium:appPackage=io.github.noah_be.overte.phone`, and a loopback Appium
server. Any `appium:app` must be a local byte-verified copy of the same candidate,
not an unverified path or download URL. Remote-grid binding fails closed; local
ADB cannot attest a remote grid's selected device. Physical targets pass the
original Shared physical ARM64 Phone check. The PH-003 virtual path additionally
reads the selected target's QEMU flag, primary x86_64 ABI, API >=26 and GLES >=3
before binding; configuration alone cannot relabel a physical/ARM64 target.
The original private Appium configuration schema and ownership checks remain.
Besides reserved describe, the wrapper rechecks installed bytes after session
creation/reuse and before every operation (session creation may itself install an
application). It does not fabricate touch/probe observations or advertise added
capabilities. Unbound Appium diagnostics retain the original behavior.

For a future authorized bound run, place the existing Phone candidate verifier's
arguments in a private adapter manifest command after `adapter.py`: `--record`,
`--artifact`, `--expected-source-sha`, `--expected-inputs`, `--expected-version-code`,
`--minimum-version-code`, `--channel`, and all six original SH-009 evidence paths
(`--bootstrapPackages`, `--hostPackages`, `--targetPackages`, `--generatedOutputs`,
`--spdx`, `--cyclonedx`). Every argument is required together. Freeze expectations
independently of the received candidate record. Do not derive expected inputs
from that record. No new common schema or standalone installation receipt exists.

Optionally add BOTH `--build-evidence PATH` and
`--expected-artifact-sha256 SHA256` to require the original SH002 Android mandatory
tier join as well. These require the full SH009 argument set, and an independently
frozen expected artifact digest. Both Phone entrypoints pass them to the same
Phone consumer and reject failed/missing evidence before native construction or
discovery. Without them, installed-byte identity remains unqualified by build
tiers. Even a successful tier join does not authenticate its receipt producer or
qualify a build. The existing four-field executionIdentity is unchanged; it gains
no tier/producer-trust assertion. Invalidated tier files do not prevent cleanup.
The current SH002 Phone plan's ARM64 package checks do not qualify a PH003 x86
candidate; equivalent emulator build acceptance still needs its own evidence.

The original Phone/SH-009 verifier checks candidate bytes, source association,
version/channel and independent input/evidence bytes before discovery. At each
reserved `describe`, the wrapper asks PackageManager for the installed
`io.github.noah_be.overte.phone` path and hashes that actual file on Android. It accepts only
one monolithic `/data/app/.../base.apk`, rejects split packages and unsafe paths,
rechecks the PackageManager path and local candidate binding, and emits the exact
SH-004 v003 `executionIdentity` extension only after all checks pass. Missing
read access or `sha256sum` support fails closed. It never echoes runner flags as
installation evidence. Bound install operations must use the same candidate;
bound upgrade is deliberately unsupported because it changes candidate identity.
Cleanup does not require a still-valid candidate: invalidation fails execution
but must not prevent the existing stop/cleanup path. Cleanup emits no identity.

Provision the verified candidate in the authorized workflow before a bound run:
the original runner checks `describe` before executing modules. Pass the runner's
three independent identity flags required by SH-004 v003 as well. It rechecks
description after modules while the target is reserved and emits the byte-bound
result. There is no automatic install or device reservation from this document.

This proves a checked relationship to installed APK bytes under a trusted Android
PackageManager/ADB boundary, not package-signature acceptance, privileged-device
attestation, source-build authenticity, anti-feature compliance or protection
against concurrent privileged replacement between observations. Original SH-002/
009 source/provisioning gates and trusted lab execution remain required. Physical
GPU/page-size/form-factor proof and AndroidJUnit source ingestion are separate.
The direct ADB entry remains physical ARM64; only the Appium wrapper has the
explicit PH-003 x86_64 path. No emulator is started by either adapter. Appium
touch behavior stays in original Shared
code and its own production assertions, not in the APK identity wrapper.

Focused host checks use the real wrapper and original candidate verifier, with
only synthetic ADB/native boundaries. No target is discovered, installed or run:
Twenty-one methods include both real tier-aware dispatchers, rejection before
native construction, and cleanup after tier invalidation.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s android/phone/tests/device -p test_installed_identity.py
```
