<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Fast path from iPad preview to usable Overte client

This is the execution order for the first usable iPad build. Each stage must
produce an installable IPA and preserve the already passing device path. Work
that does not unlock the next physical-device test stays deferred.

## Stage 0: native device shell — complete

- unsigned arm64 iPhone/iPad IPA built on hosted macOS;
- Sideloadly signing and installation on a physical iPad;
- Metal rendering, safe areas, rotation, touch, lifecycle, networking state,
  audio-session setup, and application containers.

Exit evidence: the physical iPad launches and reports drag coordinates.

## Stage 1: Overte connection preview — implemented, device test pending

- accept place names, direct domain addresses, and `hifi://`/`overte://` links;
- normalize addresses with the same default domain port as the desktop client;
- resolve a place through `mv.overte.org` and show its live domain address,
  attendance, and heartbeat state;
- remember the last destination without storing credentials; and
- make the unsupported boundary explicit for direct protocol connections.

Exit evidence: `overte_hub` resolves on the physical iPad and an external
`hifi://overte_hub` link reaches the same screen.

## Stage 2: minimal domain session

Extract or link the smallest Qt 6-compatible subset of `networking` needed for
`SockAddr`, packet headers, `DomainHandler`, and `NodeList`. Disable account
authentication, ICE fallback, scripts, and nonessential node types initially.
Send a valid domain check-in, receive the domain list, expose connection state,
and reconnect after a network interruption.

Exit evidence: the iPad reports a domain session and the domain reports the
client, without yet rendering entities.

## Stage 3: visible world

Bring in entity packets, the entity tree, asset requests, GLM, and the minimum
GPU abstraction. First render a bounded diagnostic subset of entities through
MoltenVK; compare it with the known native Metal frame before committing to the
long-term backend. Defer web entities, particles, overlays, and scripting.

Exit evidence: the iPad downloads and displays a static representative scene
from `overte_hub` for 30 minutes without unbounded memory growth.

## Stage 4: local avatar and navigation

Integrate avatar state and the minimum animation/model path. Map left-side
touch to planar movement, right-side drag to camera yaw/pitch, tap to interact,
and system text input to the address/chat boundary.

Exit evidence: the user can enter, see, and navigate a world on the iPad.

## Stage 5: spatial audio and identity

Integrate the Qt 6 audio replacement, mixer packets, output routing, microphone
permission, mute control, interruption recovery, and then account/domain
authentication. Credentials remain in Keychain-backed platform storage.

Exit evidence: authenticated entry, audible spatial mix, consensual microphone
capture, and recovery after backgrounding or route changes.

## Stage 6: scripts and compatibility closure

Link the audited non-JIT script runtime, static plug-ins, and Qt WebView-backed
web surfaces. Re-enable deferred features individually behind device tests.

Exit evidence: the representative world and avatar behave like the desktop
client within the declared first-release scope.

## Continuous gates

Every stage keeps Linux contracts, iPhone/iPad simulator launches, unsigned
device compilation, bundle/privacy validation, and physical iPad smoke results
green. No stage may introduce executable-memory entitlements, downloaded native
code, dynamic plug-ins, desktop frameworks, or committed signing credentials.
