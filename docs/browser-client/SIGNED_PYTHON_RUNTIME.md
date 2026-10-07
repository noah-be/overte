# Signed Python runtime qualification

The trusted-network builder and installer have two explicit modes. The default
version 2 manifest keeps the existing generic alias policy. Version 3 additionally
authenticates one exact Ubuntu Python library and its interpreter. Supplying the
signed inputs selects this mode; it does not enable the gateway entrypoint or
prove that the installed hosted runtime matches them.

## Why the typed record exists

Hosted Noble metadata identifies the Python config-directory link and its
canonical library as `libpython3.12t64` version `3.12.3-1ubuntu0.17`. The library
exceeds the generic 4 MiB per-target bound. Package ownership and a matching
version alone cannot authenticate its bytes. Version 3 therefore admits only the
source-pinned signed package member after checking the entire installed file.
It does not ignore the config subtree or accept an arbitrary library by name.

The generic 4 MiB bound remains unchanged. The one typed record shares the
original limits with generic aliases: 64 unique targets, 16 MiB unique content,
16 KiB metadata, 128 alias reads and 32 MiB total alias-read bytes. Its complete
metadata and content are charged to those limits. Duplicate generic/typed
records, changed files, writable ancestry and unknown records refuse admission.

## Authentication and installed-byte checks

`workflow/reviewed-library.json` fixes the Noble release, Packages index,
architecture, package version, signing fingerprint, member paths, sizes and
SHA-256 digests. The official snapshot is
`https://snapshot.ubuntu.com/ubuntu/20261002T063000Z/`.
`prepare_signed_library.py` downloads only its fixed inputs, rejects redirects
and verifies exact byte counts and digests before creating a fresh private cache.
The keyring is extracted from a separately pinned official `ubuntu-keyring`
package. The hosted runner's writable `/usr/share/keyrings` is not a trust root.

The cache contains five files in an owned `0700` directory, with owned `0600`
regular files. Gpgv verifies the exact fingerprint using authenticated, sealed
keyring/release buffers. The release authenticates the index; the index
authenticates both packages; their member metadata and entire bytes must match
the reviewed record. Preparing this cache does not install packages or compare
the hosted installed runtime.

The builder next compares the whole installed canonical interpreter through one
checked FD before running the original isolated import inventory. The inventory
must discover the exact library, whose entire installed contents and FD identity
are checked. The installer independently replays authentication and installed
comparisons from its own root-private cache, rather than accepting a proof
boolean from the build. Generated manifest/header records must agree.

The static C setup entrypoint checks the exact runtime library again with a
bounded whole-file hash, EOF and before/after FD identity checks. It uses the
existing low-level SHA-256 primitive, without loading providers or configuration
while capabilities are active. All original import-tree, namespace, route,
descriptor, profile, native-rights and capability-retirement checks remain.

## Explicit preparation and build

From the repository root, create a private parent and fresh cache/stage names:

```sh
task_signed_dir="$(mktemp -d)"
chmod 700 "$task_signed_dir"
python3 browser-client/tools/trusted-network/workflow/prepare_signed_library.py \
  --output "$task_signed_dir/signed-cache"
python3 browser-client/tools/trusted-network/workflow/policy.py \
  --output "$task_signed_dir/policy.json"
python3 browser-client/tools/trusted-network/workflow/build.py \
  --policy "$task_signed_dir/policy.json" --stage "$task_signed_dir/stage" \
  --signed-library-cache "$task_signed_dir/signed-cache" \
  --signed-library-keyring "$task_signed_dir/signed-cache/archive-keyring.gpg"
```

Native qualification must also pass the exact prepared native/Qt/input roots to
the existing policy builder. Omit both signed-input options for version 2; passing
only one refuses. A host with different installed bytes must fail closed rather
than modify permissions, substitute a package or enlarge bounds.

Installation remains an explicit administrator operation on a fresh ephemeral
host. Follow the reviewed [entrypoint qualification plan](../../browser-client/tools/trusted-network/workflow/QUALIFICATION.md).
The current browser workflow prepares a separate root-owned cache from the
already authenticated public buffers and supplies it to the installer. Existing
prefixes, disable/complain markers and incompatible policy states are refused;
this is not an upgrade procedure for an existing deployment.

## Evidence and remaining gates

The integrated composition passed 132 local trusted-network contracts. The
official five-input preparation and an independent local-cache replay both
authenticated the fixed signatures and package members. These results qualify
the code and pinned inputs, not the installed hosted runtime or an AppArmor
activation. The earlier oversized-alias and Atomic failures remain valid
negative evidence.

Hosted version-3 installed-byte equality, parser/Px/sealed-FD mediation, actual
namespace/route/capability retirement and the original browser/native journeys
still require genuine qualification against the tested source. Cache preparation
or installation alone cannot mark those gates passed. The separate Atomic
`apply-bounding-set` refusal is not repaired by signed-library authentication.
