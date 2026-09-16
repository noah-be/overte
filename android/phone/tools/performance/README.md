# Phone performance consumer (PH-005)

Pinned source: SH-008 analyzer v001 plus promoted fixture v002, and SH-009 v001.
Fixture v002 digest:
`88d94ad1936dd68deeedd9e91f0bb0170621ff69e6ce70c39580c901e679062b`.
Earlier fixture trace/budget identities cannot be relabeled as v002 observations.

Run `python3 android/phone/tools/performance/analyze.py` with `--trace`,
`--artifact`, `--expected-source-sha`, `--expected-artifact-sha256` and
`--expected-fixture-sha256`. The expected identities come from the independently
frozen candidate/run inputs, not the trace being checked. The fixture digest is
the exact Shared `tests/performance/schema/reference-fixture.json` digest, not
the scene digest. Original SH-009 hashes the supplied artifact bytes; original
SH-008 validates the trace, pinned to `android-phone`. No schema is duplicated.

Optional `--budget` requires `--expected-budget-sha256` from separately approved
frozen inputs. Do not use the received budget's own hash as approval. No production
budget is provided by this Phone lane. Without budgets the output is
`METRICS_BOUND_BUDGETS_PENDING`; successful budget checks remain
`BUDGETS_CHECKED_NOT_NODE_ACCEPTED`. Symlinked inputs, reused inodes and duplicate
CLI options fail. Diagnostics never echo paths, trace content or exception text.

SH-008 v001 requires actual frame-window p95, consistent Android total PSS or RSS
(never relabeled physical footprint), thermal and observed black-frame count.
It enforces the 60-minute trace and 30-minute checkpoint with bounded sampling
gaps, STOP conditions and serious-thermal reduced-mode observations. Device
battery percentage is not process energy; process energy remains unavailable.
Source fixture identity is not representative-load qualification.

This is an offline consumer, not a native trace producer or authorization to run
an endurance test. Candidate signature/install identity, authenticated measurement
producers, execution of the reference scene, actual observation accuracy, approved
budgets and PH-004's two complementary GPU/page-size physical targets plus repeated
runs remain required. No local trace can establish these facts. The unit tests use
explicitly synthetic candidate bytes and traces and do not claim hardware evidence.

Focused check:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s android/phone/tests/performance -p test_analyze.py
```

Import all versioned SH-008 reference-fixture prerequisites before conformance;
a source mismatch must be repaired by a General release, never a changed expected
hash or disabled fixture verification in Phone.
