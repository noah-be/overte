# Pico 4 graphics optimization results

## Goal and scope

These tests optimize Overte's Pico 4 CPU/GPU load and frame stability. Power
consumption was deliberately not used as a ranking metric. The headset stayed
on external power with the MCU fan fixed at 100% and the lowest visible MCU
brightness, 1/100. Level 0 was rejected because it turns the backlight off.

The controlled scene was `overte_hub` at approximately
`155.084,-97.403,-397.177`, 72 Hz. Every accepted run verified the authoritative
world and position and captured the stereo XR image before and after the
measurement. Images were checked for dimensions, non-blank content, and scene
similarity to a manually reviewed Hub reference.

The results are engineering measurements of this scene and build, not a claim
that every Overte domain has the same bottleneck.

## Recommended profile

- OpenXR render scale: **0.80**
- Refresh rate: **72 Hz**
- Forward renderer: **enabled**
- Shadows: **disabled**
- Bloom: **disabled**
- Ambient occlusion: **disabled**
- Antialiasing: **disabled**
- Fixed foveated rendering: **disabled**
- Haze: **enabled**
- Local lights: **enabled**
- Procedural materials: **enabled**
- Automatic world LOD: **low / 72 FPS target**
- Statistics overlay: **disabled for normal use**

This profile preserves the scene features whose removal produced no repeatable
benefit and uses render scale, the one control that reliably reduced GPU load.

## Adopted Pico defaults

The confirmed profile is now the normal Pico Interface baseline rather than a
benchmark-only property combination. With no `debug.overte.*` overrides and no
previously saved user choice, Pico starts with:

- 80% OpenXR render scale, also exposed as an explicit 80% choice in Graphics
  Settings;
- the lowest runtime-supported refresh rate (72 Hz on Pico 4);
- forward rendering, low world detail, no shadows, bloom, ambient occlusion,
  antialiasing, fixed foveation, or statistics overlay; and
- haze, local lights, procedural materials, and normal model/simulation update
  rates enabled.

An explicit saved render-scale choice still overrides the 80% default. ADB
properties remain available for controlled tests and take precedence over the
saved render-scale choice. Unattended world-status file output is gated behind
`debug.overte.test_mode`, so normal sessions do not perform benchmark cache
writes once per second.

## Final repeated A/B result

The final comparison used three 120-second measured runs per profile after a
30-second warm-up. Run order was interleaved. Both profiles used the same scene,
pose, 100% fan, 1/100 brightness, no foveation, and no statistics overlay.

| Metric (mean of run medians) | 100% baseline | Recommended 80% | Change |
|---|---:|---:|---:|
| GPU frame time | 12.317 ms | 10.359 ms | **-15.9%** |
| Median GPU clock | 587.0 MHz | 441.6 MHz | **-24.8%** |
| Maximum GPU temperature | 71.7 C | 66.8 C | **-4.9 C** |
| Maximum skin temperature | 58.9 C | 56.7 C | **-2.2 C** |
| XR compositor present rate | 69.33 FPS | 71.84 FPS | **+2.52 FPS** |
| New-frame rate | 19.85 FPS | 19.86 FPS | no material change |
| Render rate | 19.17 FPS | 19.72 FPS | within run variance |
| Game-loop rate | 41.54 FPS | 46.72 FPS | **+12.5%** |
| Overte process CPU | 286% | 293% | no reduction |

GPU frame time was highly repeatable: 12.287-12.359 ms at 100%, versus
10.350-10.376 ms at 80%. GPU clock was 587 MHz in all baseline runs and
441.6 MHz in all recommended runs. This is strong evidence that 80% creates
real GPU and thermal headroom.

The application-generated frame rate did not materially increase. The XR
compositor continued presenting close to 72 Hz, but Overte supplied only about
20 new frames per second in this Hub view. The remaining limit is therefore not
the GPU raster workload.

## Setting impact ranking

### 1. Render scale: largest useful GPU effect

The scale sweep tested 100%, 90%, 85%, 80%, 75%, and 70%.

- 100% held the GPU at 587 MHz with roughly 12.3 ms GPU time in the final runs.
- 90% still required 587 MHz.
- 85% generally used 490 MHz and roughly 10.6 ms.
- 80% reliably dropped to 441.6 MHz and roughly 10.4 ms.
- 75% remained at 441.6 MHz and improved only to roughly 9.9 ms.
- 70% reached roughly 7.5 ms in the first screen, but did not improve the
  CPU-limited new-frame rate and costs substantially more image quality.

The 80% setting is the knee of the curve: it reaches the lower stable GPU clock
without taking the larger quality loss of 75% or 70%.

### 2. Bloom: clearly harmful on Pico 4

At 85%, enabling bloom increased median GPU time from about 10.6 ms to
14.3 ms, forced the GPU to 587 MHz, and reduced compositor present rate in the
screening run. Bloom should remain disabled.

### 3. Fixed foveated rendering: no measured benefit

Low, medium, and high OpenXR foveation were all confirmed active. At 85%, all
three produced about 10.6 ms GPU time, effectively identical to foveation off.
At 80%, high foveation was about 10.34 ms versus 10.36 ms off. This difference
is negligible and does not justify visible peripheral degradation.

### 4. Shadows and ambient occlusion: keep disabled

They were already disabled in the Pico baseline. Short single-option screens
did not yield a trustworthy isolated cost because CPU/scene variance dominated;
one shadow run even appeared faster due to ordering/cache effects. There is no
evidence supporting their activation, and both add rendering work in domains
that use them. Keep them disabled for a conservative headset profile.

### 5. Haze, local lights, and procedural materials: preserve quality

Disabling each option independently at 85% did not reduce GPU time: all results
were approximately 10.6 ms. The bundled profile that disabled all three also
failed to improve the 100% baseline materially. They should remain enabled
unless a different domain demonstrates a specific pathological shader or light
load.

### 6. Recursive mirror views: scene-dependent

The Hub configuration exposed zero matching recursive mirror views, so turning
them off did not change this workload. Disabling them remains a sensible
domain-specific safeguard when mirrors are actually present, but this test does
not quantify that case.

### 7. Statistics overlay: no measurable performance change

An actual process-start A/B/A switch was added and verified in logs and XR
images. Disabling the overlay did not produce a result larger than run-to-run
variance. It should still be off in normal use because it obstructs the view;
enable it only for diagnostics.

## CPU bottleneck

Process CPU remained near 2.9 fully occupied cores and did not fall at lower
render scales. Instrumented update-stage logs identified the largest main-loop
costs as:

1. physics, typically about 4-5 ms per update;
2. entity updates, typically about 4-5 ms;
3. devices/input processing, about 3 ms;
4. avatars, about 2.5 ms; and
5. post-update lambdas, about 2 ms.

