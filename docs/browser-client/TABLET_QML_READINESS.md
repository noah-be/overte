# Native capture QML readiness

Release2026.04.1 `QmlWindow.qml`, commit
`f91d15a08587dcd37c642234424b3215dd331724`, loads its source asynchronously.
Its `fromScript()` forwards only after `dynamicContent` exists; earlier messages
are silently dropped. The browser Tablet previously marked its first GPU grab
pending immediately after issuing capture, without proving that the capture Item
had loaded. This source path can strand the first frame; it does not establish
that every observed timeout had that cause.

The dedicated native helper now sends one fixed revision-bound readiness probe
every150ms until the actual loaded capture Item echoes its probe number. Only
then can it allocate a GPU capture. Probe retries reuse one pending number;
revocation invalidates it, and closed, mismatched or expired acknowledgements
cannot authorize a capture. There is no visitor readiness command, arbitrary
source evaluation or additional native privilege.

Probe and first draw share the existing total30-second deadline. Loading at29s
leaves1s for the first draw, rather than granting a second30s. Warm draw deadlines
remain8s. Rapid Home/back actions cannot reset the cold budget. Explicit retry
after an error or reopening a closed pre-load UI receives a fresh bounded attempt.
Existing one-grab ownership, canceled callback drainage, frame acknowledgement,
engine-thread outbox and permission guards are retained.

The JSON test fixture preserves the exact pinned native wrapper source, including
its original whitespace, SHA256
`ede803f5d3e8787febb898d1a395306b2f6f81b80ab8013034027c068a861866`.
VM tests execute its actual dispatch method plus the production QML and native
helper functions. They prove dropped initial dispatch/retry/ack, total budget,
wrong or stale acknowledgements, zero GPU allocation before readiness, retry,
close/revocation and late cold-frame refusal. These are meaningful source-level
regressions, not a claim of an actual Qt/GPU session.

The subsequent source-coherent Graphics journeys now pass in both stock engines;
see [the actual own-root capture proof](GRAPHICS_OWN_ROOT_VERIFICATION.md).
The genuine full Create editing/deletion journey remains pending. Previously generated
Create audit gateways must be recreated from the new shipping capture QML;
their existing runtime-hash attestation remains mandatory.
