# Shared Jenkins control plane

This directory provides the portable Jenkins wrapper for the device-control
plane. Jenkins supplies scheduling, an exclusive target lock, credential
binding, time limits, and quarantined result publication. Test scenarios and
adapter behavior remain in the shared `tests/device` contracts.

R10 does not configure a real laboratory. Agent labels, lockable-resource
names, credential identifiers, fixture ports, target selectors, and populated
target files are private deployment inputs. They must be supplied by the
Jenkins job and must not be committed, logged, or archived. The example target
generator creates disabled templates only.

## Reproducible inputs

The root device toolchain lock pins Jenkins LTS, the Plugin Installation
Manager, and their artifacts. `plugins.txt` lists the direct plugins;
`plugins.lock.txt` is the exact resolved closure; and
`plugins.artifacts.lock.json` records the artifact URL, required core, and
SHA-256 for every resolved plugin. The direct list must match the root
toolchain lock's direct set. The resolved version and artifact locks must
contain the same full closure, with plugin IDs deterministically sorted;
`plugins.lock.txt` otherwise preserves the Plugin Manager resolver output.

Validate these inputs without downloads or device access:

```bash
python3 tests/device/validate_toolchain_lock.py
python3 -m unittest discover -s tests/device/jenkins -p "test_*.py"
```

Artifact-lock regeneration is a review operation, not a pipeline side effect:
resolve `plugins.txt` with the pinned Plugin Installation Manager against the
pinned Jenkins WAR in a fresh temporary directory, request exact versions with
`--latest=false`, hash those temporary artifacts, write the sorted schema-v1
document, and compare it with `plugins.artifacts.lock.json`. Never resolve into
or modify a persistent Jenkins/plugin cache.

## Job configuration

`Jenkinsfile` maps only canonical job names to shared adapter profiles. All
deployment-specific values are mandatory external parameters. Validation
happens before a target session or device lock is entered. Target selectors
are obtained through Jenkins Secret Text binding and are never interpolated
into shell command text or emitted to logs and diagnostics. The Python runner
passes the selector as a separate argument only to the shared adapter contract.

`jobs.json` is the checked-in migration inventory. `migrate_job_config.py`
transforms exported job XML locally while preserving unrelated XML fields; it
does not contact Jenkins. Review the generated XML before applying it with the
official administrative workflow. This repository code never creates,
enables, or triggers a Jenkins job by itself.

The pipeline executes device-free contracts before any selected target run.
The stability campaign is explicit opt-in, bounded, and fail-fast: every
iteration is reported separately and Jenkins retry wrappers are intentionally
forbidden. Upgrade and evidence gates likewise remain disabled unless their
declared inputs are present. Evidence state is evaluated from the checked-in
acceptance policy; this package does not embed historical acceptance values.

## Isolation and publication

Android build entry points use job-private workspaces and Conan state as
described in `CONAN_CACHE_ISOLATION.md`. The helpers refuse unsafe roots and do
not repair or delete a shared cache.

`run_ci.py stage-results` treats the target selector as a quarantine sentinel.
It scans both the source result tree and the copied staging tree, including
path components and regular-file contents. A match, symlink, special file, or
scope escape replaces publication with generic redacted diagnostics and an
error JUnit file. Only the explicit result allowlist is publishable; raw
screenshots, private target configuration, receipts, and build artifacts are
not.

Cleanup is bounded to marker-protected per-build paths and is idempotent. A
cleanup failure remains a build failure and must not be hidden by a retry.
Hardware runs, device jobs, and laboratory mutations are outside the scope of
the device-free checks above.
