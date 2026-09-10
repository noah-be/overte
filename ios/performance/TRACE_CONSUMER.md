# IO-008 original Shared performance consumer

verify_trace.py consumes two explicitly pinned immutable releases: SH-008
performance v001 supplies the original analyzer; v002 supplies the complete
promoted eight-second-tone fixture. Pass both --shared-contract-root (v001) and
--fixture-contract-root (v002), plus the actual trace, independently frozen source
and artifact hashes, --form-factor ipad or iphone, and --expected-fixture-sha256.
The v002 expected reference identity is
88d94ad1936dd68deeedd9e91f0bb0170621ff69e6ce70c39580c901e679062b.
This identity does not qualify the fixture as representative production load.

The consumer verifies every declared release member, exact installed original
analyzer/reference bytes, and then executes the original validator. That validator
checks the actual local fixture files, trace identity/continuity/availability and
any explicitly supplied budget. Old v001 traces and budgets are rejected, never
relabeled. Numeric production budgets are not invented; --require-budget requires
both --budget and an independently expected --expected-budget-sha256.

Result remains METRICS_BOUND_BUDGETS_PENDING or BUDGETS_CHECKED_NOT_NODE_ACCEPTED.
Synthetic test traces are not actual measured iOS output. The real renderer/scene
producer for frame percentiles, observed black frames, applied degradation and
named scene/run binding is still requested from General. Hardware identity,
native process sampling and each 30-minute device run remain deferred.

Focused consumer test: ios/tests/performance/trace-consumer-test.py with the same
two contract-root flags. It executes original Shared synthetic fixtures and checks
old fixture/budget rejection; no simulator, device or endurance job is launched.
