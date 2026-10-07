# Display-owned native tablet input

This change addresses a source-confirmed race: selecting a new native capture surface immediately changed pointer coordinates before the visitor displayed its pixels. A tablet frame is 480×706, while an associated popup can require the larger private offscreen GUI root. In-flight captures now leave input attached to the last genuinely displayed surface.

`frameAck` requires `displayed: boolean`. The browser sets it only after successful canvas drawing. Decode failures, superseded frames and the gateway's five-second backpressure release use `false`; they cannot commit an input surface. A successful acknowledgement is checked against the pending frame and active domain revision in both gateway and native helper, then reaches QML as the fixed `displayFrame` command. QML commits only a matching saved frame, retaining that capture's target, width, height, sequence and revision.

Pointer and wheel commands require the successfully displayed `frameSequence`. The gateway and QML discard another sequence rather than applying coordinates to a different GUI surface. Keyboard, committed text and clipboard operations require a committed display in QML. Permission changes, hide and teardown revoke stored surfaces. Home/back retry, original cold30-second/warm8-second capture bounds and single outstanding GPU ownership remain unchanged.

Validation:58 source/CPU contracts passed with `node --test --test-isolation=none gateway/tablet-input-surface.test.mjs gateway/tablet.test.mjs gateway/tablet-overlay.test.mjs gateway/native-tablet.test.mjs gateway/native-tablet-readiness.test.mjs gateway/tablet-qml.test.mjs tests/integration/tablet-popup-audit.test.mjs tests/integration/tablet-create-readiness.test.mjs`. This includes actual production helper/QML functions, real private PNG files, malformed wire fields and automatic release. The first combined run lacked an unchanged pinned fixture in the isolated test copy; after copying it, all58 passed. This original component checkpoint did not establish a live popup. The later
[owned-root native Graphics proof](GRAPHICS_OWN_ROOT_VERIFICATION.md) now verifies
actual painted popup rows and setting effects in both stock engines.

The diagnostic instrumenters are updated only for the revised capture entry; they keep passive fixed queries, bounded private logs and no visitor-supplied evaluation. Integration observers must record only `displayed === true` acknowledgements as actually drawn frames. A Node-only PNG observer must release with `displayed: false`.

The subsequent integrated correction adds a trusted navigation sequence for
Open/Home/Back/Close. Frames, acknowledgements and native input must belong to
that current view; pending bitmap completion and delayed old frames cannot
restore the previous surface. First authority establishment retains an already
requested Open, while later authority replacement clears the old view. A held
pointer retains its original displayed-frame coordinates, button and bounds
through later frames/resizes, then releases or cancels once. Native QML retains
the same original pressed item until that matching release.

Fifty-five focused CPU cases pass. All 26 actual canvas/navigation cases pass in
Chromium and Firefox as part of the 30-case consolidated graphics run. The
lost-capture test uses genuine trusted pointer events to establish and release
capture before checking one native cancellation; the initial two fixture
failures and traces remain preserved. The separate genuine Snap cases passed
in that earlier combined run. Native popup settings and persistence are still
tested independently. [Source-bound run](evidence/graphics-warmup-gpu-20261001.json).