This explains why GPU reductions improve clock, temperature, and compositor
stability but not the roughly 20 FPS new-frame rate. The next optimization work
should target physics/entity simulation and domain content complexity rather
than further resolution loss.

### CPU optimization screens

Two process-start CPU experiments were tested with constant slow rotation,
30 seconds of warm-up, 90 seconds of telemetry, app restarts, and validated XR
images.

Limiting physics/entity simulation to 24 Hz reduced mean process CPU from
294.5% to 292.6%, only about 0.6%. The small saving does not justify reducing
simulation freshness, so the recommendation remains unlimited simulation rate.

| Renderable budget | Mean process CPU | Median changed-renderable time | Median pending updates |
| --- | ---: | ---: | ---: |
| 2000 us | 295.4% | 3.91 ms | 36.5 |
| 1000 us | 293.1% | 3.45 ms | 38.5 |
| 500 us | 296.6% | 2.69 ms | 40.5 |

The 1000 us budget saves only about 0.8% process CPU and increases deferred
updates. At 500 us, CPU becomes slightly worse while the backlog grows further.
Retain the default 2000 us. All selected runs had valid 4320x2160 start/end
images and no visually unready entities at the one-second sampling points.

Detailed avatar and post-update profiling found that other avatars and look-at
work were negligible in the Hub. Native caller tracing instead identified
`Model::updateRenderItems()` and `CauterizedModel::updateRenderItems()` as the
dominant slow post-update callbacks. A repeated per-model rate screen produced:

| Model update rate | Mean process CPU | Median callback time | Slow callback count |
| --- | ---: | ---: | ---: |
| Unlimited | 292.9% | 1.81 ms | 450 |
| 30 Hz | 295.8% | 1.45 ms | 390 |
| 24 Hz | 295.4% | 1.37 ms | 341 |

Rate limiting reduced direct callback time by 20-24% and reduced slow callback
events, but did not reduce total process CPU. It also lowers animation/model
freshness. Retain unlimited model updates in the recommended profile.

Internal timing of callbacks exceeding 5 ms separated cluster-matrix work,
property setup, per-mesh payload/bounding-box updates, and scene enqueue. For
ordinary models, the median slow callback was 8.17 ms, but the median measured
work in each individual stage was only 0.03-0.08 ms. Cauterized models showed
the same pattern, with a median 8.24 ms callback but sub-millisecond median
stages. The missing wall time moves between stages and is consistent with main
thread preemption rather than one consistently expensive function.

Five-mesh models were the exception: their mesh stage had an 8.58 ms median,
but only five slow events occurred in the 90-second run. This is too little of
the total workload to justify a global bounding-box or mesh-update quality
reduction. The result supports fixing scheduling/content outliers rather than
removing required render-item work.

### Physics ghost narrowphase

Thread-CPU profiling split Bullet's internal simulation step into collision,
constraint, integration, action, and activation stages. In the stationary Hub
test, collision dispatch accounted for roughly 1.19 ms of the internal step.
About 0.75 ms came from three no-contact-response pairs involving the local
avatar's `CharacterGhostObject`.

The ghost object is required: its broadphase overlap cache limits the ray
shotgun that decides whether the avatar can walk over an obstacle. However,
the current controller never consumes collision manifolds generated for that
ghost. A custom near callback now preserves the overlap cache and all ray tests
while skipping only the redundant ghost narrowphase.

In matched instrumented Hub runs, ghost-pair CPU fell from approximately
0.75 ms to 0.002 ms per physics substep. Total collision dispatch fell from
approximately 1.19 ms to 0.49 ms, while the useful manifold count remained
available for the real avatar rigid body. A 30-second curved locomotion route
stayed grounded and completed safely. The clean, non-instrumented build also
passed 4320x2160 start/end image validation; its 45-second telemetry window
averaged 296.4% process CPU, reached 83.7 C maximum CPU temperature and 56.8 C
maximum skin temperature, and kept the battery at 100%. Treat the per-stage
CPU reduction as the result: the short whole-process sample has no paired
control and is not evidence of an equivalent total CPU reduction.

### Input routing and scheduler profile

Route-level instrumentation identified a JavaScript polling endpoint in the
`tabletToggle-click` mapping as the largest input-routing outlier. In the
baseline it accounted for 373 of 613 routes exceeding 2 ms and 1.62 seconds of
their cumulative measured wall time. The mapping called a JavaScript getter
every input update merely to copy `wantsMenu` to `Actions.ContextMenu`.

Routing the three relevant controller inputs directly to `ContextMenu`, while
retaining JavaScript callbacks only for their UI side effects, produced:

| Input result | JavaScript polling | Direct routes | Change |
| --- | ---: | ---: | ---: |
| Mean mapping time per call | 1.414 ms | 1.169 ms | -17.4% |
| Mean device-route time per call | 0.727 ms | 0.441 ms | -39.4% |
| Routes exceeding 2 ms | 613 | 217 | -64.6% |
| `tabletToggle-click` routes exceeding 2 ms | 373 | 7 | -98.1% |
| Mean process CPU | 285.2% | 290.5% | +1.9% |

This is a confirmed local input-path improvement, but the initial A/B run did
not demonstrate a total CPU reduction; its process-CPU result moved in the
wrong direction within the already observed run variance. A subsequent
interleaved A/B/A/B comparison produced:

| Run | Polling CPU | Direct-route CPU | Direct-route delta |
| --- | ---: | ---: | ---: |
| Pair 1 | 284.89% | 291.17% | +6.28 points |
| Pair 2 | 283.56% | 281.11% | -2.45 points |
| Combined | 284.22% | 286.14% | +1.92 points (+0.67%) |

The pair deltas changed sign, while the GPU remained at 441.6 MHz in all four
runs. This confirms that the total process result is dominated by run variance
and provides no evidence of an overall CPU saving. Keep the direct routing
change because it removes unnecessary per-update JavaScript work, but do not
count it as a global CPU optimization. All six input-route test variants passed
start/end 4320x2160 reference-image validation.

A 30-second Android scheduler trace confirms substantial preemption in the
same workload. The Qt main-loop thread had 9,097 runnable switch-outs, with a
mean runnable off-CPU interval of 2.02 ms and a maximum overall off-CPU interval
of 88.64 ms. The controller and edit JavaScript threads showed the same pattern,
including runnable off-CPU intervals and occasional much larger sleeping
intervals. Consequently, multi-millisecond wall-time outliers in route or model
timers must not automatically be interpreted as equivalent CPU execution time.

## Test artifacts and automation

