# Explicit browser graphics scan and correlated Settings confirmation

This packet is an unintegrated proposal. Its 41 CPU contracts and whole-project TypeScript check pass. The two registered browser tests and genuine native/stock-browser acceptance below are prepared but have not run for this packet. No performance improvement or globally optimal settings are claimed.

## Effective scope

The visible wrapping BrowserTablet toolbar gets Scan and Apply buttons. Scan closes the native Tablet presentation so the existing local WebGL World becomes visible. Only successful calls to the existing World animation render branch publish observations. Snapshot renders, hidden presentation, plain animation callbacks and extra renderers do not publish samples. On a same-generation non-cancelled result the Tablet reopens Home; the previous native Settings page is not restored. The result remains in the browser toolbar.

The capability snapshot records actual WebGL2, context antialias, fixed numeric dimensions and drawing-buffer size at sample start. It does not query renderer/vendor names, account information, assets or participant identifiers. Current-scene pacing is a separate two-second observation, at most 512 frame intervals with a five-second owned wait. Active model jobs or shader compilation, hidden presentation, malformed timings, connection/revision changes, cancellation and context loss refuse or end the observation. Model-jobs-idle is not complete asset readiness: independent Image entities, material assets and texture dependencies may still arrive during the sampled view. There is one observer per World and no recurring background benchmark or network/asset work.

The recommendation always keeps current settings by default. Only if the sampled view is below 30 Hz or its p95 interval exceeds 50 ms is one optional ten percentage-point resolution reduction offered, with a 10% lower bound. It expires after 30 seconds or a setting/authority change. The message explains that reduced pixel work may not help CPU limitations. FOV, local lights and clipping remain genuine existing native Settings controls; this scan does not change them or pretend that two seconds describe every world or hardware performance.

## Ordinary graphics route, with a correlated completion

Apply is a separate explicit browser button click. Scan is disabled while that confirmation is pending, and the scanner itself refuses a second observation until the original Apply settles. Cancelling an owner cannot truthfully claim that an earlier user-authorized change was never applied; readback may already have occurred before its ACK. It sends a bounded `graphicsChange` intent for resolution only through the authenticated Tablet session, existing command sequence and exact current permission revision. It does not call World.apply. The native version-matched graphics adapter creates its ordinary `kind:graphics` request with its own monotonic request ID and a bounded browser intent tag. The existing BrowserGraphicsController validates and applies it to the effective target, reads actual settings, persists through the existing callback and returns its ordinary correlated `graphicsResult` ACK.

Only after accepting that exact ACK does the native adapter update its cached Settings state/profile and send `graphicsApplied`. The browser completes Apply only when that confirmation, the current effective target and the exact requested four-field settings agree. The fresh native cache therefore precedes success. Existing untagged native slider, combo and switch requests are unchanged. The existing six installed-source hashes and generated Settings widgets remain unchanged; the new completion adds no native Render, Performance or LOD writes.

One browser intent and one native request can be pending. A native request already in flight refuses the new suggestion explicitly. Replay, wrong tag, late ACK, wrong revision, missing approval, malformed values and closed ownership fail closed. Cancellation clears the browser's pending tag before sending a validated matching `graphicsCancel`; queued tagged requests cannot apply afterward. Tab hiding, leave and permission changes cancel pending intent and release owned timers/listeners. A setting already applied before cancellation is not silently reverted: the user is told to check effective settings. A persistence failure remains the existing ordinary ACK/native Settings warning, rather than a claim that saving succeeded.

## Review and integration

Apply the single narrow `integration.patch` only after verifying every before hash in manifest.json. Add the new files from `files/`; do not copy the entire candidate World/main. The patch is based on World 9881, Main c263 (slot ledger plus production push-to-talk), Tablet 21a (reviewed fullscreen) and native Tablet 6e8. It preserves their hooks and cleanup. No changes to server, native-bridge, audio, PTT, fullscreen implementation, installed native source files, rendering options or resource limits are proposed.

Rebuild the client and restart only the owned gateway under the established laboratory manager so its startup-cached native helper bytes and new modules are coherent. Use a fresh worker. Existing graphics protocol version 1 and unchanged four-field settings are retained; browser intent tags/completion and cancel are explicitly validated addon messages, not unsolicited ACKs. New tests are collected by the existing npm test and Playwright `*.browser.spec.ts` configuration in both projects. There are no new dependencies or test skips.

