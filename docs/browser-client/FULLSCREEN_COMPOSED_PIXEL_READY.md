# Additional composed-pixel setup qualification for owned iframe input

The original passive Chromium failure is retained. Its real trusted press/release targeted the parent iframe, with no child event and no production wire; the negative case's child input worked. This observation establishes where the event stopped. It does not identify a compositor, permissions, product pointer handler or Puppeteer defect.

This separate fixture amendment requires one public screenshot of the current owned canvas before the unchanged first physical click. It qualifies actual composed center pixels, not just canvas.getImageData and a draw ACK. It then preserves the original click coordinates and the entire original press/release/policy/fullscreen/pixel/cleanup oracle. No click retry, synthetic event, focus/style/scroll change, native scene, permissions bypass or deadline extension is added. The original four registered test bodies remain byte-identical and are not claimed executed by these additional embedding cases.

## Primary implementation boundaries

Installed Puppeteer Core 25.12.0 `src/api/ElementHandle.ts` SHA-256 `50b86666e922010f2d247e0229eae325eeb23addf832b62a1e4917089f6801db` exposes `scrollIntoView` for element screenshots and calls the owning page screenshot with the measured element clip. `scrollIntoView:false` bypasses its scrolling branch. `captureBeyondViewport:false` keeps the capture inside the actual viewport; `fromSurface:true` selects compositor output. `omitBackground:false` preserves the background. No fullPage or viewport/device-scale option is supplied. Installed `src/cdp/Page.ts` obtains the native visual viewport and uses `Page.captureScreenshot`; the omitted-background emulation path is not selected. These source checks use the actual installed package, not an adapter that manufactures success.

Official API: https://pptr.dev/api/puppeteer.elementhandle.screenshot . Chromium's primary HitTestRegion flags distinguish child surfaces and inactive/not-submitted hit-test data: https://raw.githubusercontent.com/chromium/chromium/main/components/viz/common/hit_test/hit_test_region_list.h . This latter main-branch source is architecture context, not an assertion that the exact stock 154 binary has a named bug. A screenshot can qualify composed output but does not independently prove that the input hit-test tree is ready.

## Ownership, bounds and exact oracle

Before and after capture, a read-only actual element callback requires the same current connected canvas/host, visible document, positive unchanged native DPR, exact initial frame/revision/navigation ACK, and unchanged bounds. The canvas must already fit the viewport. No scrolling is performed. Bounds permit at most 4096 by 4096 physical extents and 4 MiPixels; compressed PNG is at most 4 MiB.

The Node-only fixture PNG decoder validates signature, chunk ranges/CRC, one IHDR, contiguous IDAT, final IEND, critical chunk allowlist, 8-bit RGB/RGBA, no interlace, dimensions and exact bounded inflated length. All five PNG row filters are reconstructed using two scanline buffers. Only center RGBA is retained. Its value must be exactly the original authored `[40,80,100,255]`. PNG semantics: https://www.w3.org/TR/png/#9Filters . No image data is re-authored, no profile/color setting changes, and no tolerant or alternative expected pixel is introduced. This narrow decoder is for genuine browser screenshot output, not a new product image loader.

The added setup operation has a ten-second bound inside the unchanged 45-second case. Timeout consumes the pending screenshot result/rejection; after expiry it performs no later decoding or readback and never clicks. The original context/browser cleanup still owns pending browser resources. A successful screenshot sets `hitTargetQualified:false`; the existing actual child pointer and production wire checks must subsequently succeed.

## Root-owned invocation

Run the amended `fullscreen-embedding-stock.mjs` with the exact same explicit shipping source, owned Vite URL, stock browser executable, headed DISPLAY and new private output child directory as the original two-case driver. Root alone owns the live browser/context, mapped executable checks, service/launcher and cleanup. The packet node_modules link uses the existing Root dependencies; there is no new dependency or package install. The driver strips exactly to passive diagnostic source `af12ccf3f6e6dc3094ea418b2a796efb3a83358552afa6631192663c46bf110a`. No production source is changed.

CPU invocation (nine controls passed after the exclusive Hub reservation ended, 129.647389 ms):

```sh
node --test browser-client/tests/integration/fullscreen-embedding-composed-ready.test.mjs
```

The controls cover exact actual callback projection, old CPU-only-versus-blank-composed counterfactual, all RGB/RGBA filter kinds, corrupt/oversized PNG refusal, owner/viewport/frame/quality refusal, single public no-scroll capture, unchanged readback, original error propagation, late-expiry disposal, and exact driver action/assertion preservation. No actual browser/GPU execution or success claim belongs to preparation.
