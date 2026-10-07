# Actual browser focus in the native PTT acceptance harness

Substantial AI assistance was used. Production PTT remains unintegrated while
its complete genuine acceptance is pending. These changes affect only the
owned test browser; microphone permission, native audio and input are unchanged.

In the exact stock Chromium visibility attempt, the authored second-page
foreground operation returns, but the first document remains visible and
focused. Neither original blur/hidden counter increases. The unchanged
10-second predicate therefore correctly refuses. Both synthetic voice directions
pass before this refusal. Firefox has previously passed the actual visibility
stage; its later and most recent control-frame refusals remain recorded.

The installed Playwright 1.63.0 main-frame initialization explicitly enables
`Emulation.setFocusEmulationEnabled`. The
[official Chrome protocol](https://chromedevtools.github.io/devtools-protocol/tot/Emulation/#method-setFocusEmulationEnabled)
defines that operation as focus/activity simulation. This source fact is relevant
to the fixture and does not establish the actual browser window topology.

The first narrow correction sends only `enabled: false` on a separate context-owned
Chromium CDP session for each of the two owned pages. Firefox uses its original
BiDi page behavior and receives no CDP operation. Unsupported engines or a failed
command refuse; no focus/visibility event or key is synthesized, no counter or
native value is edited, and every original physical switch, release, PCM,
deadline and cleanup assertion remains. The successful session lives with its
existing context. No browser target ID or native window query is collected.

The actual Chromium retry still remains visibly focused with zero blur/hidden
events. Removing an override on a separate agent has therefore not qualified
the fixture. An independent source review is examining the original driver's
focus override ownership and an actual unemulated launch. Do not describe this
first correction as a resolved visibility bug or production success.

All 75 focused CPU contracts pass after updating the extracted harness-body
fixture for the newly required context/report prerequisites. Its initial missing
report failure is retained separately. Root launched the first actual retry
before that fixture correction was verified; the actual result is preserved
as a negative, not accepted as a complete passing cohort. Neither CPU result
proves GUI events or a physical microphone.
