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
template avatars:

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

## Limitations and next work

- The Hub test is CPU-limited and contains no nearby avatars or active mirror
  views. Avatar-heavy and mirror-heavy domain tests are still needed.
- The dynamic turning screen had large resource-streaming/order variance and
  was not used for the final numeric recommendation.
- Internal frame counters and Android telemetry are appropriate for comparative
  engineering tests but are not a substitute for a hardware GPU profiler.
- A stable native 72 new FPS was not achieved. The compositor stayed near
  72 presents/s, while Overte generated about 20 new frames/s.
- Physics broadphase and inactive simple-kinematic work are already bounded and
  are not strong next candidates for this scene. The strongest remaining work
  is longer avatar-load testing with a controlled template, followed by avatar
  complexity controls only if those runs identify a scalable bottleneck.
  Per-module controller profiling and safe Create lazy loading have now also been screened.
  Global simulation-rate and renderable-budget reductions, model-update
  throttling, redundant Create gizmo updates, and idle near-search suppression
  have been screened and rejected.
