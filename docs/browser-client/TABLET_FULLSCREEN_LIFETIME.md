# Independent fullscreen review and same-target lifetime amendment

This packet reviews frozen proposal `89976fb5e34f7f9fe849045dcba2259f63e84ccfd45654d2555ca8f3106a2648`. The original packet and Root sources remain unchanged. Only source reads, narrowly scoped Node tests and a targeted TypeScript check were performed. No browser, native Interface, GPU, service, system or Git operation was launched.

## Concrete defects

1. Original `src/fullscreen.ts:38–39,84,93` transfers the lease owner when a same-target replacement is constructed, but leaves established ownership on the old controller. Disposing the old controller then disconnecting/disposing its replacement cannot release the established fullscreen.
2. A disposed controller's pending enter can complete after a replacement is already disposed. The original callback cannot assign ownership to the replacement or release it, leaving the target fullscreen with no live owner.
3. The same pending completion clears shared `busy` without publishing to the live replacement. If the platform change event precedes promise completion, the replacement's button stays disabled despite an actually completed operation.
4. Availability does not verify that the target still belongs to the captured document. A DOM-adopted connected target could request another context's fullscreen while the controller observes the old document. The amendment refuses before the API call.

The additive tests against the byte-identical original module produce **12 PASS / 5 FAIL**, including four replacement failures and the document-affinity refusal. The candidate produces **17 PASS / 0 FAIL**. All original eleven contracts remain unchanged. Tests use authored platform boundary objects; they are not actual browser acceptance.

The amendment stores owned state and current connection on the existing per-target lease. A retired callback can notify the current observer and release a late enter only when the replacement is disconnected. The current controller inherits cleanup of established ownership; obsolete controllers cannot clear its connection. Disposal removes the lease's UI observer, and asynchronous cleanup captures only the document/target/lease rather than a disposed Tablet observer. Actual foreign fullscreen readback still refuses cleanup. Trusted-click invocation, no native command, original eight-second confirmation wait, platform promise consumption, and normal Tablet navigation/input are unchanged.

## Reviewed safe paths and limits

The API call occurs synchronously before any await, which preserves the browser's activation boundary. Actual `fullscreenElement` readback controls acknowledgement. Unsupported, denied, synthetic and foreign-element requests refuse. No keyboard lock, display enumeration, renderer/DPR/quality mutation, asset request or native schema change is introduced. Root `main.ts` constructs the Tablet with the existing application container; its normal reset disposes the Tablet. The only current `Object.create(BrowserTablet.prototype)` CPU fixture executes `send`, not the newly initialized fullscreen methods, so no missing-constructor dependency was found.

The browser-owned button does not exercise native fullscreen-display selection. Native capture canvas aspect and frame-bound input remain governed by existing code. Actual native Tablet input/painted-control acceptance must still be run after integration.

The per-target lease does not serialize unrelated target controllers in one document, nor coordinate uncontrolled third-party fullscreen calls. The foreign guard verifies the actual element before requesting exit and before cleanup; it cannot cancel a platform operation once submitted. The supplied stock fixtures cover the real single application target. A never-settling browser promise remains conservatively pending; replacing an already-pending controller does not make the underlying API cancellable. These limits should remain explicit instead of claiming global document exclusivity or guaranteed cancellation of platform UI.

The [WHATWG Fullscreen standard](https://fullscreen.spec.whatwg.org/) requires transient activation at request time and specifies asynchronous continuation and actual fullscreen-element readback. Fullscreen changes may also be ended by the browser/user. The controller therefore keeps real API calls and events, with no simulated Escape or browser-security override. Source review was performed on 2026-10-02.

## Source-only integration and parent qualification

Apply the original Tablet patch/new module, then `followup.patch`; only the three manifest-listed source/test files are amended. The original `src/tablet.ts` after-hash stays `21a7149bc0b61da0f8f24f7edcc7ebb4dbe4b7ef302c159cc31967c96f02419a`.

The original three registered browser bodies are byte-preserved. A fourth registered body uses a genuine trusted enter, constructs a same-container Tablet replacement, retires the old Tablet, then checks real disconnect cleanup. The parent must execute all four unchanged registered bodies with actual stock Chromium 154 and Firefox 156, normal security, fresh contexts, actual API activation and owned cleanup. No browser result is asserted here. Then qualify a genuine native Tablet journey; authored PNG canvas pixels are not native UI evidence.

CPU command from either owned candidate/base directory:

```sh
node --import tsx --test --test-concurrency=2 tests/fullscreen.test.ts
```

Targeted typecheck of the amended module, all CPU contracts and the registered browser fixture passed. No production build or full project rerun was performed in this followup. The original proposal's full-project typecheck is separate recorded evidence.

The loading-residence measurement packet is unchanged and unrelated.
