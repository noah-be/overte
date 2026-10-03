# Opt-in native avatar diagnostics

Use the existing Browser client workflow's manual `avatar_sample_diagnostics`
input to investigate a native peer's stale browser pose. It defaults to false.
The normal workflow and all original core-journey assertions remain unchanged.

```sh
gh workflow run browser-client.yml --repo noah-be/overte \
  --ref feature/main/browser-client \
  -f startup_diagnostics=false -f avatar_sample_diagnostics=true
```

Dispatch only after reviewing the exact source and confirming the fork/ref. The
input enables the existing full sampler before isolated laboratory preparation.
Startup-only diagnostics omit this sampler and its collector. This is a
controlled managed-domain measurement, not public-world or device acceptance.

After the original stop and evidence curation steps, the workflow adds
`native-avatar-samples.json` to the existing `native-core-journey-evidence`
artifact. The collector uses the unchanged production projection and only the
last 1 MiB and at most 512 accepted rows of each owned native/gateway log. It
discards incomplete lines and reports tail and row censoring explicitly. It
refuses unsafe files or metadata changes rather than exporting partial raw data.
No raw log, path, avatar name, session identifier or credential is included.

Compare publication pose age, rig phase/timing, post-publication pose delta and
receiver position counters with the retained failed core journey. A recently
arrived browser snapshot does not establish when its native pose was sampled.
Two projected sources can overlap; their counts must not be added as independent
observations. Full sampling has observer overhead, and neither Stats freshness
nor native packet delivery is established by these counters alone.

Offline replay against an already stopped, owned private laboratory is:

```sh
node browser-client/tools/curate-avatar-samples.mjs \
  --output /absolute/owned/evidence-directory --commit-sha FULL_TESTED_SHA
```

Run from the repository root. The input root is fixed to `build/browser-lab`;
the output directory must already exist and be owned and protected against
group/other writes. Publication is exclusive and refuses an existing output.
This command starts no browser, native process, domain or service. Its report is
diagnostic evidence and cannot turn a failed acceptance assertion into a pass.
