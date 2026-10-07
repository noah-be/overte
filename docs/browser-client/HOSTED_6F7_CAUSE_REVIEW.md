# Hosted prerequisite failure attribution, exact image 20260927.320.1

This records source and protected-log evidence from checkpoint `6f7a35d`. The public descriptor fixture correction and failure-only provenance helpers are integrated locally. Hosted execution of those changes is pending; they do not establish Linux qualification. Raw private logs and account or participant data are excluded.

## Exact image source association

All three authorized hosted logs report Ubuntu24.04 image **20260927.320.1**. The official [ubuntu24/20260927.320 release](https://github.com/actions/runner-images/releases/tag/ubuntu24%2F20260927.320) reports that version and points to commit **1275e33f5019b02660b81ecc5622fe196211fa89**. At that exact commit, [configure-system.sh](https://github.com/actions/runner-images/blob/1275e33f5019b02660b81ecc5622fe196211fa89/images/ubuntu/scripts/build/configure-system.sh#L10-L13) sets `/usr/share` recursively to0777. The commit's [image readme](https://github.com/actions/runner-images/blob/1275e33f5019b02660b81ecc5622fe196211fa89/images/ubuntu/Ubuntu2404-Readme.md) independently names the same image version.

This is a primary-source image configuration cause consistent with the actual UTC regular-file mode, not a speculative package extractor failure. Current repository stage/keyring extraction reads only exact regular tar members and writes fresh owned no-follow descriptors; the installer changes fresh descriptor modes. No source path was found that copies a symlink's0777 mode onto the external UTC target. No exact UTC package-content attestation was obtained in this review.

## Separate measured failures

Both browser logs show81 Python tests,3 failures and4 errors. Six individual test methods plus `Workflow.setUpClass` account for those outcomes.

Five methods use the public fixture constant `/usr/share/zoneinfo/Etc/UTC`:

- `test_actual_root_owned_public_descriptor_hash_and_size_match_independent_digest`, line164: `rooted` rejects before digest publication.
- `test_real_build_nonzero_inventory_binds_exact_profile_manifest_header_and_static_binary`, line227: same early fixture refusal.
- `test_descriptor_metadata_mutation_refuses_and_owned_fd_closes`, line195: the early mode refusal prevents reaching the intended mutation rejection.
- `test_actual_c_descriptor_hash_accepts_matching_reviewed_bytes`, line326: the exact C gate refuses the same descriptor.
- `test_actual_c_read_count_and_total_bytes_are_bounded`, line344: the same C refusal prevents reaching the successful repeated-read budget.

Actual projected target metadata is regular,root-owned,114bytes,0777,group/other-writable,within size bounds,entry0/ancestor0. The refusal is correct. Original code does not chmod that fixture. Do not repair a test by accepting or chmodding this global file, overlooking a writable ancestor, or masking descriptor errors.

The sixth method, `test_installer_recomputes_inventory_and_hashes_before_mutation` line204, and `Workflow.setUpClass` line26 independently fail while inventorying an actual root0644 shared-library alias above4MiB. The fixed canonical-name diagnostic is `python312-shared-library-name`/`usr-library-directory`,aliasordinal3. Its target size is censored at4194305; no exact larger size or loaded-library identity is established. Native CLI inventory has the same category. This is not the114byte writable UTC failure. The4MiB/alias-count/total-read bounds remain unchanged.

Atomic preflight's original own-child eight-second command exits127 with no milestones. Its original safe projection reports `capability-action-refused`; a private stdout/stderr prefix is retained. That identifies a failure category, while the exact failing suboperation, executable and full prerequisite cause remain unproved. The earlier frozen evidence packet predates this additional projection review. No interpreter, security, timing or deadline change follows from the category.

## Narrow next correction

For the five public-descriptor fixture methods, use a fixed existing root-owned immutable small packaged file beneath `/usr/lib`, or explicitly stage a reviewed signed fixture beneath a locked root-owned path. Preserve every original digest/size/metadata-mutation/FD-closure/ancestor/read-count assertion and add the measured UTC0777 refusal as a negative. The fixed nested systemd basic.target file is a candidate because it retains the nonzero inventory's explicit necessary-parent read rule; choosing a shallow os-release file without preserving that assertion would drop useful coverage. Current Fedora metadata qualifies that candidate's structure; actual hosted metadata and any required package-content authentication remain pending. No production privilege or file grant is changed by a test fixture correction.

Reinstalling only UTC is insufficient if `/usr/share` itself remains writable; original `rooted` checks every ancestor. Blanket mode changes are excluded. A signed private bootstrap must authenticate exact package/release/index/member bytes, create fresh root-owned no-follow directories/files, verify immutable canonical ancestry and bind the selected fixture's source hash. Existing keyring/member extraction can supply an architecture pattern, not an unreviewed generic archive extractor.

For the shared-library alias, current diagnostics retain the canonical target name but not the lexical symlink path or loader dependency. Thus they do not prove a development-config-only link, nor that the bytes are an already authenticated loaded runtime dependency. Inventory currently walks all entries, and the profile can read the entire approved import root. Skipping a config path without enforcing an equivalent read exclusion would weaken that trust boundary. A separate signed package/loader/lexical-link audit is prerequisite to any narrowly bounded architecture change.

No complete hosted success is claimed.
