# Full Client build performance

Measured baseline: [successful build 654](https://github.com/noah-be/overte/actions/runs/34509169726),
job 102981263425, source `db54c34b9a78b9316b406eb39ebefa2892c42674`.

| Phase | Observed duration |
| --- | ---: |
| Bootstrap Linux contracts | 119 s |
| Reusable workflow Linux contracts | 116 s |
| Full Client configure | 84 s |
| Full Client build | 3,470 s (57 min 50 s) |
| IPA packaging | 33 s |

The compiler checkpoint was restored, but sccache recorded **0 hits and 984
misses**, no non-cacheable calls and no cache write errors. It ended at 511 MiB
with a 512 MiB limit. The runner exposed 3 CPUs and 7 GiB RAM; end-of-build disk
headroom was about 78 GiB. CPU activity during compilation was high. More
parallel compiler processes on the same runner are not a demonstrated fix.

The repository Actions cache was also close to its shared limit (10,705,836,223
bytes observed on 2026-09-11). Qt artifacts/cache eviction had already forced a
host-tools rebuild in build 656. Do not evict Qt or Conan to make room for objects.

## Implemented changes

The Full Client disk cache now has a 4 GiB limit. The old 512 MiB restore remains
a seed fallback, preserving existing data and its namespace. New snapshots are
workflow artifacts, not additional large entries in the shared Actions cache.
The Qt, V8, Conan, SDK, compiler and policy inputs in the cache namespace are
unchanged. Source changes do not introduce an artificial per-build cache buster.

Object artifacts use their own bounded archive kind and retain the existing
repository-ID, producer-branch, toolchain-key, SHA-256 and extraction checks.
They restore into a separate staging directory and merge without overwriting or
deleting existing objects. Conflicting entries fail visibly and both copies are
retained. Native dependency provenance and the trusted `apple-ios` Qt boundary
are unchanged; objects are never treated as Conan closure or native acceptance.

Snapshots are created after stopping the compiler cache server, including after
a compilation failure when valid objects exist. Compiler objects are already
compressed, so their outer archive uses gzip level 1 and artifact upload uses
compression level 0. Archive failures remain visible but do not turn a successful
Full Client build into a compiler failure. Existing data is not deleted.

Before/after cache inventories and hit rates are included in runner telemetry
and the job summary. A restored cache with zero hits now produces an explicit
warning. Cache saturation supports working-set pressure as a problem; it does
**not** prove why every individual cache lookup missed. Do not claim a speedup
until a subsequent build reuses this enlarged checkpoint successfully.

## Evaluate the next runs

1. First build with this workflow: record cache restore source, hits/misses,
   object bytes and build/snapshot/upload durations. This may still be largely
   cold because the previous checkpoint was undersized.
2. A subsequent small native edit must restore the same compatible object
   namespace. Compare hit rate and Full Client duration with the 3,470 s baseline.
3. If restored objects still produce no hits, inspect actual compiler/preprocessor
   key inputs and generated headers. Do not relax compatibility keys blindly.
4. Keep the two host-contract phases for now: removing about two minutes is lower
   priority than restoring compiler reuse, and must preserve caller validation.

Pure QML/client-JS iterations can instead use
[development sync](../development/README.md), bypassing the native workflow after
one foundation IPA has been installed. Shader/native API or new Qt plugin changes
still need a full native build. No shorter build time or device parity is asserted
by the host tests.
