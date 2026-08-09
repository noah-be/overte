<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# iOS privacy preparation

The app bundle contains `PrivacyInfo.xcprivacy` at its root. Its initial
required-reason declarations map directly to first-client behavior:

| Category | Reason | Overte use |
| --- | --- | --- |
| File timestamps | `C617.1` | Manage metadata for cache and app-container files |
| System boot time | `35F9.1` | Measure elapsed time for simulation, rendering, audio, and network timers |
| Disk space | `E174.1` | Check that assets and cache files can be written and prune a low-space cache |
| User defaults | `CA92.1` | Store settings accessible only to this app |

These declarations do not permit tracking or unrelated use. The manifest sets
tracking to false and lists no tracking domains.

Each linked framework and static dependency remains responsible for documenting
its own required-reason API use. Before a release candidate, generate Xcode's
privacy report and compare it with source, linked-symbol, and dependency
manifests. A missing or unexpected category blocks the candidate.

`NSPrivacyCollectedDataTypes` remains empty for the bootstrap because it does
not send user data. The integrated client's actual account, voice, telemetry,
and crash-report behavior must be reviewed against both the runtime network
trace and App Store privacy disclosures before that array can be considered
final. Enabling telemetry or crash uploads is not implied by the port.

