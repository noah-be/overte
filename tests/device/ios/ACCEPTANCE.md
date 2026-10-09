<!-- Copyright 2026 Overte e.V. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Physical iOS acceptance observations

`acceptance_observation.js` observes the real renderer's `Stats.newStats`,
the physical iOS audio adapter, loaded scene identities, avatar/camera state,
window dimensions and tablet visibility. It does not create audio, override
input, move the avatar, modify settings or manufacture OS lifecycle events.
An owning device runner supplies a fresh `OVERTE_ACCEPTANCE_RUN.id` matching
`output-[0-9a-f]{32}` and launches the installed E2E client with `--testScript`
and its existing dedicated `--testResultsLocation`. The observer stops after
70 minutes and releases its renderer handler and timer when its script ends.

`acceptance_evidence.py` rejects stale or mismatched runs, absent physical
observations, frozen rendering, replaced local scene identities, restarted
processes, incomplete monitoring intervals, invalid thermal readings and
sustained memory growth. The stability interval is at least 1,800 seconds with
observations from its start and end, gaps no larger than 45 seconds, advancing
script and render sequences, one unchanged OS process identity and real memory
and thermal samples throughout. The final five-minute footprint median must
not exceed the five-to-ten-minute median by more than 128 MiB or 10%. This
bounded-session rule does not prove the absence of every memory leak.

The local laboratory owns authenticated Wi-Fi transport and native XCTest/DVT
observations. Physical memory samples come from PID-matched Instruments
Sysmontap `physFootprint`; system thermal state comes from
`NSProcessInfo.processInfo.thermalState` through the existing WDA endpoint.
Raw observations, device selectors, app paths and scene UUIDs stay private.
Publish only sanitized counts, durations, scalar measurements and hashes.

Bind results to the exact producer source, IPA hash, installation receipt and
observed app version. A successful build or host fixture is not device evidence.
Do not combine process lifetimes or silently replace a pinned milestone
candidate. USB installation is followed by an authenticated Wi-Fi check before
device tests. If microphone authorization is reset, answer and close the OS
dialog before proceeding. Internal output at volume zero uses the separate
[output workflow](AUDIO_OUTPUT.md); it does not measure emitted speaker sound.

Run the regression checks with:

```sh
python3 tests/run-unittest-suite.py tests/device/self_tests --pattern test_ios_acceptance_evidence.py
```
