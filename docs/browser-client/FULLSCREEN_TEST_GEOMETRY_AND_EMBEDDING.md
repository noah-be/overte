# Fullscreen geometry and actual embedding denial

This proposal changes test oracles and authored test fixtures only. It does not change production styles, fullscreen behavior, permissions, DPR, focus, or physical input. No browser was launched for this proposal. The corrected active four cases require fresh actual qualification.

## Why integer equality is not a correct geometry oracle

The retained stock Chromium154 original four-case report contains three passes and one failure: the fullscreen host DOMRect width was1280.4000244140625, while `innerWidth` was1280. The original report SHA is04894b7e310606e5ffa4a405e8bc88b6618c0e337eb351f7e576d0611e28ee2c. The retained measurement does not include a same-call VisualViewport or native-DPR witness. Do not retroactively mark its geometry passed.

CSSOM View exposes `innerWidth`/`innerHeight` as WebIDL long integers. Chromium154 implements them through `GetViewportSize()` and `AdjustForAbsoluteZoom::AdjustInt`. Its DOMRect path retains a `gfx::RectF` converted to double-valued DOMRect components. Exact equality between those representations is not guaranteed.

Direct exact DOMRect-to-VisualViewport comparison is also not universally correct. The pinned DOMRect path multiplies floats by a reciprocal zoom; VisualViewport width/height divides floats by zoom. A controlled source-arithmetic counterexample with internal width303 and zoom1.25 produces242.40000915527344 versus242.39999389648438. This is not evidence of those internal values in the retained browser run.

The new test creates one independent, invisible, pointer-inert reference element with fixed inset0, automatic dimensions, no padding/border/margin or transform. Its bounds come solely from authored viewport CSS, never from the fullscreen host or a measurement. Both reference and host use the same public DOMRect path. The oracle requires exact equality of all four edges and both dimensions, plus reference origin0, positive bounded dimensions, current connected fullscreen ownership, an owned reference, visible top-level document, native-density bounds, and VisualViewport scale1/offsets0. One-CSS-layout-subpixel edge or dimension changes fail; no rounding or tolerance is used. VisualViewport doubles and legacy integer sizes are separately recorded in the fixed-field `fullscreen-geometry` attachment before the assertion.

The unchanged first-case painted pixels, aspect, real Fullscreen/Exit/Escape actions, trusted canvas input, leave/rejoin and ownership cleanup remain mandatory. The unchanged small-toolbar and replacement bodies remain mandatory. Reference removal is owned by normal afterEach cleanup. No production element is styled by the geometry helper.

## Correct active denial for both stock engines

Firefox156's default native source does not enable HTTP Permissions-Policy header enforcement on the tested path. Its retained original header-negative failure remains a failure. Do not green-skip it or assign `fullscreenEnabled`.

The active third case now uses a real current cross-origin loopback child without `allow` or `allowfullscreen`. Both exact authored HTML responses must be observed once; no redirect, srcdoc, sandbox, extra service or permission attribute mutation is used. The child installs the byte-identical original authored BrowserTablet callback, waits for its real displayed-frame ACK, and requires actual capability denial, disabled production button, visible unchanged warning, painted pixels/aspect, trusted physical pointer press/release, and exact actual production input revision/frame/button/center. A separate visible authored button makes exactly one synchronous real requestFullscreen call from a trusted click. TypeError denial, visible connected target and null owner in parent/child are mandatory. Finally disposes the child and removes only its two authored routes.

This does not qualify HTTP-header support. The earlier two separate registered embedding cases already qualified real denial/delegation in stock Chrome and Firefox; they are not a substitute for running this newly active main-spec case.

## Historical source and exact attestation

The complete original53ae639c6ec16a6f57aba3ee60bf997e87589a20ec6ce50735fd3bccfb393c37 source is preserved byte-for-byte as `tests/fixtures/tablet-fullscreen-original-20261002.ts.txt`, outside the registered test glob. The CPU recovery test strips only the documented amendments and restores exactly that source, including its failed header case. It never claims the old four bodies are unchanged in the corrected active spec.

The standalone two-case embedding driver now explicitly reads the historical fixture for its unchanged original callbacks while also hash-pinning the corrected active main spec. Its report states `historicalOriginalBodiesUnchanged:true` and `activeRegisteredSpecChanged:true`. Its exact recovery control first restores the revieweda55 driver, then preserves existingc007→af12→7fa recovery assertions. All driver actions, bounds, real wire checks, screenshots, policy gates and deadlines remain unchanged. Older frozen four-case stock wrappers still pin53ae: retain them as historical records and prepare a new reviewed source binding before using them against the corrected active spec.

Focused verification:

```
node --import tsx --test --test-isolation=none tests/fullscreen-geometry.test.ts
node --test tests/integration/fullscreen-embedding-contract.test.mjs tests/integration/fullscreen-embedding-pointer-diagnostic.test.mjs
node node_modules/typescript/bin/tsc --ignoreConfig --noEmit --strict --skipLibCheck --target ES2022 --module ESNext --moduleResolution Bundler --lib ES2022,DOM,DOM.Iterable --types node tests/fullscreen-geometry.ts tests/fullscreen-geometry.test.ts tests/fullscreen-embedding-denial.ts tests/tablet-fullscreen.browser.spec.ts
```

Parent-owned live acceptance must run the corrected registered main spec under the existing original45-second case and10-second assertion bounds. Keep exact source/executable/cleanup attestations and prior failures. This packet makes no native Tablet, performance, microphone or production fullscreen quality claim.

Primary sources:

- [CSSOM View](https://www.w3.org/TR/cssom-view-1/) defines integer Window sizes and floating VisualViewport sizes.
- [Fullscreen standard UA stylesheet](https://fullscreen.spec.whatwg.org/#user-agent-level-style-sheet-defaults) establishes fixed fullscreen inset0 and full containing-block size.
- [Chromium154 Window IDL](https://github.com/chromium/chromium/blob/154.0.8037.57/third_party/blink/renderer/core/frame/window.idl#L119), [LocalDOMWindow](https://github.com/chromium/chromium/blob/154.0.8037.57/third_party/blink/renderer/core/frame/local_dom_window.cc#L1643), [AdjustForAbsoluteZoom](https://github.com/chromium/chromium/blob/154.0.8037.57/third_party/blink/renderer/core/layout/adjust_for_absolute_zoom.h#L48), [Element DOMRect](https://github.com/chromium/chromium/blob/154.0.8037.57/third_party/blink/renderer/core/dom/element.cc#L3239), [DOMRect float conversion](https://github.com/chromium/chromium/blob/154.0.8037.57/third_party/blink/renderer/core/geometry/dom_rect.cc#L21), and [VisualViewport division](https://github.com/chromium/chromium/blob/154.0.8037.57/third_party/blink/renderer/core/frame/visual_viewport.cc#L491) establish the different representations/arithmetic.
- [Firefox156 default preferences](https://hg.mozilla.org/releases/mozilla-release/raw-file/FIREFOX_156_0_RELEASE/modules/libpref/init/StaticPrefList.yaml), [Document fullscreen/feature-policy implementation](https://hg.mozilla.org/releases/mozilla-release/raw-file/FIREFOX_156_0_RELEASE/dom/base/Document.cpp), and [feature policy defaults](https://hg.mozilla.org/releases/mozilla-release/raw-file/FIREFOX_156_0_RELEASE/dom/security/featurepolicy/FeaturePolicyUtils.cpp) distinguish header support from actual nondelegated container denial.
