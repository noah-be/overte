# Remaining native Image proof

This proposal adds an opt-in lit cohort to the existing real isolated-domain
Image test. It changes no browser material or native rendering defaults. CPU
checks establish fixture/oracle behavior, not native GPU/browser acceptance.
Material AI assistance: OpenAI Codex. Parent review retained the strict lit oracle.
Native default environment and the browser fixed lighting are not synchronized;
any failure is whole-scene parity evidence and cannot identify the material alone.

## Source findings

Pinned native f91d15a RenderableImageEntityItem.cpp is unchanged in this topic
(SHA-256 baa83332ee74f1c6f18a8b085ce6a791d5632a5ab96c146bec8d51e759135bb3).
It maps emissive to material unlit state, applies color/alpha/pulse, classifies
transparency from alpha/pulse/native GPU usage, applies sampler/subImage and
optionally preserves source aspect ratio. Its unchanged simple.slf shader
(SHA-256 b98da9e7ff571e83b5ab291ebfb9fd0f406a24378f98edc0469ccd90cc32d197)
evaluates global/local lighting in its non-unlit branch.

The shipping browser Image path uses MeshBasicMaterial for both emissive states,
always sets transparent:true and ignores these other Image-specific properties.
Changing tone mapping alone cannot establish lit parity. Existing native-image
cases all use emissive:true; they prove neither lit nor pulse/subImage behavior.

## Existing and proposed runs

The standard gateway/lab must already provide the isolated seven-entity domain
and normal native renderer. No other GPU cohort may overlap. From browser-client,
use the established stock-browser executable/library and DISPLAY environment:

```sh
OVERTE_IMAGE_LIGHTING=unlit node tests/integration/native-image-state.mjs
OVERTE_IMAGE_LIGHTING=lit node tests/integration/native-image-state.mjs
OVERTE_LAB_BROWSER=system-firefox OVERTE_IMAGE_LIGHTING=lit node tests/integration/native-image-state.mjs
```

Only unlit/lit are accepted; malformed options fail before fixture writes. Both
cohorts retain the same four expiring owned entities, exact own-ID cleanup and
seven baseline IDs. Actual native data arrives through the cookie-authenticated
gateway. No synthetic browser image, replacement light or material is supplied.
Actual native/browser entities must agree on emissive mode and case URL.

The default unlit absolute source-color oracle is unchanged. Lit source detail
and orientation require correlation >=0.9 and mask mismatch <=3%. Source colors
cannot be treated as unlit expected colors under real incident lighting.
Actual native/browser lit readbacks additionally require RGB MAE <=10,
correlation >=0.9 and mask mismatch <=3%. Original-versus-KTX remains RGB MAE <=10
and mask mismatch <=1% independently in each renderer. Screenshots/measurements
are saved before assertions. FINISHED readiness, actual post-FINISHED frames,
full 16-frame TAA cycle, three pairwise-stable captures, maximum eight captures
and the original 30-second readback deadline remain unchanged.

These cases should expose the current lit material defect. Do not mark their
failure as acceptance or substitute a browser-only lighting scene to pass.

## Next property cases (not implemented or verified here)

- subImage: author {x:192,y:0,width:384,height:768} on the audited opaque 768x768
  source, keepAspectRatio:false. Derive expected UV using native integer
  original-to-loaded size scaling and half-texel inset; compare authentic
  original/KTX modes at existing thresholds. Full-source/UV-reversed crops are
  negative controls.
- Constant pulse: min=max=.5, period=2, colorMode:'in', alphaMode:'none', then a
  separate alpha-mode case. This is a native phase-independent pulse case.
  Multiply pulse into the native sRGB tint first, then decode that tint into
  linear color before multiplying the linear texture. Alpha pulse separately
  scales opacity before blending over existing magenta. Ignored pulse must fail current colors/mask thresholds.
- Changing pulse: attest actual entity created time and snapshot/render time.
  It needs its own bounded temporal oracle; static three-frame convergence is
  inappropriate for intentionally animated output. Wall-clock sleeps do not
  establish native phase.
- Aspect/sampler/color/alpha: explicit natural-size and half-texel cases are still
  required. Preserve independent sampler ownership and authorized real updates.

Published advanced material/environment parity remains pending; this proposal
makes no full-client completion claim.
