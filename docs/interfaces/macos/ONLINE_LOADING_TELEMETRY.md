# macOS online-loading telemetry

The online-loading benchmark assigns every cold or warm process one navigation ID. The ID has the form
`c<concurrency>-p<pair>-<cache-mode>` and is meaningful only inside that benchmark artifact. The runner also supplies the
SHA-256 identity already stored in `online-loading-manifest.json`. Interface enables the telemetry only when all of the
following are true:

- an explicit `--testScript` is active;
- `OVERTE_MACOS_ONLINE_LOADING_NAVIGATION_ID` is a lowercase, bounded identifier;
- `OVERTE_MACOS_ONLINE_LOADING_LOCATION_SHA256` is exactly 64 lowercase hexadecimal characters.

Every process first loads the local `serverless-render.json` fixture. The test waits for all three fixture entities, empty
resource queues, and a new display present. Only then does `Test.beginOnlineLoadingNavigation()` validate the bounded
`hifi` target supplied in `OVERTE_MACOS_ONLINE_LOADING_TARGET_URL`, compare the SHA-256 of its exact UTF-8 bytes with the
manifest identity, record `url_accepted`, and queue the address lookup on `AddressManager`'s thread. The target value is
never returned to JavaScript or written to diagnostics. Repeated begin requests do not trigger another lookup.

Invalid configuration fails closed. No URL, host, entity or node UUID, compiler argument, environment dump, token, or
signing value is included in a telemetry record. Event-specific fields are integers only.

## Event contract

Each line starts with `OVERTE_MACOS_ONLINE_NAV` followed by one compact JSON object. `monotonic_us` uses
`std::chrono::steady_clock`; it is not a wall-clock timestamp. Events are emitted once per navigation and must form this
contiguous order:

1. `url_accepted`
2. `domain_connected`
3. `entity_server_active`
4. `entity_query`
5. `entity_data`
6. `entity_decode` — packet decompression has completed, immediately before tree mutation
7. `entity_tree`
8. `render_handoff` — first domain entity accepted by the render scene; includes additive attribution for the full
   `entity_tree`-to-handoff interval
9. `first_presented`
10. `first_visible`

`first_presented` means that a new OpenGL frame was executed and swapped after a domain entity entered the render scene.
`first_visible` is later: the benchmark observed at least one visible render-affecting entity and then observed another
display present. The deterministic screenshot remains the pixel-level evidence; neither an entity property nor the old
process-wide `OVERTE_MACOS_ENTITY_GATE` marker is treated as proof of visibility.

The JSON validator retains only these nonnegative numeric details: resource loading/pending counts at server activation
and query, query/data byte counts, packet queue depth, decompression/lock/tree time in microseconds, decoded entity/element
counts, render add/update queue depths, and present/visible counts. The render handoff additionally records
`tree_to_add_slot_us`, `add_slot_to_pending_pass_us`, `pending_pass_to_handoff_us`, `adding_slots`, cumulative synchronous
`preload_us`, `add_passes`, and `parent_incomplete_skips`. The first three intervals must add up exactly to the measured
`entity_tree`-to-handoff interval; the analyzer rejects missing or inconsistent attribution. These values are exposed in
the analysis as `navigation_event_details` and as millisecond queue diagnostics; arbitrary keys and all string details are
rejected.

`preload_us` is the cumulative synchronous `checkAndCallPreload()` time on the EntityTreeRenderer thread. With one add
pass it is wholly contained in `add_slot_to_pending_pass_us`, and the analyzer validates that bound. With multiple add
passes, additional queued add slots and their preload work may occur after the first pending pass, so the cumulative value
may legitimately exceed that first interval; it remains contained in the overall first-add-slot-to-handoff window.

Immediately after the validated `first_visible` event, the script synchronously writes the immutable one-shot
`macos-online-loading-checkpoint.json`. This is not the supervisor's completion file and therefore cannot stop the process
before the screenshot/idle observation finishes. The final result remains `macos-online-loading.json`. Both carry the same
`navigation_id` and sanitized location digest. Their 500 ms
queue samples cover active and pending downloads, active and pending processing, pending texture transfers, entity counts,
and display rates. `analyze-online-loading.py` rejects another navigation ID, another location identity, duplicate or
out-of-order events, non-monotonic timestamps, and a successful result with an incomplete event sequence. It also requires
the Core and JavaScript `first_visible` clocks to agree within the fixed 500 ms polling interval plus 250 ms scheduling
allowance. This fail-closed check prevents application startup from being mistaken for navigation time.

On a hosted diagnostic runner only, a signal exit may use a validated primary first-visible checkpoint or a validated final
LLDB retry result. The selected evidence must have the exact attempt identity and digest, the complete ordered navigation
sequence through `first_visible`, matching log/process evidence, and a visible entity. The original signal status remains a
failed/incomplete attempt and is counted as a crash; this evidence can only satisfy the bounded diagnostic capture/skip gate.
It cannot satisfy native-hardware acceptance, make `measurement_passed` true, or select a production concurrency. A crash
before visibility, a malformed/partial checkpoint, a missing event, or any identity mismatch remains a hard failure.

## Scope and limitations

This is additive test instrumentation, not a production analytics channel. It intentionally measures **ready application
to online world**, not cold process startup, and does not copy the Pico loading state machine. Cold startup remains a
separate benchmark. The first presented frame is correlated with render handoff and a later visible-entity observation,
but it does not identify a particular mesh draw call. A future deterministic-domain fixture can strengthen that last
association without changing the navigation identity or event format.
