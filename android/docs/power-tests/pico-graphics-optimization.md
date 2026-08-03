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

## Test artifacts and automation

Raw data is stored in the Git-ignored `power-results/graphics-matrix-*`
directories. The final repeated comparison is in
`power-results/graphics-matrix-20260803T111534Z`.

`pico-graphics-matrix.sh` automates:

- fixed Pico fan and brightness controls;
- process-start render configuration;
- app restart, Hub navigation, and position validation;
- start/end XR screenshots with reference validation;
- Overte frame telemetry, process CPU, CPU/GPU clocks, and thermals;
- five-second battery monitoring with immediate drop warnings; and
- static, dynamic, feature, quality, overlay, and final repeated matrices.

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
```

## Limitations and next work

- The Hub test is CPU-limited and contains no nearby avatars or active mirror
  views. Avatar-heavy and mirror-heavy domain tests are still needed.
- The dynamic turning screen had large resource-streaming/order variance and
  was not used for the final numeric recommendation.
- Internal frame counters and Android telemetry are appropriate for comparative
  engineering tests but are not a substitute for a hardware GPU profiler.
- A stable native 72 new FPS was not achieved. The compositor stayed near
  72 presents/s, while Overte generated about 20 new frames/s.
- The strongest next candidates are physics broadphase/entity workload
  reduction, script/update scheduling, inactive-entity throttling, and avatar
  complexity controls.
