# Exact screenshot color encoding qualification

The retained stock Chromium 154.0.8037.57 failure-page PNG includes one 480-byte RGB/XYZ ICC profile. Its SHA-256 is `883a0b8b9fd4ed2381bf911b9ec7f5e59e93ae01440c34e9447aca0557a0b6e1`. The matrix equals Skia's exact fixed-point sRGB/D50 matrix; all three curves are ICC parametric type 0 with gamma `144179/65536`. The authored canvas remains `[40,80,100,255]`. Applying the sRGB decoding curve followed by the inverse gamma curve and 8-bit rounding produces exactly `[44,81,100,255]`, matching the retained strict failure.

The prior element screenshot was not archived before assertion, so that original failure remains unqualified. The fresh two-case stock Chromium followup now passes in3.589s: both actual element PNGs carry the exact reviewed480-byte profile, and the independently calculated encoded pixel matches exactly. Real trusted input, denial/delegation, source coherence and owned cleanup pass. [Actual element-profile proof](evidence/fullscreen-actual-element-icc-stock-chromium-20261002.json).

The followup reads color metadata from the actual element PNG. It verifies the complete profile hash, size, header, complete tag inventory, exact matrix/white-point data and all three curves before calculating the expected integer sample. Profile names are never an admission token. Unknown profiles, duplicate or conflicting color metadata, invalid compression and unsupported transparency/animation metadata refuse. For the already-qualified untagged authored fixture or explicit sRGB, the original exact `[40,80,100,255]` expectation remains. There is no color tolerance, brightness mask, forced profile, viewport/DPR/quality change or calibrated value taken from the observed pixel. The encoded center and its alpha must equal the independently computed result exactly.

Private element screenshot bytes are saved before assertion, with fixed filenames under the existing canonical visitor-owned 0700 output directory, `O_EXCL|O_NOFOLLOW|O_NONBLOCK` and mode 0600. Input is capped at 4 MiB. Metadata/ICC inflation is independently bounded; private screenshot bytes are not part of this patch. The CPU fixture contains only the generated 480-byte color profile, not a captured image or participant/device metadata. Reports project its fixed encoding class, hash, gamma and matrix. The original failures remain evidence.

The original physical click, press/release production-wire proof, authored canvas reads, policy/API assertions, ownership checks and 45-second case deadline remain unchanged. The existing setup bound is still ten seconds. The only driver addition to `c007015b...` passes the fixed private PNG path into the existing setup observation; source recovery tests require exact recovery of that driver, its passive predecessor and the original registered body. A screenshot still does not prove compositor hit-target readiness.

Primary sources:

- [PNG iCCP specification](https://www.w3.org/TR/png-3/#11iCCP) defines embedded profile semantics and compression.
- [ICC.1 v4.3](https://www.color.org/specification/ICC1v43_2010-12.pdf), section 10.16, defines parametric curve type 0 and fixed-point parameters.
- [Chromium 154 screenshot encoding](https://github.com/chromium/chromium/blob/154.0.8037.57/content/browser/devtools/protocol/page_handler.cc#L103) selects the bitmap PNG encoder.
- [The same release's PNG codec](https://github.com/chromium/chromium/blob/154.0.8037.57/ui/gfx/codec/png_codec.cc#L167) preserves pixmap color-space information through the Rust encoder.
- [Its exact Skia dependency](https://github.com/chromium/chromium/blob/154.0.8037.57/DEPS#L314) is `2466dcf3937437e217e7f284afe0e1aae15891ce`.
- [Pinned Skia PNG encoder](https://github.com/google/skia/blob/2466dcf3937437e217e7f284afe0e1aae15891ce/src/encode/SkPngRustEncoderImpl.cpp#L257) emits an ICC profile for non-sRGB color spaces.
- [Pinned Skia transfer functions and fixed sRGB gamut](https://github.com/google/skia/blob/2466dcf3937437e217e7f284afe0e1aae15891ce/include/core/SkColorSpace.h#L120) supply the matching source equations and matrix.

Run the three affected CPU suites with Node's ordinary test runner. Actual Chromium qualification passes for this exact followup. Current ICC-aware Firefox qualification remains pending; its earlier composed cases passed. Chromium's previous strict color refusal remains preserved.
