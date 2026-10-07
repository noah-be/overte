<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native KTX reuse audit

Direct compressed color-texture reuse is a plausible next loading optimization,
with **no runtime change or speed claim yet**. The audit reads actual retained
public Hub KTX files and metadata; stock-browser capabilities and GPU pixel/upload
comparisons still require host execution. It does not contact or modify a domain.

Five retained KTX1 assets validate through the audit-only
`browser-client/lab/audit-native-ktx.mjs`. Their full mip payloads and hashes are in
[the header audit](evidence/native-ktx-header-audit-20261001.json). The leaf uses
512×512 sRGB DXT5, ten mips and native usage flags 13 (color, alpha, mask); opaque
shrubs/trees use 768×768 or 1024×1024 sRGB DXT1, ten/eleven mips and flags 1
(color). Independently retained original PNG alpha counts agree with those native
opaque/mask classifications. Real saved `.texmeta.json` records advertise both
native DXT and sRGB ETC2/EAC alternatives, plus original PNG and version 1.
These are actual previously downloaded artifacts, not a claim of a fresh remote
availability check.

Five offline tests pass: actual leaf header/mips and Three parser comparison,
actual non-POT integer mip dimensions, hostile/truncated header/payload cases,
unknown native usage and duplicate keys, and a structurally valid version-2
metadata extension. The validator rejects unsupported endianness, dimensions,
arrays/faces, formats, invalid mip/block sizes, metadata bounds/duplicates,
unknown payload versions and unknown/inconsistent usage flags. It requires exact
file exhaustion. It is deliberately not imported by application runtime code.

The current Three KTXLoader returns the native GL internal format directly.
Actual leaf format 35919 must map to Three RGBA_S3TC_DXT5_Format 33779, with
SRGBColorSpace retained, so WebGLUtils selects the correct sRGB upload enum.
Passing 35919 directly fails Three's format conversion. The installed loader is
also permissive on invalid containers and computes fractional late mip widths
for 768-pixel images; a validated parser must floor each dimension. The
[KTX1 specification](https://registry.khronos.org/KTX/specs/1.0/ktxspec.v1.html)
defines headers, metadata and aligned mip payloads; the
[Three KTXLoader documentation](https://threejs.org/docs/pages/KTXLoader.html)
describes the loader and color-space role.

Actual stock Chrome/Firefox must expose and successfully use the appropriate
[S3TC](https://registry.khronos.org/webgl/extensions/WEBGL_compressed_texture_s3tc/)
and [sRGB S3TC](https://registry.khronos.org/webgl/extensions/WEBGL_compressed_texture_s3tc_srgb/)
formats. Extension presence alone is not sufficient: the specifications allow
RGB DXT1 to map to RGBA DXT1 with different alpha behavior on some implementations.
The 768-pixel chain includes 6- and 3-pixel mip levels; Three uses immutable WebGL2
storage and full-level subimage uploads, whose actual acceptance must be tested.
Fallback PNG must remain available for unavailable or incompatible paths.

A narrow implementation should start with **color maps only**. Native albedo and
emissive baking uses sRGB BC1/BC3; native normal baking stores XY in BC5/EAC and
requires Z reconstruction, while Three's normalMap reads RGB. Native scalar
baking stores one red channel, while Three's roughnessMap reads green. Direct
reuse of those latter maps would corrupt materials even when a compression format
is supported. They should retain PNG until separately verified channel adapters
exist. Source: TextureProcessing.cpp color/normal/grayscale processors.

CompressedTexture does not have a drawable image; its image object contains size
metadata. The existing canvas-based alpha inspector cannot consume that object.
Any compressed alpha path must carry **validated** native usage through an owned
module identity, preserving existing material eligibility and explicit opacity
mode/cutoff precedence. It must not treat every compressed texture as opaque or
let arbitrary texture userData claim a trusted shader/alpha hook. Sampler, UV
orientation, role-specific color space, imported texture transforms and independent
material clones must remain correct; compressed textures cannot rely on ordinary
bitmap flipY uploads. Pixel checks must cover orientation, opaque color and mask
coverage, not just metadata classification.

Existing session-bound asset resolution, origin validation, permission revisions,
abort ownership and resource gates should remain unchanged. A per-world compressed
source cache needs a retained **byte** budget, including views retaining an entire
KTX buffer, and independent Texture/sampler objects for materials. Authenticated
asset requests should use the same gateway route. No global visitor/account cache
or generic native file access is needed.

Using authored compressed mips can reduce RGBA upload size and avoid GPU mip
construction, but KTX can be larger on the network than highly compressible PNG.
The next proof should measure actual supported-format upload times and pixels in
both stock engines, then a frozen, whole Hub loading journey with transfer bytes,
first model/texture readiness, walking and reconnect. The failed Firefox fluidness
gates remain open; theoretical compression ratios do not establish completion.
