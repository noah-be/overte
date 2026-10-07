# Native Image comparison fixture

This is a pending integration harness, not a completed native pixel result. It complements the already completed standalone BrowserWorld PNG/KTX Image comparison; it does not measure public-world loading speed.

The harness uses four exact SHA-checked saved public Hub assets (opaque shrub-bluepops PNG/KTX and mask jungle-leaf PNG/KTX). It writes these bytes and version-1 `.texmeta.json` metadata only into a fresh UUID folder of the existing isolated laboratory asset HTTP server. The metadata contains relative filenames and the audited S3TC sRGB format. No public service is changed or contacted.

A fresh, muted pinned 2026.04.1 native observer creates four collisionless, 360-second entities at (60,10,0): a magenta background Box, its unlit Material, and two Images. It refuses creation unless the real native permission `Entities.canRez()` is granted. No domain permissions, native quality settings, framebuffer/resource loader, or renderer-loaded flags are changed. The existing winding fixture area at (40,10,0) is not used.

The normal visitor cookie bootstrap and `CompressedColorSession` join the actual local domain through the gateway. Only the native-created fixture entities are rendered by the real BrowserWorld. Authenticated pose packets position the native octree query at this off-spawn fixture. Compressed assets use the current real session ID, permission revision, World abort signal and operator-validated asset routes; there is no manually injected cache authority.

Each original/metadata Image case must reach native `TextureCache.prefetch(url, DEFAULT).state === FINISHED`, have at least three subsequent real draw-job statistics events, retain the exact independent camera, and produce an actual native snapshot within the unchanged 30-second runner deadline (29-second native guard). Browser readiness requires the actual mapped texture, completed shaders and a visible Image root. Final oracles inspect screenshot pixels, not just entity JSON or resource flags.

Opaque-case edges against the unlit magenta background calibrate each renderer's projection. A fixed 64 by 64 sample grid checks texture detail and orientation. Within each engine, original-versus-KTX RGB mean absolute error must remain at most 10 and mask disagreement at most one percent, matching the existing compressed-color oracle. Across engines, channel-centered pattern correlation must be at least 0.9 and background-hole disagreement at most three percent. The latter compares orientation and actual holes without claiming identical global native/browser tone grading. Opaque coverage must be below one percent background, while the mask must contain both visible pixels and holes. A missing texture, flat black frame, opaque replacement, reversed mapping, unsupported compression, absent camera/frame readiness, permission denial, or teardown failure is a failed result; none is silently counted as a native parity pass.

Cleanup deletes only the four author-owned entity IDs that still have this UUID prefix. The authenticated gateway must deliver their deletions. All seven existing `Browser Lab ` entity IDs must remain exactly unchanged; raw IDs are kept only in process memory. Cleanup is also invoked in `finally`; expiration is a backup, not successful cleanup evidence. Only owned local files/processes are removed. The private native log is written with mode 0600; portable results contain aggregate state, pixels, versions and source/input hashes. Source hashes must agree at start/end.

## Validation completed in the restricted preparation environment

- `node --check` passed for both integration scripts.
- `node --test --test-isolation=none tests/native-image-fixture.test.mjs`: 8/8 passed. This executes the production native author in a VM and verifies exact owned writes, default texture role, mode-specific resource/frame gating, unchanged deadline, permission refusal and ownership-limited cleanup. These tests do not substitute for real native/GPU execution.
- The additional six pixel contracts reject missing, flat and mirrored images
  against actual SHA-audited source colors and detail. See
  [the diagnosed dark-image oracle correction](NATIVE_IMAGE_ORACLE.md).
- No native observer, services, GPU or original topic files were started or changed by the preparing agent.

## Required host run

First copy the three reviewed source files into the topic under the same paths and run the focused native-author tests. Use the existing managed domain, gateway 8090, asset HTTP server 45110, native X display :95 and private native PulseAudio socket. The operator asset allowlist must already include the local laboratory asset origin. The isolated native author must have actual normal fixture-creation permission; this harness does not obtain or modify that permission. Both saved PNG/KTX pairs must exist under `build/browser-hub-lab/hub` with the pinned SHA values. The already-approved development origin5173 must be free. The first5198
cohort failed WebSocket admission and remains a negative result; the
gateway origin allowlist was preserved.

Run each stock browser sequentially, with no other native/GPU or Hub performance test:

```sh
cd browser-client
OVERTE_LAB_BROWSER=system-chromium \
OVERTE_LAB_BROWSER_DISPLAY=:0 \
OVERTE_LAB_CHROMIUM=/tmp/overte-chromium-hardware-probe/extracted/usr/lib64/chromium-browser/chromium-browser \
OVERTE_LAB_CHROMIUM_LIBRARY_PATH=/tmp/overte-chromium-hardware-probe/extracted/usr/lib64 \
node tests/integration/native-image-state.mjs

OVERTE_LAB_BROWSER=system-firefox \
OVERTE_LAB_BROWSER_DISPLAY=:0 \
node tests/integration/native-image-state.mjs
```

Each run writes UUID-owned screenshots, a portable report and a private log into `build/browser-lab/evidence/image-state/<UUID>`. Preserve failed reports and inspect the actual screenshot before diagnosing a threshold failure. A completed report is required before describing native Image pixel parity as tested.