Raw data is stored in the Git-ignored `power-results/graphics-matrix-*`
directories. The final repeated comparison is in
`power-results/graphics-matrix-20260803T111534Z`.
The repeated simulation-rate screen is in
`power-results/graphics-matrix-20260803T122038Z`, and the renderable-budget
screen is in `power-results/graphics-matrix-20260803T132034Z`.
The repeated model-update-rate screen is in
`power-results/graphics-matrix-20260803T150423Z`.
The internal model stage profile is in
`power-results/model-render-stages-20260803T153354Z`.
The input-route baseline and direct-route comparison are in
`power-results/input-route-mapping-20260803T161749Z` and
`power-results/input-route-direct-20260803T162404Z`. The scheduler trace is
`power-results/pico-input-sched.atrace`. The repeated interleaved comparison is
in `power-results/input-route-abab-20260803T163113Z`. The Bullet stage,
collision-pair, and final clean-build runs are in
`power-results/bullet-top-profile-20260804T095057Z`,
`power-results/bullet-pair-profile-20260804T100739Z`, and
`power-results/ghost-narrowphase-final-20260804T103142Z`.

`pico-graphics-matrix.sh` automates:

- fixed Pico fan and brightness controls;
- process-start render configuration;
- app restart, Hub navigation, and position validation;
- foreground-app and Guardian/Seethrough focus validation;
- start/end XR screenshots with reference validation;
- Overte frame telemetry, process CPU, CPU/GPU clocks, and thermals;
- five-second battery monitoring with immediate drop warnings; and
- static, dynamic, feature, quality, overlay, final, CPU simulation, and
  renderable-budget repeated matrices.

The added debug properties permit controlled individual tests:

```text
debug.overte.render_scale
debug.overte.foveation
debug.overte.shadows
debug.overte.bloom
debug.overte.ambient_occlusion
debug.overte.haze
debug.overte.local_lights
debug.overte.procedural_materials
debug.overte.mirror_views
debug.overte.stats
debug.overte.simulation_hz
debug.overte.renderable_budget_us
debug.overte.model_update_hz
```

## Physics and entity CPU-time baseline (2026-08-04)

The Pico-specific diagnostic build recorded both wall time and
`CLOCK_THREAD_CPUTIME_ID` time. This prevented runnable-but-preempted intervals
from being misclassified as CPU execution. A fixed 100% fan, MCU brightness 1,
80% scale/72 Hz Hub run kept the verified reference position and passed the
end XR image check (4320x2160, reference RMSE 0.176). The app was stopped after
the run and automatic fan control was restored.

The repeatedly observed per-update ranges were:

| Stage | Wall time | Thread CPU time | Interpretation |
| --- | ---: | ---: | --- |
| Bullet step | 2.8–5.3 ms | 2.1–2.7 ms | Real CPU work is substantial, but part of each wall-time outlier is scheduling delay. |
| Entity tree update | 0.7–1.5 ms | 0.6–0.7 ms | Mostly real work. |
| Changed-renderable synchronization | 2.5–4.5 ms | 1.7–1.9 ms | Largest measured entity CPU stage; the wall-time excess is preemption/lock delay. |
| EntitySimulation simple kinematics | 0.5–1.0 ms | 0.46–0.52 ms | Small, stable cost. |

Physics contained 46 collision objects: 45 rigid bodies, of which one was
active, 13 sleeping, and 31 kinematic; no entity dynamics were registered.
This does not support an optimization that broadly skips sleeping bodies. The
Hub instead concentrates entity CPU in `updateChangedEntities()` / renderable
updates, normally with only 0–7 pending render updates (mostly models).

The follow-up below splits that function into changed-ID transfer, renderer
lookup, prioritization, and individual `updateInScene()` calls. The global
entity/simulation rate and existing 2000-us budget remained unchanged.

## Entity synchronization and animation-joint update (2026-08-04)

Thread-CPU instrumentation of 3,567 Hub entity-render synchronization calls
showed that changed-ID transfer, renderable lookup, and priority sorting cost
only 0.009, 0.037, and 0.121 ms per call respectively. `updateInScene()` cost
1.230 ms per call and accounted for nearly all remaining CPU work. Model
entities represented 92.5% of that CPU time. The existing changed-ID and
renderable containers are both sets, so duplicate same-frame work was already
coalesced and did not offer another optimization.

Deeper profiling of 4,817 animation samples attributed 89.2% of their measured
thread CPU to joint-data generation and transfer, 6.7% to smooth-frame
interpolation, and 4.1% to setup. Reusing temporary interpolation and joint
vectors did not help: model CPU per render update changed from 0.1619 to
0.1637 ms (+1.1%), so that experiment was rejected.

The retained Android change removes a redundant per-joint string-map lookup.
`_jointMapping[j]` already maps model-joint index `j` to an animation-joint
index, but the default-translation path previously looked up the animation
joint name to recover the same model index on every sample. Directly using
model joint `j` produced:

| Metric | Name lookup | Direct model-joint index | Delta |
| --- | ---: | ---: | ---: |
| Joint CPU per animation sample | 0.2286 ms | 0.2028 ms | -11.3% |
| Joint CPU normalized per joint | 0.02741 ms | 0.02386 ms | -13.0% |
| Total measured animation CPU | 0.2563 ms | 0.2287 ms | -10.8% |
| Mean process CPU | 291.83% | 298.00% | +2.1% |

The direct-index run covered 5,117 animation samples. Its process-CPU result
moved in the wrong direction within known run variance, so this is a confirmed
local hot-path improvement rather than evidence of a global CPU reduction.
Both variants retained the same 24 Hz animation cadence and passed start/end
Hub XR image validation; end-image RMSE was 0.275 for the lookup variant and
0.269 for the direct-index variant.

Artifacts are in `power-results/entity-sync-profile-20260804T091757Z`,
`power-results/entity-sync-reuse-20260804T092607Z`,
`power-results/model-animation-profile-20260804T093217Z`, and
`power-results/model-joint-direct-20260804T093636Z`.

## Idle controller-script scheduling (2026-08-04)

A history and branch audit preceded this follow-up. Android already limits
simple-kinematic work to two entities or 4000 us per update, model animation
already runs at 24 Hz, Bullet already disables unconditional AABB refreshes,
and the retained ghost-pair narrowphase skip was already present. None of the
other Pico branches contained an additional physics, entity, or script
scheduling optimization to carry over.

A clean build of the branch was installed before recording a new fixed-fan Hub
baseline. The 60-second baseline averaged 301.17% process CPU over 12 samples
(292–307%), with a maximum CPU sensor temperature of 84.5 C. Start and end XR
screenshots passed the 4320x2160 reference check with RMSE 0.357 and 0.267.

