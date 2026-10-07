> Runtime integration checkpoint: main.ts now instantiates this adapter and provides
> its lazy approved factory to BrowserWorld. The 467-test component suite, all106
> browser cases and34repository checks passed. Real Hub timing and refreshed
> current shared-native acceptance are recorded separately. Historical prototype
> statements below describe the independent pre-integration proof scope.

# Compressed color session authority proposal

This standalone adapter is not wired into `main.ts` or `BrowserWorld`. It adds no native permissions and does not replace the existing asset path. GPU equivalence, controlled original-image fallback and a cold-world loading comparison must precede a runtime switch.

`CompressedColorSession` subclasses the existing `BrowserSession`. It preserves that class's WebSocket generation checks and normal join/leave flow. Its wrapped callbacks revoke compressed cache approval synchronously before forwarding connecting, disconnected, error or transport-failure notices. `leave()` revokes before sending Leave or closing the socket. A parsed connected state must carry both the bound session ID and a positive safe-integer permission revision; missing metadata or an unexpected session change fails closed through the existing application protocol-error teardown.

The main UI's `permissionRevision` is also used for Tablet/history state. That variable is not an independent compressed-asset grant. This adapter accepts approval only from the connected state, ignores Tablet revision changes, and creates a new local approval epoch after reconnect even when the reported revision repeats. Duplicate connected notices for the same active approval are idempotent.

The proposed lazy world API is:

```ts
const session = new CompressedColorSession(callbacks);
// The world supplies its actual renderer capabilities and its existing lifetime signal.
const colors = session.compressedColors(capabilities, worldSignal);
const texture = await colors.load(originalKtxURL, {signal: modelSignal, sampler});
```

The cache factory requires a current connected approval. It constructs only `/api/assets/<capturedSessionId>?url=<original>` on the actual browser origin. Its authority callback captures the session ID, socket epoch and approval epoch/revision, and compares them before any reader release. It never substitutes a current mutable session ID into an old cache. Cookies still pass through the existing gateway asset checks; the client callback is a revocation boundary, not server authentication.

One active world signal owns one cache. Disposing that world closes it, and a different still-live world cannot borrow it. A session transition closes the cache and rejects its readers before UI callbacks. A retired cache with pending download or ready-hit readers remains owned until its actual statistics are idle. Replacement allocation is refused during that interval, preserving the two-download bound even if a test fetch cannot be cancelled. There is no extended timeout, background polling loop or automatic PNG fallback to conceal revocation. Future loading integration must handle this explicit settling state without exceeding the existing deadline.

Five component scenarios exercise the actual `BrowserSession` methods and event parsing with an external WebSocket-event fixture and real cache promises/streams: connected-only approval, exact owned asset routes, Leave before transport sends, old socket isolation across a fresh domain join, denied/transient state revocation, repeated-revision reapproval without old byte reuse, retired request ownership, and protocol/missing-authority refusal. They do not establish real server authentication, domain compatibility or a world rendering result.

```sh
cd browser-client
node --import tsx --test --test-isolation=none src/compressed-color-session.test.ts
node node_modules/typescript/bin/tsc --noEmit
```

The source proposal deliberately leaves baseline `BrowserSession`, `main.ts`, packet validation and `BrowserWorld` unchanged. Its tests use the same session source SHA as the reviewed topic snapshot. A later integration must preserve existing model-generation checks: a texture already delivered before revocation remains model-owned until normal model/world disposal and must not be attached by an obsolete asynchronous model job.
