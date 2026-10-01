# Offline skinning regressions

`skinning-SkinningTests` runs real glTF/FBX serializers, HFM palette preparation,
the model baker, graphics attribute packing and skeleton bind lookup. All fixtures
are generated in memory; no fixture downloads, service ports or device accounts
are required. The large-scene control has 200 nodes and two used joints with
nonidentity inverse binds. Other cases cover distinct skins sharing joints, rigid
nodes in a skinned scene, invalid cardinalities/weights, unused root lanes,
127/128/65535 index boundaries and supported/oversized used palettes. ASCII and
binary FBX controls also check raw source vertex indices before conversion,
including 4294967296, fractional/nonfinite values and typed 64-bit arrays.

`skinning-ShaderSkinningTests` uses the production Scribe include
`render-utils/src/Skinning.slh`, the production 450 shader headers, glslang and the
actual matrix/DQ upload layout. On Linux it executes both generated vertex
shaders through transform feedback in a surfaceless **software** EGL/OpenGL 4.5
context. It checks actual uploaded counts, shorter/empty palettes, zero-weight
invalid lanes, no valid influences, degenerate DQ accumulation, polarity,
nonuniform scale, normals, tangents and cauterization. Missing EGL headers,
library or software context fail the Linux native gate; they are prerequisites,
not a reason to report passing shader verification. This test is not physical GPU
or device acceptance.

The shader executable also links the actual entity renderer. Consumer regressions
initialize the real Model/Rig and check ordinary/cauterized render-payload bounds
against animated mixed weighted/zero-weight vertices and software shader output.
They call `RenderableModelEntityItem::computeShapeInfo` for static-mesh and
simple-hull collision, checking a rejected first mesh followed by a rigid mesh
translated +5, alongside the supported-palette control. These are offline geometry
and shape-data tests, separate from a full Interface or physics/device run.

Both executables are registered in `.github/native-tests.json` and use the normal
production CMake graph. From a configured full native build:

```bash
cmake --build build/native --target skinning-SkinningTests skinning-ShaderSkinningTests --parallel 2
ctest --test-dir build/native -R '^skinning-(SkinningTests|ShaderSkinningTests)-test$' --output-on-failure --no-tests=error
```

## Producer and shader contract

HFM stores exactly four indices and four quantized weights per actual skinned
vertex. Before baking, genuinely used cluster objects and their vertex indices
are compacted together; global skeleton joint indices and both inverse bind
representations remain attached to their original clusters. The runtime skeleton
and matrix/DQ updates therefore consume the same ordering as packed vertices.
Inactive lanes are canonicalized before narrowing. All-zero vertices keep zero
weights and use the shader's finite bind-space position/normal/tangent fallback.
A skinned mesh remains weighted even when compaction produces only one or two
clusters; rigid local transforms are selected by the presence of skinning
attributes rather than palette length.

Skinned render bounds conservatively include the original local bound as well as
the cluster-transformed bounds, so bind-space fallback positions remain visible
when all joints move away. Rigid bounds retain their existing transformed bound.
Rejected meshes retain their original slots; collision geometry selects each
surviving mesh's transform using that original slot rather than a count of valid
meshes.

A used palette above 128 is explicitly rejected, without splitting, clamping or
truncation. Invalid influence cardinalities, active indices outside the actual
palette and invalid used joints/binds are also rejected before packing. glTF
influence sets beyond four lanes and FBX vertices beyond four active influences
are unsupported and rejected explicitly. FBX unpainted vertices retain its
explicit mesh/root influence; its inactive root lanes do not require that root
in the used palette.

FBX cluster source indices must be nonnegative integral values representable as
an `int` before conversion and within the actual source vertex domain afterward.
ASCII indices use checked decimal integer parsing; binary scalar/array numeric
values are checked before narrowing. Parse failures reject the malformed input
with a bounded diagnostic instead of admitting a wrapped vertex index.

Ordinary and cauterized uploads bind the complete std140 block and its actual
populated count. A count/mapping mismatch or oversized upload clears the old
buffer and prevents drawing. Every shader load requires a positive finite weight
and an index below both the actual count and the supported bound. DQ polarity
uses the first usable weighted lane. No usable influence or degenerate/nonfinite
DQ norm returns the input bind-space vertex and directions without division by
zero. Valid matrix/DQ blending and cauterization retain their existing formulas.