A separate 30-second, 99 Hz `simpleperf` sample showed that the remaining work
was not dominated by Bullet broadphase. The controller-script thread accounted
for 27.64% of sampled process cycles, while all of `libphysics.so` accounted
for 1.75%. Existing internal Bullet measurements put AABB refresh plus
overlapping-pair calculation at only about 0.12–0.14 ms per substep after the
ghost-pair fix. Further broadphase changes were therefore not justified.

The retained change makes the standalone controller dispatcher adaptive. Its
normal interaction rate remains 60 Hz whenever the tablet, keyboard, Create
mode, trigger/grip input, or a dispatcher module is active. When all of those
are idle, the already-independent controller mappings continue to capture
input while the expensive dispatcher poll runs at 30 Hz. Other platforms do
not enable the standalone lazy-ray setting and retain their existing behavior.

Two repeated 60-second Hub runs produced:

| Metric | Clean baseline | Adaptive run 1 | Adaptive run 2 |
| --- | ---: | ---: | ---: |
| Mean process CPU | 301.17% | 291.42% | 288.08% |
| Process CPU range | 292–307% | 278–300% | 274–300% |
| Maximum CPU temperature | 84.5 C | 81.8 C | 80.6 C |
| End-image reference RMSE | 0.267 | 0.270 | 0.266 |

The repeated adaptive mean was 289.75%, a reduction of 11.42 CPU percentage
points (3.8%) from the clean baseline. Both runs reported zero dropped frames
and zero stutters in the final GPU sample. A follow-up `simpleperf` recording
reduced the controller-script share from 27.64% to 23.04%; normalized by each
recording's total event count, that is approximately 18% fewer cycles in the
controller-script thread.

Two narrower experiments were not retained. Coalescing repeated hidden Create
gizmo edits and fully disconnecting their inactive frame callback did not
produce a repeatable process-CPU improvement. Skipping the dispatcher's nearby
overlay/entity searches while idle measured 291.00%, within the adaptive
30-Hz runs' normal spread. These results indicate that dispatcher cadence, not
the individual near-search calls, is the useful low-risk lever in this scene.

Per-module wall-time instrumentation then split the dispatcher into controller
location, overlay, nearby-entity, pointer, and individual module calls. Nearby
entity-property collection was the largest blocking stage. Replacing its
individual property reads with `Entities.getMultipleEntityProperties()` made
that local stage about 26% shorter, but a clean 60-second run measured 290.17%
process CPU, indistinguishable from the 291.42% and 288.08% adaptive runs. The
dispatcher simply completed more polls, so the batch experiment was rejected.

Deferring the entire Create editor behind a lightweight button was also
screened and rejected. Two valid idle runs without `edit.js` averaged 282.42%
CPU versus 289.75% for the adaptive comparison, but the repeated delta varied
substantially. More importantly, an automated first-open test found that the
large editor could remain in initialization for more than five minutes when
loaded in an already active domain. Delaying a core function by an unbounded
amount is not an acceptable tradeoff, so the launcher and handshake were fully
removed. One run that lost XR focus to the Pico boundary UI was discarded and
is not included in these figures.

Artifacts are in `power-results/physics-open-baseline-20260804T164324Z`,
`power-results/overte-open-20260804T164643Z-r2-leaf-r2.data`,
`power-results/controller-idle-ab-20260804T165549Z`,
`power-results/controller-idle-repeat-20260804T170117Z`, and
`power-results/controller-idle-20260804T165900Z.data`. The rejected batch and
Create-lazy runs are in `power-results/controller-batch-ab-20260804T175126Z`,
`power-results/create-lazy-valid-20260804T181855Z`,
`power-results/create-lazy-valid-r2-20260804T182241Z`, and
`power-results/create-lazy-simpleperf-20260804T182608Z`.

## Local avatar-load screening (2026-08-04)

A branch and upstream audit found an existing client-side test facility that
creates offset copies of received other avatars. It was not usable as written:
the first replica recursively acquired the non-recursive avatar-map write lock
through `addAvatar()` and froze avatar packet processing. Removing the outer
lock lets `addAvatar()` retain its own normal locking and fixed the reproduced
deadlock. No other Pico branch or upstream `master` contained that fix.

Pico test mode now accepts a timestamped, bounded replica count and publishes
aggregate avatar status without identifiers or screenshots. Commands older
than ten seconds are rejected, counts are limited to 0--50 copies per received
avatar, and setting zero removes the local load. Build, install, live changes
from 0 to 2 and 5 copies, return to zero, and stale-command rejection all
passed on the headset. With three received template avatars, five copies of
each produced 19 total avatars and the status correctly identified 15 local
replicas.

Two short interleaved A/B screening pairs used a fixed 100% fan and MCU
brightness 1. Each side contained six samples and retained the same three real
template avatars. At this point the avatar-simulation value was an
instantaneous sample taken when status was published:

| Metric | 4 avatars | 19 avatars | Combined delta |
| --- | ---: | ---: | ---: |
| Mean process CPU | 218.08% | 229.67% | +11.58 points (+5.3%) |
| Mean avatar simulation | 3.861 ms | 5.421 ms | +1.560 ms (+40.4%) |

The direction repeated in both pairs, but the individual CPU deltas were 8.4%
and 2.3%, and individual one-second avatar timings contained loading/scheduling
outliers. This validates the load generator and confirms that the existing
avatar update budget limits growth, but it is not yet evidence for a specific
production complexity limit. A controlled template avatar and longer
interleaved runs are required before changing avatar quality or distance rules.
`pico-avatar-matrix.sh` now automates those repeated stages and rejects a run if
XR focus or the real template-avatar population changes.

A follow-up 20-second-per-stage 0/5/0/5 matrix retained one stable template.
Combined process CPU was 226.38% without replicas and 222.88% with replicas,
so this run did not reproduce an overall CPU increase. It also confirmed that
an instantaneous avatar-simulation sample is too sensitive to frame timing for
small matrices. Test-mode status now reports the mean of every avatar
simulation frame in its one-second publication interval and test mode can be
toggled at runtime. A post-change smoke matrix measured 2.895 ms without
replicas and 4.178 ms with replicas (+44.3%), while combined process CPU was
231.5% and 225.4% respectively. This more stable internal metric confirms that
local avatar work scales, but the total-process effect remains below the noise
of the current scene. No production avatar limit is justified by these runs.

A higher-load 20-second-per-stage 0/20/0/20 matrix retained two stable real
templates and produced 43 total avatars during load. Combined process CPU was
222.95% at baseline and 225.30% under load (+1.05%); mean avatar simulation was
3.542 ms and 3.857 ms (+8.9%). The loaded stages skipped 40.75 avatars per
frame on average because the time budget had expired, compared with 0.65 at
baseline. The separate `updated` counter averaged 1.10 and 1.20 respectively;
it counts in-view avatars with fresh joint data while within budget, not every
avatar that was simulated. This demonstrates that the existing fixed update
budget successfully bounds CPU growth at high local crowd counts. It also
makes the tradeoff explicit: additional avatars primarily lose update
frequency rather than consuming unbounded simulation time.

