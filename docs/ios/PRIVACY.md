<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# iOS privacy preparation

The app bundle contains `PrivacyInfo.xcprivacy` at its root. Its initial
required-reason declarations map directly to first-client behavior:

| Category | Reason | Overte use |
| --- | --- | --- |
| File timestamps | `C617.1` | `QFileInfo::lastModified()` reads metadata for cache and app-container files (`libraries/networking/src/FileResourceRequest.cpp`) |
| System boot time | `35F9.1` | `QElapsedTimer` measures elapsed time for the client (`interface/src/main.cpp`) |
| Disk space | `E174.1` | `QStorageInfo::bytesFree()` protects cache writes and pruning (`libraries/shared/src/shared/FileCache.cpp`) |
| User defaults | `CA92.1` | `QSettings` stores settings accessible only to this app (`libraries/shared/src/SettingManager.cpp`) |

These declarations do not permit tracking or unrelated use. The manifest sets
tracking to false and lists no tracking domains.

Both the bootstrap and integrated client copy the same audited manifest to the
root of the app bundle. Configure fails if the source manifest is absent, and
bundle verification or `package-client` fails if the bundled plist differs
from the exact allowlist. Adding a category therefore requires source evidence,
an approved reason review, and an intentional contract update.

Each linked framework and static dependency remains responsible for documenting
its own required-reason API use. Before a release candidate, generate Xcode's
privacy report and compare it with source, linked-symbol, and dependency
manifests. A missing or unexpected category blocks the candidate.

`NSPrivacyCollectedDataTypes` remains empty for the bootstrap because it does
not send user data. The integrated client's actual account, voice, telemetry,
and crash-report behavior must be reviewed against both the runtime network
trace and App Store privacy disclosures before that array can be considered
final. Enabling telemetry or crash uploads is not implied by the port.
