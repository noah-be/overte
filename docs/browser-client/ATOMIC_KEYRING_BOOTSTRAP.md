# Exact private Ubuntu archive keyring bootstrap

This proposal preserves hosted run 36974530738's negative result: staging refused at `keyring-write-permissions`. That proves the original keyring stat contained group/world-write bits; its exact mode was not collected. The current [official runner image configuration](https://github.com/actions/runner-images/blob/main/images/ubuntu/scripts/build/configure-system.sh) recursively makes `/usr/share` writable (lines 10–11). This is a source-grounded explanation compatible with the failure, not an attestation of that run's exact image revision or file metadata.

The workflow downloads only the reviewed `ubuntu-keyring` 2023.11.28.1/all package from the exact official Ubuntu HTTPS URL, refuses redirects, bounds the response to 11,124 bytes, and verifies its repository-pinned SHA256 before parsing. The package identity, size and hash match the **already signed and pinned Noble Packages.xz**; the exact archive keyring member hash also matches the existing dependency.json. The repository-pinned package/member digests are the explicit bootstrap trust root. No unauthenticated host keyring or arbitrary copied trust bytes are accepted. No package installation, maintainer script or filesystem archive extraction occurs.

The authenticated archive is parsed in memory with a three-member ar allowlist; decompressed output is bounded to 128 KiB, zstd work to five seconds, and tar entries to 128. Only the single regular 3,607-byte reviewed keyring member is used. A new current-user-owned 0700 directory and O_EXCL/O_NOFOLLOW 0600 single-link file hold the result. The host keyring is never modified or read by the bootstrap. Stage.main revalidates the optional input's ownership, exact 0600 mode, regular-file type, single link and hash before copying its bytes to the existing owned staging root. The original signed_dependency implementation is byte-identical, including root/current-user ownership, no group/world-write, exact archive signature fingerprint, signed Release/index/package and executable digests.

The workflow passes the fresh keyring into the existing test suite explicitly; otherwise those tests would still reject the writable host keyring. Absent the optional input, the old strict stage.main behavior remains unchanged. The bootstrap emits only fixed schema/phase/category summaries; package/key bytes and private paths are not printed. No services or namespace/kernel policies change.

## Qualification

Parent integration runs the entire67-test suite successfully in3.620seconds
with the three original reviewed cached inputs. The portable offline proof is
[recorded here](evidence/atomic-keyring-bootstrap-offline-20261002.json).
Hosted qualification remains pending publication of the next checkpoint.

`offline-qualification.json` records the exact parent-brokered package, its authenticated member, newly created private keyring, and the original genuine gpgv/signed Noble/strace chain. The qualifier used cached signed inputs, made zero network requests, started no services, and removed its own temporary output. All original 52 tests are byte-preserved; 15 new tests bring the suite to **67/67 passing in 2.851 seconds**, with no skips. They cover signed cached metadata, malformed archive/layout/padding/size, symlink/duplicate/nonregular members, modified package/member bytes, output bounds, unsafe file/directory permissions, single-link creation, source/fork refusal, fixed failure projection, exact reviewed input and genuine fresh-keyring signature chaining.

A first draft parser incorrectly required GNU ar's trailing slash. The official Debian package uses bare padded names. The correction accepts only the same exact known member names with an optional single GNU slash. The first combined test draft also had two authored test-adapter defects (nullcontext yielded None; patched subprocess adapter recursively called itself). Both were fixed in tests without weakening runtime checks. Original negative output is retained privately. AST, YAML parse, unchanged signed_dependency and original test byte checks pass.

Hosted acceptance is **pending**. The old hosted refusal remains valid evidence and is not relabeled as a pass. Actual parent execution/publication must bind the reviewed new commit and repeat the unchanged atomic job.

## Parent review and run

Apply `proposal.patch` only when its two original-source hashes match. New files are invoked with Python; no executable-mode changes are needed. Review the bootstrap repository pins as trust policy. Then publish to the authorized fork and run the existing workflow normally. Do not chmod the system keyring or relax checks.

Local CPU qualification uses already authorized read-only cache paths through `ATOMIC_DIAGNOSTIC_CACHE`, `ATOMIC_DIAGNOSTIC_STRACE` and `ATOMIC_DIAGNOSTIC_TEST_KEYRING`; run `python3 -B -m unittest discover -s browser-client/lab/atomic-provisioning -p 'test_*.py'`. The paths are private and intentionally absent from portable evidence. The parent-brokered package is an independent read-only input, not copied into the repository.