An ascending and descending 0/1/2/5/10/20/10/5/2/1/0 saturation ramp then
measured where this tradeoff begins. With two stable templates, mean
budget-skipped counts were 0.60 at 3 total avatars, 2.80 at 5, 4.30 at 7,
10.65 at 13, 20.65 at 23, and 40.90 at 43. Process CPU stayed between 222.3%
and 228.5% without a monotonic increase; avatar simulation stayed between
3.494 ms and 4.130 ms. The budget is therefore already active in this scene at
the smallest tested crowd increase and becomes the dominant limiter as the
crowd grows. Raising it would trade CPU for smoother crowd updates rather than
remove CPU work. The matrix now writes both per-stage `summary.csv` and an
`aggregate.csv` that combines repeated replica counts.

Test-mode timing was then split around the other-avatar update stages. A
repeated 0/5/0/5 matrix with three stable templates measured 4 and 19 total
avatars. Combined process CPU was 228.95% and 229.60%, while complete
other-avatar processing was 7.636 ms and 9.730 ms. Priority construction grew
from 0.349 ms to 1.226 ms, but sorting was only 0.005--0.032 ms,
`ensureInScene()` 0.070--0.086 ms, scale animation 0.001--0.022 ms, and the
budgeted simulate/render-update section 2.100--2.194 ms. The remaining
wall-clock time was observed around the lightweight skeleton/orb/physics state
polls. Those functions did not appear as material leaf costs in the guarded
CPU profile, so the wall-clock bucket likely includes main-thread descheduling
and must not be interpreted as equivalent CPU time. The result rules out sort,
scene assurance, and scale animation as useful Pico crowd targets in this
scene. Priority construction scales, but its current process-level effect is
too small to justify a production change.

A later guarded 30-second-per-stage 0/5/0/5 matrix retained two stable real
templates throughout and compared 3 with 13 total avatars. The two baseline
stages averaged 223.583% process CPU, 3.116 ms avatar simulation, and 0.75
budget-skipped updates. The two loaded stages averaged 223.083% CPU, 3.646 ms
simulation, and 10.75 skipped updates. Thus process CPU changed by only -0.50
percentage points while avatar simulation increased by 0.530 ms (17.0%) and
ten additional updates per frame were skipped. The budgeted simulate/render
section remained effectively unchanged at 1.074 versus 1.063 ms. Complete
other-avatar processing grew from 3.279 to 4.014 ms, again mostly in the
wall-clock state-poll bucket rather than in a CPU-profiled compute hotspot.
This longer stable repetition reinforces the fixed-budget conclusion without
justifying a production budget increase or crowd-quality change. Raw local
artifacts are in `power-results/avatar-long-guarded-20260804`.

A guarded 15-second, 99 Hz frame-pointer callgraph follow-up captured 2858
samples with none lost. `AvatarManager::updateOtherAvatars()` accounted for
2.79% of sampled cycles including descendants. Its largest visible descendant
was `OtherAvatar::updateOrbPosition()` at 1.82%; `OtherAvatar::simulate()` was
0.60%, and the remaining reported avatar functions were each below 0.4%.
Although 25.7% of samples had incomplete call chains, this inclusive result
agrees with the leaf profile and provides no evidence that the state-poll
wall-clock bucket is a comparable CPU cost. No production state-poll or avatar
budget change is justified by this scene.

Loaded-model telemetry subsequently exposed an important limitation in all of
the local replica results above. `setReplicaCount()` removed the received
source avatars even when the requested count was already zero. Their unchanged
identity and skeleton traits were not guaranteed to be retransmitted, so the
source avatars and their replicas were recreated as loading-orb placeholders.
The prominent `updateOrbPosition()` profile was consistent with that state.
Consequently, the preceding numbers describe placeholder/update-budget harness
behavior and must not be used as rendered-avatar performance evidence.

The test-only replica implementation now leaves received source avatars alive,
does nothing when the requested count is unchanged, reconciles replicas on a
normal avatar data packet, and seeds new replicas from the source identity and
skeleton traits. Status reports loaded source and replica model counts without
recording identifiers. The matrix waits until every expected model is loaded
and rejects a stage if any model becomes unloaded.

A live `0 -> 5 -> 0` validation retained four loaded source models throughout,
loaded all 20 expected replica models, and removed those replicas without
reloading the sources. A short 10-second-per-stage smoke matrix then measured
5 loaded total avatars at baseline and 25 loaded total avatars under load. The
two baseline stages averaged 228.5% process CPU and 4.742 ms avatar simulation;
the loaded stage averaged 224.0% and 4.108 ms. Budget-skipped updates rose from
1.8 to 22.0 per frame. These short, noisy values validate loaded-model test
plumbing, not a production optimization. Replica creation also produced brief
`ensureInScene()` warm-up spikes before settling; the matrix's load wait and
warm-up keep them outside the measurement interval. The next meaningful test
is a longer interleaved run with a controlled, stable template population.

The first longer follow-up correctly became invalid when Interface aborted in
the loaded-stage warm-up. Its native backtrace showed non-finite joint poses
reaching eye-rig basis construction, where a zero or invalid look-at axis hit a
debug assertion. Avatar packet parsing now rejects a non-finite joint
translation scale, rig pose copying falls back to the model defaults for
non-finite joint transforms, and eye updates ignore non-finite or near-zero
basis inputs. A subsequent 60-second stress run kept all four sources and 20
replicas loaded with no NaN warning, assertion, or process restart. The
rejected matrix remains diagnostic only; a complete longer matrix is still
required.

The repaired 30-second-per-stage `0/5/0/5` matrix then completed with four
stable source avatars and compared 5 with 25 fully loaded total avatars. Every
sample reported all four source models and all 20 expected replica models as
loaded. Baseline stages averaged 230.417% process CPU, 3.987 ms avatar
simulation, 4.378 ms complete avatar processing, and 2.333 budget-skipped
updates. Loaded stages averaged 227.084% CPU, 4.318 ms simulation, 5.832 ms
processing, and 22.000 skipped updates. Priority construction increased from
0.391 to 1.514 ms and the budgeted simulate/render section from 3.800 to
4.117 ms; sorting and scene assurance remained below 0.03 ms. The 0.331 ms
simulation increase is modest, while the lower total-process CPU again shows
that scene/process variance and the fixed avatar budget dominate this test.
No production budget increase or crowd-quality reduction is justified. A
loaded-avatar CPU callgraph is the next useful way to check whether priority
construction or the budgeted section contains an actionable compute hotspot.

