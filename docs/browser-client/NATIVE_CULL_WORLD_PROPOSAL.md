# Native culling / fixed-CCW World proposal

This is a narrowly reviewed opt-in proposal, not an activated optimization.
CPU contracts pass; actual World GPU cases, a native mirrored reference and
real Hub fluidity measurements remain pending. No speedup is claimed.

The World patch applies to the source hash in `NATIVE_CULL_WORLD_BASE.json`.
Apply that patch and listed files, not this snapshot's complete World. The
constructor captures `nativeCullDefaults: true`; normal entry points remain
unchanged. With the option absent, materials, index order, staged geometry and
rendering remain on the previous path. The opt-in adds no viewport, resolution,
LOD, lighting, texture, transparency threshold, material color or asset change.

Native `graphics::Material` defaults to CULL_BACK. FBX material creation retains
that default, while glTF `double_sided` independently selects CULL_NONE. The
source references and exact installed Three behavior remain documented in the
frozen `NATIVE_DEFAULT_CULL_REVIEW.md`. In World, fresh native Material/FST
templates and known solid primitives use that default. Explicit NONE/FRONT/BACK
wins; an unknown explicit mode retains the old side. Imported glTF sides remain
unchanged. Image/Text double-sided paths remain unchanged. Quad/Circle's current
one-plane geometry is excluded until native flattened closed geometry is
implemented. Native alpha setup runs before culling on fresh templates; no
foreign shader or zero-light wrapper is authorized by the new code.

Native uses fixed CCW, whereas Three reverses its front-face convention when
the complete object transform has negative determinant. A native material side
change alone is therefore insufficient for mirrored nodes. The frozen owned
static helper creates a bounded, deduplicated index clone, reversing the first
two indices of each triangle while retaining authored triangle order,
attributes, groups and materials. It evaluates full world matrices, including
the final entity normalization and parents. Positive meshes remain untouched;
skinned/instanced/batched/unaligned negative meshes explicitly report unsupported
parity and retain prior winding. Native animated sign changes remain outside
this static proposal.

The current loader publishes copied physical triangles early while image work
continues. Compensation therefore runs after the final normalized entity has
committed, before shader warmup or static batching. ModelResources captures
before/after and releases only replaced owned geometries, retaining attributes,
materials and textures still in the root. Converted indices invalidate only
that owner's copied BVH so the existing final collider update rebuilds it.
The contact/support math is winding-independent; a CPU regression checks real
floor support before/after, without bounding-box substitution. Positive models
keep their early BVH. Both the world and reader AbortSignal guard preparation,
and removed owners cannot publish new state. Source graph/parity/geometry is
checked before subsequent batch rebuilding after restoring the old batch.
Existing batching excludes negative child transforms, so transformed batches
cannot accidentally reinterpret the reversed index convention.

Validation:

```sh
node --import tsx --input-type=module -e 'await import("./src/native-default-cull.test.ts"); await import("./src/native-static-winding.test.ts"); await import("./src/world-native-cull.test.ts");'
./node_modules/.bin/tsc --noEmit
npx playwright test tests/world-native-cull.browser.spec.ts --output ../build/native-cull-world-results
```

The 19 CPU cases cover four default-state contracts, eight transactional static
winding contracts and seven actual World factory/resource/collision/lifetime
contracts. The prepared two-engine World GPU test loads the same independently
authored indexed positive/mirrored glTF as the native reference. It uses actual
World loading, normalization, native material replacement and shader warmup;
no loaded material or geometry is patched to achieve expected pixels. Six
BACK/FRONT/NONE/default and lit-facing cases assert authored face dominance,
front/back normal sign, vertex colors, two actual draws, and stable material
versions/programs over 20 renders. Controlled fixture lighting does not claim
native Zone support or exact native/browser PBR color equality.

Run the preserved `native-winding.mjs` observer proof with four short-lived
owned private-domain entities before accepting native mirrored parity. Its
independent native pixels are required in addition to component tests. Then
enable the World flag in a reviewed production experiment and measure strict
stock Firefox/Chromium Hub cohorts at unchanged DPR and existing functional/
fluidity gates. A failed gate remains a failure; no quality reduction is part
of this proposal.
