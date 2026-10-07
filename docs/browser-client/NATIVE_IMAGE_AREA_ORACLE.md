# Deterministic Image oracle sampling

The prior native Image failure was reproduced on saved genuine opaque native and
browser screenshots. Native FINISHED resource state, at least three subsequent
render frames, actual camera pose, fixture cleanup and source coherence were
already satisfied. Canvas minification selected a kernel that aliased authored
fine detail despite `imageSmoothingQuality='high'`. No new native process or GPU
run was performed for this proposal.

Both screenshot and SHA-audited source now use the same deterministic weighted
pixel-overlap area reducer. Canvas only decodes/extracts original RGBA bytes at
natural size; it never resizes for the oracle. Each output cell integrates exact
fractional input-pixel coverage. Source RGBA is composed over authored magenta in
linear light using the existing compositor, before encoded-RGB area averaging.
Screenshot channels receive no brightness, tone or exposure transformation.
The existing calibrated two-screen-pixel inset is applied as normalized source
UV coordinates. The reduced grid remains 64×64. Dimensions are at most 16,384
per side and four megapixels total; RGBA view lengths, crop bounds, finite
positive footprints and output limits are explicit. Only floating-point sum
overshoot is clamped back into physical byte-channel bounds.

CPU reanalysis of the existing opaque images yields:

| Saved actual pixels | RGB MAE against audited source | Correlation | Mask mismatch |
| --- | ---: | ---: | ---: |
| Native | 1.82425 | 0.93899 | 0 |
| Browser | 0.70503 | 0.99261 | 0 |

All three UV reversals fail the unchanged 0.9 correlation requirement. Portable
SHA/crop/metric evidence is in `evidence/native-image-area-oracle.json`; raw
screenshots/RGBA remain private ignored laboratory artifacts. This confirms the
saved opaque case only. Fresh full native/browser runs now pass in both stock engines after the passive
convergence guard described below.

Nine new CPU tests cover checkerboard minification, exact fractional crops,
alpha composition and input immutability, unchanged screenshot channels,
UV/detail/ten-level RGB controls, authored hole classification, allocation and
crop limits, tiny invalid footprints, and floating-point white-channel bounds.
The six original pixel-oracle tests also pass, including genuine dark source,
flat/missing/UV negative controls and linear-light alpha. RGB MAE≤10,
correlation≥0.9 and all original/compressed/cross-engine mask thresholds are
unchanged. Existing actual PNG/source SHA checks, native resource/render-frame
readiness, source hashes and save-before-assert behavior remain in the runner.

## Actual passive native convergence

The first actual deterministic-area Chromium cohort passed all four cases.
Firefox exposed a genuine remaining native TAA readiness problem: its native
original/compressed mask mismatch was 1.8799%, above the unchanged 1% limit.
The browser pair passed. Three frames after FINISHED did not establish a stable
native presentation. That failed cohort remains in the runtime evidence.

The author now reads the existing native antialiasing mode, stopped and frozen
state without modifying it. The pinned normal renderer uses a 16-sample Halton
sequence. TAA captures require at least sixteen newly completed native frames;
non-TAA requires three. Unknown or unavailable state refuses readiness. The host
requires three same-case captures, spaced by the native frame guard, with
pairwise RGB delta at most 0.5 and mask delta at most 0.25%. It allows at most
eight captures within the original thirty-second case deadline. These additional
readiness checks do not alter the final source, pair or cross-engine thresholds.

Fresh source-coherent Chromium154 and Firefox156 runs pass original/compressed
opaque and authored-mask images, source detail/color, both pair comparisons and
cross-engine comparisons. Both independently verified deletion of their four
owned fixtures and preservation of the seven original domain entities. Firefox's
native mask pair mismatch is 0.07324%, and its native opaque original source
correlation is 0.992857. Fifteen convergence/fixture contracts pass. Exact native
version, binary/source hashes, three-capture deltas and retained failures are in
[evidence/native-image-runtime-20261001.json](evidence/native-image-runtime-20261001.json).
This proves these unlit fixtures; lit, pulse, sub-image and complete native feature
parity remain separate acceptance work. No audio or public-world writes occurred.