Paired 15-second, 99 Hz frame-pointer callgraphs compared the same four loaded
sources without replicas and with 20 loaded replicas. The baseline recorded
2812 samples with 24.96% incomplete call chains; the loaded profile recorded
2748 with 23.33% incomplete chains. Neither lost samples. Inclusive
`AvatarManager::updateOtherAvatars()` stayed nearly unchanged at 1.81% and
1.86%, and `OtherAvatar::simulate()` was 1.38% and 1.24%. This rules out an
avatar-update compute hotspot corresponding to the larger priority-construction
wall-clock measurement.

The scaling CPU path was avatar packet decoding. Inclusive
`AvatarHashMap::parseAvatarData()` increased from 0.69% to 2.61%, while
`OtherAvatar::parseDataFromBuffer()` increased from 0.55% to 2.35%. The loaded
profile attributed 1.78% to `AvatarReplicas::parseDataFromBuffer()`. Local
replicas intentionally decode the received source packet once per copy, which
resembles per-avatar decode work but is not the same network population as
independent mixer-fed avatars. The result identifies packet parsing as the
next controlled-crowd profiling target; it does not by itself justify changing
production avatar update budgets or quality limits.

A higher-resolution follow-up used guarded 30-second, 399 Hz frame-pointer
profiles. The initial baseline and 20-replica runs recorded 35,109 and 34,207
samples with no loss; their incomplete-callchain rates were 27.50% and 27.75%.
The loaded `AvatarData::parseDataFromBuffer()` callgraph exposed repeated Qt
detach/refcount work from two temporary `QVector<bool>` validity arrays and
from indexing the already write-locked joint array. Joint packets now read the
two validated wire-format bit vectors directly and acquire the joint-array data
pointer once after resize, avoiding those allocations and repeated detach
checks without changing the packet format or decoded state.

After build, install, and a fully settled loaded-crowd check, the paired
profiles recorded 35,914 baseline and 33,604 loaded samples with no loss and
26.50% and 25.79% incomplete callchains. Under 20 loaded replicas,
`AvatarHashMap::parseAvatarData()` fell from 3.02% to 1.06% inclusive and
`AvatarData::parseDataFromBuffer()` from 1.95% to 0.45%. The new detailed
callgraph contains none of the removed `QVector<bool>` or joint-vector detach
paths. These percentages also depend on the uncontrolled remote avatars'
packet rates, so they demonstrate removal of the identified decoder overhead
but are not claimed as an exact production CPU reduction. Interface remained
connected and crash-free, all 24 other skeleton models loaded, and the local
replica count returned to zero after each run.

The decoder audit also found that truncated hand-controller data could be read
past the received buffer and that several raw floating-point fields accepted
non-finite values. The parser now checks the complete hand-controller block
before decoding and rejects non-finite positions, bounding boxes,
sensor-to-world translations, face coefficients, and far-grab transforms
before changing avatar state. The host regression suite covers every truncated
prefix of the fixed and variable avatar-data sections, including face, joint,
far-grab, default-pose, and hand-controller data. It also verifies that invalid
numeric follow-up packets preserve the preceding valid state. Joint and
default-pose sections now validate their complete variable-length payload
before resizing or updating the joint array; every truncated prefix and an
invalid far-grab tail preserve seeded joint state. The decoder also enforces
the encoder's positive, finite joint-translation scale invariant; zero,
negative, NaN, and both infinities preserve seeded state in the host regression.
The matching encoder now derives that scale only from finite components, so an
invalid component follows the fixed-point encoder's zero fallback without
making the complete packet undecodable; an encode/decode regression retains a
valid component from the same joint.
The avatar-data encoder now also caps joint and blendshape counts to the 255
entries representable by their one-byte wire fields while leaving the complete
local rig and expression vectors unchanged. Regressions serialize 301 local
joints and 300 local blendshapes; the latter deliberately precedes joint data
to verify that the following section remains aligned and decodable.
Non-finite outbound blendshape coefficients and the legacy face header's float
fields now use a zero fallback as well. An encode/decode regression combines
finite, NaN, and infinite coefficients with a following joint and verifies that
both sections remain decodable.
Raw global/local positions, bounding boxes, look-at positions, and
sensor-to-world matrices are now flagged for transmission only when their
floating-point values are valid. Bounding-box dimensions must be non-negative,
and sensor matrices must have finite positive axis scales. A regression first
verifies that valid versions of all five sections remain present, then makes
all five invalid and confirms that they are omitted while following joint data
is still decoded.
The receiver mirrors the same geometric constraints: negative bounding-box
dimensions and zero or negative sensor-to-world scales are rejected before
replacing the preceding valid state. Host coverage includes zero, a negative
unit, and the minimum signed wire value for the sensor scale.
Far-grab output now applies the same finite, non-degenerate matrix validation.
Invalid individual poses use identity, and the far-grab section is omitted
when no valid pose remains, allowing the joint section that shares its packet
to stay decodable. A valid identity-pose control remains present on the wire.
The rebuilt Android client completed a clean Pico cold start without a native,
JNI, or packet-validation error.
The shared six-byte quaternion decoder was hardened as well: byte patterns
whose three stored components fall outside the unit sphere are projected onto
it instead of taking the square root of a negative remainder. Existing
rotation-accuracy tests and new malformed-extreme tests both pass. The matching
encoder now normalizes finite inputs and substitutes identity for zero-length
or non-finite rotations; its invalid-input roundtrips are covered as well. The
same guarded normalization is shared by the legacy eight-byte encoder.
The shared signed fixed-point encoder similarly maps non-finite scalar and
vector components to zero before integer conversion. Its radix scaling now
uses a bounded floating-point exponent instead of a potentially undefined
integer shift, with direct scalar and mixed-vector regression coverage.
Avatar scale-ratio packing now maps non-finite and non-positive inputs to the
neutral scale, clamps finite overflow to the format maximum, and keeps tiny
positive ratios away from the wire value reserved for the `10` range boundary.
Tests cover invalid values, underflow, overflow, and the unchanged boundary.
The two-byte view-angle encoder now uses the same policy: non-finite values
fall back to zero and finite overflow is clamped to `[-180, 180]` before the
unsigned conversion. Both limits and all non-finite classes are covered.
Packed audio gain now treats non-positive and non-finite input as silence
instead of allowing the bit-level logarithm approximation to turn invalid
values into a loud byte. The exact unity-gain roundtrip remains unchanged.
Inbound microphone and injector property parsing now rejects truncated fixed
headers, invalid channel/boolean flags, non-finite transforms, and invalid
injector radii before audio reaches the jitter buffer. A host regression test
checks every truncation boundary as well as representative invalid scalar and
transform values; the suite passes all seven QtTest entries.
The audio mixer now performs the same fixed-header validation before creating
a microphone or injector stream. Truncated codec negotiation, domain-list,
per-avatar gain, and injector-gain messages are ignored before they can change
mixer state; the server-side translation unit passes host syntax compilation.
Replicated audio wrappers now require a recognized mapping and a complete,
non-null source UUID before creating a replicated node. Radius-ignore, solo,
stop-injector, and replicated-codec control messages likewise reject incomplete
records before mutating mixer state.
Privileged environment-mute broadcasts now require a complete finite position
and a non-negative finite radius. Node-mute requests similarly require a
complete non-null target UUID before looking up or changing a node.
GCC's static analyzer reported no primary-source diagnostics in the four audio
stream/parser translation units or the two mixer translation units. Its
remaining diagnostics originated in dependency headers rather than these
changed paths.
A matching analyzer pass reported no primary-source diagnostics in the changed
avatar packet, avatar-map, trait, received-message, animation-pose, GLM, or
shared packing translation units. A syntax pass also accepted every
`android/pico-*.sh` test and profiling script.
A clean Debug configuration with server targets enabled subsequently compiled
and linked the complete `assignment-client` target, including all modified
audio stream and mixer translation units.
The underlying `ReceivedMessage` API now clamps copied and zero-copy reads and
seek positions to the actual message bounds, including string payloads with a
truncated length or body. Bulk avatar parsing additionally rejects incomplete
UUID/header tails and records whose parser length cannot make valid progress.
Dedicated networking tests cover these boundary conditions.

