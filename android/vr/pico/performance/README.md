# Pico PI-006 Shared performance consumer

The existing power-report tool has an explicit retained-parity path:

```sh
python3 android/vr/pico/tools/analyze-pico4-power.py --parity \
  --trace TRACE.json --expected-source-sha SOURCE_SHA40 \
  --expected-artifact-sha256 ARTIFACT_SHA256 \
  --expected-fixture-sha256 FROZEN_FIXTURE_SHA256
```

The equivalent standalone entry is `android/vr/pico/performance/analyze.py`.
Both invoke the original `tests/performance/schema/metrics.py::validate` with
platform fixed to pico4. The schema, fixture, duration, gap, thermal/black-frame
stop and budget rules are General sh008-performance/v001, source
5930a21b68ec0ed2d86fe3c420a7244a330249f9, release manifest
ca53fddbdf16ffdb48ecb2298f3e6ebd260d9be413d09904bee9c9cc579cad96.
The fixture binding migrates to sh008-performance/v002, source
0804dac978df3dd63321d98ed33802da9f6f9c79, manifest
38def334f05daf1d9b6c958d034d0b08010f28ef98a9198e853264af1b6e45cc.
Its independently frozen reference-fixture.json SHA256 is
88d94ad1936dd68deeedd9e91f0bb0170621ff69e6ce70c39580c901e679062b.
The promoted eight-second tone is retained; the older v001 two-second identity
is rejected, not silently relabeled. No real traces were generated in this work.
There is no Pico schema clone, device execution or automatic budget approval.

Supply a budget only with both `--budget BUDGET.json` and independently frozen
`--expected-budget-sha256 SHA256`. Do not compute approval from the received
budget itself. Without it, status is METRICS_BOUND_BUDGETS_PENDING; with it,
the strongest result is BUDGETS_CHECKED_NOT_NODE_ACCEPTED. Critical thermal,
observed black frames and stopped runs retain closed STOP diagnostics. Other
failures emit only PICO_METRICS_REJECTED, not raw paths, arguments or values.

The source fixture is a bounded baseline, not a qualified representative world.
Its manifest and generated tone must match the exact published source release;
an older source fixture is not accepted just because its scene name is the same.

Existing `pico4-power-test.sh` CSV contains coarse device battery/thermal data,
wall-clock timestamps and private context. Its legacy report remains exploratory
and is NOT this retained parity format. It lacks measured windowed frame p95,
process PSS/RSS, black-frame observation and a real named checkpoint. Passing
that CSV as a parity trace fails. Neither a refresh target nor battery percentage
can fill those missing fields; device energy estimates are not process joules.
No new instrumentation or run is silently triggered by either analyzer entry.

Real trace production/measurement accuracy, authenticated producer, actual
installed candidate and representative scene, Pico comfort-preserving reduced
mode, approved budgets, GPU/page-size criteria, authorized 60-minute endurance
and 30-minute checkpoint, repeats and upstream acceptance remain pending.
The iOS native publisher's 15/30-Hz caps are never applied to the Pico HMD.
