# Native default culling and mirrored static meshes

This is an unintegrated source proposal. The current browser and native-client
pixel proof covers explicitly declared culling on a positive transform. It does
not prove native defaults or mirrored models. The new 12 CPU contracts pass. The prepared GPU fixture must
run before any World integration; an actual native-client mirrored fixture is
also required. No performance improvement is claimed.

## Primary sources

The reviewed Overte source is commit
`e8c7523a285b688af69955b4baef4ab95660499b` in `noah-be/overte`.
Three is the installed 0.186.1 source. Relevant native paths and source locations:

| Path | Source behavior |
| --- | --- |
| `libraries/graphics/src/graphics/Material.cpp:31` | Default material culling is `CULL_BACK`. |
| `libraries/model-serializers/src/FBXSerializer_Material.cpp:216` | FBX materials construct that default; no replacement default culling is declared here. |
| `libraries/model-serializers/src/GLTFSerializer.cpp:1578` | `double_sided` switches to `CULL_NONE`; omitted/false retains BACK. |
| `libraries/entities-renderer/src/RenderableImageEntityItem.cpp:23` | Image entity material explicitly uses NONE. |
| `libraries/entities-renderer/src/RenderableTextEntityItem.cpp:37` | Text background material explicitly uses NONE. |
| `libraries/render-utils/src/text/Font.cpp:391` | Text glyph pipeline uses BACK independently of its background. |
| `libraries/gpu/src/gpu/State.h:422` | Default front-face-clockwise flag is false. |
| `libraries/gpu-gl-common/src/gpu/gl/GLBackendState.cpp:106` | False selects fixed `GL_CCW`. |
| `libraries/render-utils/src/MeshPartPayload.cpp:356` | Parent/local model transforms are bound before indexed drawing; no determinant-driven winding compensation appears in this path. |
| `libraries/render-utils/src/CullFace.slh:16` | Native normals change sign according to actual `gl_FrontFacing`. |

Three's `src/renderers/WebGLRenderer.js:1200` derives `frontFaceCW` from
the object's world determinant. `src/renderers/webgl/WebGLState.js:754–763`
combines that flag with BackSide and changes GL's front face. Applying only
Three FrontSide therefore changes native behavior for a mirrored model.

## Narrow proposed defaults

`applyNativeDefaultCull` chooses BACK only for known solid native primitives,
native Material definitions and native FBX/FST material paths. It preserves an
imported glTF's existing double-sided decision. Image and Text background use
NONE. Recognized explicit NONE/FRONT/BACK wins. An unknown explicit value keeps
the prior state. Existing foreign/custom material hooks remain refused by the
owned render-state helper.

Current single-plane Quad/Circle approximations are excluded. Native Quad is a
flattened closed box and Circle a flattened cylinder; native Shape clamps Y,
whereas the browser currently constructs a single XY plane. Enabling BACK on
that approximation would hide faces rather than reproduce native geometry.
The browser's combined Text canvas also cannot independently reproduce native
background NONE and glyph BACK. Neither gap is covered by this proposal.

## Mirrored owned geometry

`prepareNativeStaticWinding` considers the complete current world transform,
including normalization and entity parents. For a negative determinant it
reverses the first two indices of each triangle, without changing triangle
draw order. Three's determinant flip then produces native fixed-CCW face
classification. It shares unchanged owned attribute buffers, creates a bounded
owned index clone, and deduplicates clones when multiple negative meshes share
the same geometry inside one parsed model. A positive mesh keeps its original
geometry. The caller captures `ModelResources` before and after preparation,
then calls `releaseKeeping(root)` to retain shared originals where needed.

This helper belongs before GPU uploads, BVH creation, or static batching. It is
not safe to share these attribute buffers with an unrelated world/model resource
owner. Preparation checks aborts between tiles and yields through an owned
MessageChannel. The default aggregate index allocation is 64 MiB. Invalid
indices, nonfinite transforms, changed source geometry/graph during preparation
and invalid budgets fail transactionally. No partially converted mesh commits.

Skinned, instanced, batched and unaligned negative meshes retain prior geometry
and report unsupported winding parity. Singular transforms are not a verified
parity case. The returned scope is private ownership metadata, not asset
`userData`. Repeated preparation returns that same validated scope. A changed
world parity, graph or geometry later requires reload before rendering. World
does not yet enforce that guard, so this helper is not integrated.

For double-sided lighting, mirrored compensation must preserve the original
native front/back normal sign as well as surviving faces. The prepared raw-GL
fixture tests fixed-CCW pixel/culling and stable draw/program/material state;
it does not claim complete lit-normal parity or actual native-client output.

## Required actual fixture extension

Extend the existing indexed native fixture asset with an explicit glTF node
`scale: [-1, 1, 1]`; keep its six original vertices, six indices and authored
triangle order. Test BACK/FRONT/NONE with a native Model/Material pair and
omitted culling separately. Keep native readiness, authenticated camera pose,
source asset hashes and cleanup checks. Use the existing dominance oracle for
transparency; native versus canvas absolute color mismatch remains documented
until the separate linear presentation pipeline is proven. Also compare a lit
normal-facing case before accepting mirrored double-sided lighting.

Future World integration must be a reviewed small patch on the current root
source, not a stale whole-file copy. It must retain explicit modes, alpha shader
ownership, staged geometry lifecycle, BVH construction order, material overrides
and actual output/quality. Measure a separate real Hub cohort only after these
functional gates pass; culling can reduce fragments but this review does not
establish its measured contribution to Firefox frame time.