Skeleton traits now receive equivalent boundary handling. Serialization is
limited to the 255 joints representable by the wire header, derives UTF-8 name
offsets from the encoded bytes, and substitutes safe transforms for invalid
joint input. Deserialization verifies the complete joint and string-table
payload, finite scale headers, bone types, string ranges, and reconstructed
transforms before replacing the current skeleton. Regression coverage includes
negative translations, zero and non-finite transforms, non-ASCII names, an
oversized joint vector, and every truncated prefix of a valid trait.

Avatar identity decoding is transactional now, so a truncated variable-length
identity cannot advance its sequence number or partially replace names and
flags. Replica identity forwarding also creates an input stream per replica;
previously only the first replica consumed the shared stream successfully. In
multi-identity packets, forwarding is limited to the byte range of the current
record, and records for ignored avatars are still consumed so parsing can
continue with the next identity.
Regression coverage checks every truncated identity prefix and two recipients
of the same replicated identity.

Bulk and override trait records now reject enum values outside the declared
trait range, negative payload sizes on simple traits, oversized declared
payloads, and missing per-avatar trait terminators. Instanced-trait deletion
retains its defined `-1` marker. Truncated kill-avatar records are discarded
before reading either field. Unit coverage exercises the shared type and wire
size validation, including the deletion exception.

A later avatar-load validation exposed transient non-finite absolute joint
poses while a fallback rig was initialized. Matrix decomposition in
`AnimPose` divided each basis column by its scale even when an axis had
collapsed to zero, which turned a valid degenerate transform into NaN. The
decomposition now normalizes only nonzero finite axes, reconstructs a single
missing axis from the other two when possible, and uses an identity rotation
when the orientation cannot be recovered safely. Non-finite input matrices
also fall back to an identity pose. Regression coverage exercises each of the
three collapsed axes, a fully collapsed transform, and non-finite input. The
complete host animation test executable passed all 12 test groups. The Android
build and a clean Pico cold start also completed without a NaN, native crash,
or JNI error.

The avatar matrix no longer depends on another user as its source. In guarded
test mode it can create one local `OtherAvatar` from the current MyAvatar pose,
identity, skeleton URL, and skeleton trait, then feed the existing replica path
without transmitting a synthetic identity or pose to the domain. Commands are
timestamped, the status schema exposes whether this source is active, and test
mode shutdown removes it and all replicas. The matrix now defaults to this mode and requires an
otherwise empty domain; `--received-template` keeps the prior explicitly
selected behavior. Cleanup removes both replicas and source before restoring
test mode and device controls.

Host avatar tests, the ARM64 Android build, and a Pico live sequence all passed.
The live sequence moved from one self avatar to one fully loaded local source,
then to five fully loaded copies (seven total), and returned to one self avatar.
A stale template command was rejected. A short end-to-end 0/2 smoke matrix also
completed with one stable source, produced the expected two and four total
avatars, retained loaded models for every stage, and cleaned back to one. Its
four-second measurements validate the harness only and are not used as a
performance recommendation.

The first 30-second-per-stage local `0/5/0/5` run exposed a remaining fixture
gap. Baseline and five-replica stages averaged 289.083% and 292.333% process
CPU, 1.306 and 3.245 ms avatar simulation, and 1.385 and 3.457 ms complete
other-avatar processing. However, `updated` remained zero in every stage: the
local pose had only been injected during template creation, so the copies no
longer had fresh joint data. These values characterize static loaded-avatar
simulation, not the normal continuously received avatar path, and are retained
only as that limited baseline.

The local fixture now replays its cached complete pose packet once per client
update immediately before other-avatar simulation. A twentieth status field
and matching CSV column count successful replays, allowing stale-fixture runs
to be identified. This remains entirely client-local, sends no synthetic
packet to the domain, and adds no Pico SDK or proprietary dependency. The
updated 0/2 harness smoke test passed with 20-column status/summary/telemetry
and 18-column aggregate output.

A repeated 30-second-per-stage `0/5/0/5` matrix then compared one refreshed
local source with that source plus five fully loaded replicas. The two baseline
stages averaged 286.583% process CPU, 1.056 ms avatar simulation, and 1.164 ms
complete processing. The two loaded stages averaged 285.417% CPU, 3.115 ms
avatar simulation, and 3.360 ms complete processing. Almost all of the 2.196 ms
processing increase was in the budgeted simulate/render section (0.972 to
2.995 ms); priority construction grew from 0.107 to 0.245 ms and pre-update
work from 0.005 to 0.022 ms. The source refreshed 54.584 times per baseline
interval and 37.334 times under load. Mean `updated`/budget-skipped counts
changed from 1.000/0.000 to 3.250/2.750, proving that fresh joint data now
reaches the fixed update budget. Process CPU changed by -1.166 percentage
points (-0.4%), so this controlled result supports the existing budget's
bounded CPU behavior and still does not justify a production avatar-quality
or population reduction.

A refreshed-pose `0/1/2/5/10/20/10/5/2/1/0` saturation ramp then located the
first update-budget plateau. The repeated aggregate stages measured:

