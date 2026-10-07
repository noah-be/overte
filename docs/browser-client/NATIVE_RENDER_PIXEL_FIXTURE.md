<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native render-state pixel fixture

`tests/integration/native-render-state.mjs` is an isolated laboratory integration
fixture, not a public-world writer or a replacement for real-world acceptance.
Its native reference is the installed 2026.04.1 Interface (f91d15a). The harness
records the actual executable SHA-256 and requires that release's version.
Actual native comparisons passed all five cases in stock Chromium 154 and
Firefox 156 on 2026-10-01, with owned-entity cleanup and preservation of all seven
original entity identities. Exact versions, source hashes and measured pixels
are in [the curated comparison](evidence/native-render-state-20261001.json).
These are channel-dominance tests, not exact absolute transparent color parity.

The fixture adds four finite-lifetime domain entities under its unique prefix:
a black background, its unlit Material, a Model and its Material. It leaves the
existing seven laboratory entities intact. A fresh, muted native profile creates
the actual entities and edits only its own Material. Its own command file and
snapshot directory avoid changing the existing observer's commands or settings.
Cleanup deletes only owned IDs whose current names still match that prefix and
checks that actual gateway deletion updates arrive. It also verifies preservation
of all seven original entity identities without publishing those IDs. Unexpected
native failure leaves a maximum 240-second server lifetime on the owned fixtures;
it is reported as failure, not successful cleanup.

The generated glTF contains exactly one mesh and one material. Its first triangle
is CCW, nearer the camera and red; its second is reverse-wound, farther and green.
KHR_materials_unlit and BLEND alpha 0.5 provide a known layer-order test. Material
entities exercise CULL_NONE, CULL_BACK and CULL_FRONT. Separate explicit mask and
fully opaque controls use nearer-triangle depth occlusion. Mask mode has a real,
owned white RGBA PNG bound as both albedo and opacity maps.

The browser reads genuine, authenticated entity snapshots and their owned asset
URLs through BrowserSession and the gateway into BrowserWorld. It does not inject
an alternate synthetic world or change loaded materials to make the test pass.
A fixed diagnostic camera and DPR 1 render the actual scene into an owned PNG.
Native snapshots use Window.takeSnapshot and its real completion callback. Both
PNGs retain their complete bytes and SHA-256. The central 16×16 sample checks
channel dominance. A measured limitation remains: native transparency blends
linear values before its final sRGB conversion, whereas the current browser
canvas blends already encoded values. Native single-face 50-percent red measured
187; the browser measured 127. Mask and opaque controls both measured 255.
Correcting this requires a linear world target and a final presentation pass;
the fixture does not adjust alpha or colors to conceal the difference.
The expected no-cull blend is green-dominant, demonstrating authored triangle
order and no translucent depth writes. Back culling is red-only, front culling
green-only, and mask/opaque controls retain the nearer red triangle. The browser
report also records actual imported material side, depthWrite, opacity and
forceSinglePass; it does not substitute those diagnostic properties for pixels.

Current repository source expresses native defaults in Material.cpp (CULL_BACK),
State.h (frontFaceClockwise false), GLBackendState.cpp (GL_CCW), and
RenderPipelinesInit.cpp.in (LESS_EQUAL, translucent depth writes disabled and
SRC_ALPHA/INV_SRC_ALPHA blending). These source facts define the expected fixture;
the actual reference comparison now confirms their five tested behaviors.

The native observer anchors its own avatar as well as its independent camera:
initial entity streaming follows the avatar's 10-metre query sphere. It calls
the camera orientation setter after `lookAt`, because that native method changes
the orientation without recomposing the GPU view transform. Before capture it
requires actual model readiness, six vertices/indices and fresh render frames.
The observer disables only its own avatar rendering; entity rendering is intact.
The Firefox desktop window is 1280×800 at native density, avoiding fractional-DPI
window-size failures. The diagnostic world canvas and PNG remain 1024×768 at
DPR 1 in both engines; no public-world resolution setting changes.

With the managed laboratory and current gateway already running, invoke from
`browser-client` after copying the two trusted fixture sources into the reviewed
worktree:

```sh
OVERTE_LAB_BROWSER=system-chromium \
OVERTE_LAB_BROWSER_DISPLAY=:0 \
OVERTE_LAB_CHROMIUM=/tmp/overte-chromium-hardware-probe/extracted/usr/lib64/chromium-browser/chromium-browser \
OVERTE_LAB_CHROMIUM_LIBRARY_PATH=/tmp/overte-chromium-hardware-probe/extracted/usr/lib64 \
node tests/integration/native-render-state.mjs
```

For stock Firefox, set `OVERTE_LAB_BROWSER=system-firefox` and keep the display
variable. Use one GPU comparison at a time. The harness requires its own free
Vite port 5173, existing lab HTTP port 45110, native X display :95 and the private
native PulseAudio socket. It refuses an occupied Vite port, unavailable rez
permission, unavailable model/snapshot deadlines or changed source hashes. It
records failures without lowering these checks. Results and private native logs
remain in the ignored `build/browser-lab/evidence/render-state` subtree; raw logs
are not publication artifacts. This is a current-source Vite component comparison,
not production-distribution or 30-minute endurance evidence.
