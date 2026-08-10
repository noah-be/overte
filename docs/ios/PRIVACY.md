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

## Transport, links, and capabilities

The integrated client keeps ATS enabled. Its only ATS relaxation is
`NSAllowsLocalNetworking`, for user-selected services on the local network;
there is no arbitrary-load switch and no domain exception list. The built-in
metaverse directory and default asset endpoints use HTTPS. Domain, audio, and
entity traffic over UDP is outside ATS, but remains subject to the separately
documented local-network permission gate.

The full-client bundle registers only `hifi` and `hifiapp`, matching
`NetworkingConstants.h` and the existing URL dispatch path. HTTP and HTTPS are
ordinary outbound links and are not claimed as application-owned schemes. The
bootstrap additionally accepts its explicitly implemented `overte` alias.

Both targets use the audited empty `Overte.entitlements` allowlist. Microphone
and local-network prompts are Info.plist usage declarations, not signing
entitlements. A capability may only be added after a source-level requirement
and provisioning impact have been reviewed. These are build-time contracts;
device behavior still requires the documented iPad validation run.

## iPad bundle boundary

The integrated target explicitly selects device families `1,2`, the configured
iOS deployment target, and both device and simulator SDK platforms. Its iPad
orientation list supports portrait, upside-down portrait, and both landscape
orientations; `UIRequiresFullScreen` remains false so the metadata does not
exclude iPad multitasking.

The launch screen references the existing `AccentColor`, and Xcode compiles the
existing `Assets.xcassets` catalog with its universal `AppIcon`. No additional
icon or launch artwork is synthesized. Host contracts can validate this wiring,
but final icon rendering, launch presentation, rotation, and multitasking remain
iPad test items.