| Replicas | Total avatars | Mean CPU | Avatar simulation | Updated | Budget-skipped |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 2 | 284.9% | 1.053 ms | 1.0 | 0.0 |
| 1 | 3 | 289.4% | 1.792 ms | 1.9 | 0.1 |
| 2 | 4 | 279.4% | 2.743 ms | 2.9 | 0.1 |
| 5 | 7 | 285.9% | 3.078 ms | 3.7 | 2.3 |
| 10 | 12 | 291.5% | 3.642 ms | 3.4 | 7.6 |
| 20 | 22 | 289.6% | 4.621 ms | 3.2 | 17.8 |

Only the peak 20-replica stage occurred once; every other row combines the
ascending and descending stages. CPU remained inside the run's background
variance while the updated count stabilized around three to four from five
replicas onward. Five replicas are therefore the first useful controlled
plateau, rather than an arbitrary crowd-size limit.

Paired 30-second, 399 Hz frame-pointer profiles at that plateau recorded
41,319 baseline and 38,444 loaded samples with no loss. They exposed work
outside the already measured `updateOtherAvatars()` interval: every decoded
joint packet immediately forced all of an avatar's kinematic detailed motion
states active, even when the fixed update budget had not applied that packet
to the rig. Inclusive `DetailedMotionState::getWorldTransform()` grew from
0.74% to 1.86%, while `AvatarManager::postUpdate()` grew from 0.95% to 2.22%.

Detailed motion states are now activated after fresh joint data is accepted by
`OtherAvatar::simulate()`, immediately after interpolation updates the rig.
Position-only motion continues to dirty the main avatar motion state during
packet parsing. This aligns collision-transform pulls with the same accepted
pose that rendering uses and avoids physics work for budget-skipped packets.
The repeated profiles recorded 40,183 baseline and 38,669 loaded samples with
no loss. The detailed-motion load delta fell from 1.12 to 0.63 percentage
points (44%), and the complete avatar post-update delta fell from 1.27 to 1.03
points (19%). These are reductions in the isolated callgraph deltas, not an
exact whole-process CPU claim: a post-change `0/5/0/5` matrix still had enough
run variance that loaded process CPU was lower than its baseline. All models,
fresh-data counters, and budget counters remained valid, and a guarded
10-second locomotion check completed without an unsafe height, restart, native
failure, or non-finite-pose diagnostic.

The post-change profile still showed a separate scalable bound-update cost.
`Avatar::updateFitBoundingBox()` read every joint's position and rotation
through two independent thread-safe Rig calls. With five replicas it accounted
for 1.40% inclusive versus 0.48% at baseline; repeated `QReadWriteLock` paths
were visible below it. Skipping or rate-limiting collision bounds would risk
stale avatar physics, so that approach was not used.

Rig now provides one consistent absolute-pose snapshot copied under a single
read lock. Each avatar reuses snapshot storage, transforms every pose to world
space, and computes the same multi-sphere fit bound every frame. This removes
per-joint lock/relookup overhead without reducing bound freshness or avatar
quality. Paired 30-second, 399 Hz profiles recorded 39,289 baseline and 41,461
loaded samples with no loss. Fit-bound work measured 0.25% and 0.58%; compared
with the preceding pair, loaded inclusive cost fell by 59% and the load delta
fell from 0.92 to 0.33 percentage points (64%). Complete avatar post-update
measured 0.40% and 0.80%, reducing its load delta from 1.03 to 0.40 points
(61%). The new bulk Rig snapshot itself measured only 0.02% and 0.04%.

The shared ARM64 Android build and rebuilt host animation test executable
passed. A guarded local 0/5 smoke matrix retained every model, fresh-pose
refresh, and update-budget invariant. A subsequent 15-second verified Hub
locomotion run with five replicas completed at the expected safe height and
returned to the test start; no process restart, native failure, assertion, or
non-finite-pose diagnostic was present. These profiles isolate the removed
overhead, but whole-process CPU remains too scene-sensitive for an exact power
claim.

### Reproducible host regression set

`tests/pico-host-regression-test.sh` now explicitly builds and runs the six
host suites covering the changed animation, positional-audio, avatar-data,
packet, received-message, and GLM paths. The Debug run passed 81 tests with one
expected configuration-dependent skip. A separately generated Release
dependency configuration passed all 82 tests with no skips, covering optimized
and `NDEBUG` behavior as well as the regular Debug assertions. Both runs used
an isolated settings directory and the Qt platform plugins belonging to their
CMake build. The headless Release dependency graph disabled SDL X11 support
because these suites do not create an SDL display; this does not change the
Android build or runtime configuration.

The Rig snapshot regression also publishes changing two-joint poses on the Rig
owner thread while a foreign thread copies 5,000 bulk snapshots. Every copy
must contain a finite root and child from one consistent generation. Twenty
repeated Debug and twenty repeated Release runner invocations completed with no
suite failure, adding 3,260 passed tests and 20 expected Debug-only skips.

The dedicated Pico Gradle configuration also completed `lintDebug`, Java
compilation, the ARM64 native build, and final APK assembly with no lint issues.
The package now carries the shared Overte launcher icon and explicit no-backup
rules for both legacy and Android 12 data extraction. Its controlled restart
uses an exact alarm only on pre-Android-12 systems or after the platform
confirms exact-alarm access; otherwise it uses an allowed idle-capable fallback
instead of risking a permission exception. The packaged manifest and all three
new resources were verified from the generated APK.

## Limitations and next work

- The Hub test is CPU-limited. A controlled local avatar population is now
  available; its refreshed-pose 0/5/0/5 and 0-through-20 saturation tests are
  complete. Mirror-heavy and independent mixer-fed moving-avatar tests are
  still needed.
- The dynamic turning screen had large resource-streaming/order variance and
  was not used for the final numeric recommendation.
- Internal frame counters and Android telemetry are appropriate for comparative
  engineering tests but are not a substitute for a hardware GPU profiler.
- A stable native 72 new FPS was not achieved. The compositor stayed near
  72 presents/s, while Overte generated about 20 new frames/s.
- Physics broadphase and inactive simple-kinematic work are already bounded and
  are not strong next candidates for this scene. The strongest remaining work
  is validation with independent mixer-fed moving avatars and a mirror-heavy
  domain; the local fixture intentionally controls pose traffic but cannot
  reproduce every network and content interaction. Avatar complexity controls
  remain unjustified unless those tests expose a bottleneck that cannot be
  removed without reducing quality.
  Per-module controller profiling and safe Create lazy loading have now also been screened.
  Global simulation-rate and renderable-budget reductions, model-update
  throttling, redundant Create gizmo updates, and idle near-search suppression
  have been screened and rejected.
