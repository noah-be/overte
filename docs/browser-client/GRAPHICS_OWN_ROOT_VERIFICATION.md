# Genuine native Graphics controls with owned-root capture

Two source-coherent runs now pass the **controls and framebuffer** scope using the actual native Qt Graphics application, including its C++-created popup root:

| Browser | UTC interval on 2026-10-01 | Matched setting effects | Painted popup checks | Result |
| --- | --- | ---: | ---: | --- |
| Stock Chromium 154.0.8037.57 | 17:11:30.391–17:13:42.166 | 17 | 13 | Controls/framebuffer passed |
| Stock Firefox 156.0 | 17:22:04.676–17:24:09.971 | 17 | 13 | Controls/framebuffer passed |

The genuine sliders and switches change field of view, resolution, local lights and camera-clipping target settings. Actual painted native combo rows select 100%, 80% and 60%; the native Custom row correctly reads back 70%. Browser drawing buffers follow the changes: 1280×900 at100%, 1024×720 at80%, 768×540 at60%, and896×630 at70%. Leaving and joining again preserves the chosen70% and field-of-view130 settings; the harness restores the original100% resolution and field-of-view70 afterwards. These are explicit user actions; no default density or fluidness threshold changed.

Both reports set `completed`, `controlAcceptance`, `resolutionProfileAcceptance` and `sourceAttestation` to true. `functionalAcceptance` and `performanceAcceptance` remain false intentionally: these runs do not prove local-light pixels, constrained-camera pixels, online-world fluidness, every Tablet application, or complete native parity. Those require their separate actual acceptance tests. The tested scene receives no entity mutation, and no endurance test runs.

The reports retain matching start/end hashes for nineteen frontend/gateway/harness files and six pinned original native Settings sources. The accepted worker boundary admits only the generated Create Properties HTML to its exact reviewed installed target read-only. The earlier16:56 join refusal remains negative evidence: that exact mapping had been missing, and the guard correctly refused startup before any settings effect. Earlier15:21 and15:41 popup attempts also remain negative: the prior QML callback capture could not capture a C++-created popup root lacking a QML engine. The reviewed bounded C++ own-root capture now handles that root; no popup predicate was relaxed.

Evidence:

- [Chromium controls/framebuffer report](evidence/tablet-graphics-own-root-chromium-20261001.json).
- [Firefox controls/framebuffer report](evidence/tablet-graphics-own-root-firefox-20261001.json).
- [Retained earlier failures](evidence/tablet-graphics-own-root-retained-failures-20261001.json).
- [Supplemental retained native module audit](evidence/tablet-graphics-native-module-supplement-20261001.json). This last record is explicitly a post-run retained-module audit, not an extra start/end binary attestation. It records matching Qt5.15.3 SDK/runtime and the compiled source digest.

The portable reproducer uses the actual installed release's reviewed `defaultScripts.js` and selected stock browser resources; operator-specific absolute paths are deliberately excluded:

```sh
OVERTE_LAB_DEFAULT_SCRIPTS="$OVERTE_LAB_ROOT/appimage/squashfs-root/usr/bin/scripts/defaultScripts.js" \
  OVERTE_LAB_CHROMIUM="$OVERTE_STOCK_CHROMIUM" \
  OVERTE_LAB_CHROMIUM_LIBRARY_PATH="$OVERTE_STOCK_CHROMIUM_LIBRARY_PATH" \
  node browser-client/tests/integration/tablet-graphics.mjs

OVERTE_LAB_DEFAULT_SCRIPTS="$OVERTE_LAB_ROOT/appimage/squashfs-root/usr/bin/scripts/defaultScripts.js" \
  OVERTE_LAB_BROWSER=system-firefox \
  node browser-client/tests/integration/tablet-graphics.mjs
```

This is a portable reproduction recipe; the harness reports contain the actual timestamps, browser versions and exact source digests. Neither command introduces an automatic quality profile change.