Focused CPU validation from browser-client:

```sh
./node_modules/.bin/tsx --test tests/graphics-environment-route.test.mjs tests/graphics-environment-scan.test.ts tests/world-graphics-scan.test.ts gateway/browser-graphics.test.mjs
./node_modules/.bin/tsc --noEmit
```

Prepared renderer/DOM tests, with a distinct ignored output directory:

```sh
npm run test:browser -- graphics-environment-scan.browser.spec.ts --output build/graphics-scan-browser-results
```

The first test reads real World-rendered pixels and verifies real completed observations without altering quality. The second uses an authored protocol state to qualify the browser-owned toolbar at 375 pixels, closes and returns its presentation around actual World renders, and preserves fullscreen/quality. This DOM scaffold does not claim a native Qt frame, native GUI confirmation or stock-browser acceptance.

## Required genuine native/stock-browser qualification

Root alone runs the following with the same bounded native UI geometry/popup calibration and source attestation used by `tests/integration/tablet-graphics.mjs`, first on stock Chromium 154, then stock Firefox 156. Keep the native microphone muted; use the owned managed domain, fresh profiles and unchanged rights. Pin new scanner/intent/shared/helper modules along with the existing controller, gateway, World/main, generated native Settings sources and actual production bundle. Preserve evidence for failures and verify source hashes and cleanup after each attempt.

1. Complete the unchanged native Graphics slider/switch/profile/persistence journey. Open its genuine native Graphics page, record the actual effective settings/framebuffer and native frame. Click the browser toolbar Scan button with normal trusted pointer input. Require Tablet hidden during sampling, successful actual visible World frames, no graphicsChange/graphicsResult caused by Scan, and unchanged settings/framebuffer after the result.
2. Require the toolbar result to distinguish WebGL environment dimensions from measured current-view cadence and to recommend keeping settings. Require the same session to return Home with an actual fresh painted native frame. Manually opening Tablet early cancels a sample and cannot later force it open.
3. In a view that genuinely meets the slow-sample rule, click its optional Apply button. Record only bounded public settings/request metadata: exact browser intent ID, ordinary native graphics request ID/revision, existing graphicsResult ACK and later graphicsApplied with matching tag/revision/settings. Require one real effective framebuffer resize, ordinary persistence, fresh native cached settings, no success before the completion and no change to the other three fields. If the actual scene does not meet the rule, require Apply disabled; do not synthesize timestamps or manufacture a suggestion. That result does not qualify the optional-Apply GUI path.
4. Navigate by genuine native pointer input back to Settings/Graphics. Use the existing painted native widget and popup calibration: require a fresh native slider frame and the actual confirmed profile row (Default/Balanced/Faster/Custom) to match the completed value. This painted readback is required in addition to the DTO confirmation. Leave/rejoin and repeat the genuine native readback to verify ordinary persistence.
5. Start a new scan and hide the browser tab, leave or rejoin. Require prompt bounded cancellation, released source/listeners, no late return to Tablet and no old suggestion applying in the fresh session. Ordinary native Graphics controls must still pass unchanged after scanning. Reconfirm PTT release on opening the Tablet and fullscreen operation; these existing callbacks are retained, not replaced.

No real GUI, native cached-state pixels, mic behavior, GPU speed or hardware-optimal-setting claim is authorized by the CPU tests alone. Real renderer coverage and these native/stock paths remain pending.

## Primary sources

The exact installed native f91 source/version and existing generated widget source hashes are reviewed by `gateway/browser-graphics-overrides.mjs` and the original 11 graphics contracts. The current World renderer and ordinary BrowserGraphicsController are the integration source of truth; tests exercise their production methods rather than substitutes.

The WebGL capability/actual drawing-buffer semantics come from the [Khronos WebGL2 specification](https://registry.khronos.org/webgl/specs/latest/2.0/), consulted 2026-10-02 (the latest page is an editor's draft), and [Three WebGLRenderer documentation](https://threejs.org/docs/#WebGLRenderer), with installed Three 0.186.1 source. Visibility cancellation follows the [WHATWG HTML page visibility specification](https://html.spec.whatwg.org/multipage/interaction.html#page-visibility). These sources provide no promise that a short scene sample predicts hardware performance or globally optimal options.
