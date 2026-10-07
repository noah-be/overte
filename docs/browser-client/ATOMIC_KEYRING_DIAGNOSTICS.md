# Fixed keyring staging subphases

The actual hosted checkpoint failed with `owned-atomic-dependency-staging`, phase `keyring-read`, category `validation-refused`. That combined phase does not establish whether ownership, writable mode, regular-file/size bounds or another original operation refused. No hosted metadata or cause is invented here.

This two-file source-only amendment retains the original resolve/stat operations at `keyring-read`, followed by fixed `keyring-ownership`, `keyring-write-permissions` and `keyring-bounded-regular` labels. The original allowed owners (root or the current user), group/world write refusal, no-follow bounded regular read (one MiB), all error strings, digest/signing fingerprint/archive/executable checks, subprocess arguments and deadlines are unchanged. The original combined OR is split in its original short-circuit order; ownership refusal still does not read the mode. A keyring disappearing before its later bounded read still yields the original trusted-keyring-unavailable classification.

The projection continues to publish only known phase/category and an already permitted bounded HTTP status. It never publishes a path, UID, owner name, permission bits, size, exception text, argv, tool output, signature policy or environment. No install, permission adjustment, alternate keyring, source trust expansion or archive gate change occurs.

## Local proof

All original 45 contracts plus seven new tests pass: 52 total, no failures/skips, 2.534 seconds. They use the already reviewed local signed Noble Release/index/package cache and public archive keyring; no live download. The additional cases exercise original untrusted ownership with mode getter deliberately unreachable, original group/world-writable flags, root/current allowed ownership through the genuine cached signature chain, actual oversized and FIFO keyring reads, missing-file classification after original stat, and private-data-safe phase projection. Existing changed digest, failed signature, extraction, source/fork, strict archive and curation refusals remain exercised.

An initial staged harness had symlinked companion metadata; the original O_NOFOLLOW guard correctly rejected those links before reaching the keyring. Only TMP companion files were replaced by byte-identical regular copies, with no guard or Root change. That negative is retained in `initial-harness-negative.json`; it is not a hosted keyring finding. Raw local test output remains private and is not part of the public patch.

## Parent-owned next step

Apply only `atomic-keyring-subphases.patch`, publish its exact reviewed commit and let the original hosted atomic job run unchanged. The fixed failure phase distinguishes the original branch. If ownership or write permissions fails, first verify the actual signed package/file state and repair only that trusted preparation boundary without accepting an unsafe keyring. If bounded regular fails, retain the same no-follow/regular/size constraints. If resolve/stat still fails, preserve that classification and diagnose the actual original operation. No generic validation failure authorizes weakening a check.

Validation command: `python3 -B -m unittest discover -s . -p 'test_*.py'` in the staged atomic-provisioning folder, using the parent-provided `ATOMIC_DIAGNOSTIC_CACHE`, `ATOMIC_DIAGNOSTIC_STRACE` and `ATOMIC_DIAGNOSTIC_TEST_KEYRING`. Interpreter parsing of both changed files and exact Root `git apply --check` passed. No absolute local dependency path is added to test source. Other current modules and policy records were copied byte-identically only for the local test and are excluded from the patch.
