<!--
Copyright 2026 Noah
SPDX-License-Identifier: Apache-2.0
-->

# License and REUSE inventory

This is a factual inventory prepared on 2026-09-01, not a legal conclusion and
not a claim that any file or dependency violates a license. It records metadata
already present in the repository so later REUSE work can be reviewed against
known provenance instead of inferred in bulk.

## Repository-level material

- [`LICENSE`](../LICENSE) states that the project is licensed under Apache-2.0
  and directs readers to individual licenses for included third-party and
  platform software.
- [`LICENSES/`](../LICENSES/) contains canonical text files named
  `Apache-2.0.txt` and `MIT.txt`.
- No `REUSE.toml`, `.reuse/dep5`, or other repository-wide REUSE annotation
  file is currently tracked.
- 529 tracked files contain an `SPDX-License-Identifier` line. This count only
  describes explicit headers; it is not a compliance score.

The explicit SPDX identifiers found in those headers are:

| Identifier | Header count | Observed scope |
| --- | ---: | --- |
| `Apache-2.0` | 523 | Project source, tests, configuration, and documentation |
| `BSL-1.0` | 2 | Two copies of an OpenXR vendored header |
| `GPL-2.0-only` | 1 | Doxygen configuration |
| `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` | 1 | Vendored Qt Android source |
| `MIT` | 2 | Repository policy files |

The identifiers other than Apache-2.0 and MIT do not currently have
identifier-named text files under `LICENSES/`. That observation is a metadata
inventory item only; the applicable source distribution, embedded notice, and
license-text requirements must be verified before adding or moving any text.

## Existing component license files

The repository also carries component-local material that must remain linked to
its component during any future consolidation:

- [`docs/LICENSE_highlight.js.txt`](LICENSE_highlight.js.txt)
- [`docs/LICENSE_markdeep.txt`](LICENSE_markdeep.txt)
- [`scripts/communityScripts/libraries/axios/LICENSE`](../scripts/communityScripts/libraries/axios/LICENSE)
- [`scripts/communityScripts/libraries/materialdesignicons/license.md`](../scripts/communityScripts/libraries/materialdesignicons/license.md)
- [`scripts/system/places/fonts/LICENSE.txt`](../scripts/system/places/fonts/LICENSE.txt)
- [`tools/jsdoc/hifi-jsdoc-template/LICENSE.md`](../tools/jsdoc/hifi-jsdoc-template/LICENSE.md)

Their presence does not by itself establish metadata for neighboring files.
Keep each file in place until the component boundary, upstream provenance, and
redistribution expectations have been confirmed.

## Safe REUSE preparation sequence

1. Export a complete tracked-path inventory with file type, generated or
   vendored status, existing SPDX header, and nearest component license file.
2. Verify each vendored component against its recorded upstream source and
   revision. Record unknown provenance as unknown, not as a suspected breach.
3. Confirm the exact SPDX identifier and copyright holder before adding a
   header or repository-wide annotation.
4. Add canonical license text under `LICENSES/` only after its identifier and
   applicability are verified from an authoritative source.
5. Use file headers where the format safely supports comments. Consider a
   narrowly scoped `REUSE.toml` annotation for verified binary, generated, or
   comment-free paths instead of rewriting their contents.
6. Run `reuse lint`, review each result as a metadata question, and keep the
   resulting machine-readable inventory separate from generated build output.

Large media, fixtures, generated sources, lockfiles, and packaged archives must
not be normalized, regenerated, or migrated merely to add metadata. First prove
their source and reproduction process, then make any content change in a
separate, reviewable commit with before-and-after hashes.
