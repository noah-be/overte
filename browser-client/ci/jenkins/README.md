# Proposed isolated Jenkins native/browser qualification

Historical exact-source qualification: commit
`09c062bf5a371df78b01014dccfdbc4c37febcb9` executes all nineteen gates in build6.
Eighteen pass, including194 renderer tests and the complete Firefox core journey
with synthetic voice in both directions. Chromium fails the original
second-participant movement assertion; complete CI acceptance remains open.
See [the actual gate evidence](../../../docs/browser-client/evidence/jenkins-ci-09c062-checkpoint-20261002.json).

The integration harness now stamps the original avatar records through a private
WeakMap, captures the existing last snapshot once after the unchanged2,800ms
command delay, and uses those exact captured avatars in the original assertion.
One subsequent regular-file-only/no-follow read projects at most1MiB of the
owned native log into fixed numeric/boolean diagnostics matched to that exact
command sequence. There is no retry, later browser sample, new wait or relaxed
predicate. The optional curator whitelist cannot change eighteen-checkpoint
completion. Nine Node and eleven Python contracts cover capture identity,
bounded readback and safe projection; actual diagnostic CI proof is pending.

Historical setup qualification: the dedicated
`overte-browser-native-ci` job has been created through the official Jenkins CLI;
unrelated jobs, nodes, services and device configuration are preserved.
Its exact `9f8dc66e8751bb7c17f4c5f7a2123d10efba1938` build verifies the source
and fails dependency preparation because npm user/global configuration resolve
to the same empty file. None of the nineteen native gates ran in that build.
The distinct private-config correction and FIFO guard pass39 host-runner
contracts; exact-source Jenkins acceptance of the next published commit is
still required.

The helper files belong at `browser-client/ci/jenkins/` in the exact attested
fork commit. The final pipeline refuses modified/untracked policy helpers and
any remote other than `https://github.com/noah-be/overte`. It holds the single
non-root agent executor for preparation, all gates, cleanup and curation.

Dependencies are prepared in the job's dedicated checkout, without fixture
startup. The Fedora path downloads/extracts the existing reviewed artifacts and
host tools without replacing the user's audio services. Existing Node must meet
the repository engine requirement; its actual version is recorded. Browser
engines, npm configuration and caches are confined to the job checkout. Runtime
environments exclude Jenkins tokens, credential bindings, desktop display,
audio and bus settings. The actual HOME is retained without substitution.
Each preparation command uses an ordinary private PID namespace with normal
download networking and drops namespace capabilities before the installer.
Parent death destroys that owned tree, including independently grouped children.

The job then enters ordinary util-linux user/network/IPC/mount/PID namespaces.
Its UID stays non-root. Setup-only namespace capabilities are retained briefly
for private mounts/loopback, then all bounding, inherited and ambient capabilities
are dropped before any gate. Every gate verifies zero effective/permitted/
inherited/bounding/ambient capabilities. Native workers still create their normal nested
boundaries; no test is skipped and no kernel/AppArmor/browser policy is disabled.

Private `/tmp` is mandatory: the managed lab's displays 94/95, X sockets and lock
files would otherwise collide with existing visitor services even with separate
network/IPC namespaces. A pre-opened FD binds only the dedicated checkout at its
original pathname after the private tmpfs mount. This preserves prepared absolute
paths without copying unrelated files. Private resolver configuration affects
only the owned mount namespace. Slirp host-loopback access stays disabled.

Cancellation or timeout terminates only recorded Popen groups. The util-linux
parent has `--kill-child=KILL`, so destroying it kills private PID-namespace init
and the kernel removes even descendants that started their own process groups.
Both util-linux and slirp are executed with kernel `PR_SET_PDEATHSIG(SIGKILL)`
ownership. A parent-identity check after registration closes the startup race;
the commands replace their helper so their recorded process identities remain
unchanged. No Jenkins credential or cleanup cookie is copied into runtime.
Normal completion additionally runs the unchanged recorded lab cleanup. An early
failure, omitted engine, cancellation, duplicate/missing stage or cleanup failure
cannot produce a complete passing gate summary.

## Review and actual qualification order

The CPU-only contracts pass (23 cases), including real owned-child group exit,
hard-parent-death termination/reaping and startup-race refusal. The prior parent
namespace-only qualification passed in 0.645 seconds on the recorded source,
with actual nested normal isolation, all fixed ports and four zero capability
sets. The updated parent-host namespace qualification also passed in 0.503 seconds,
checking all five zero sets, parent-death-owned helpers, nested normal isolation
and the private ports/tmp. Both runs truthfully used a dirty local checkout and
reported completeCI: not-run. Installer namespace qualification initially failed
because setup capabilities were not retained until setpriv; the corrected path
retains setup authority, drops every capability and verifies the actual five-zero
result before any installer. The corrected installer qualification actually passed
as a non-root process with all five capability sets zero. Complete
Jenkins CI, GUI and voice gates remain **not run** for this candidate.

First use the explicit namespace-only smoke from a dedicated checkout. The
operator supplies the existing reviewed slirp binary path; no credentials or
private node selector enter this command:

```sh
python3 browser-client/ci/jenkins/run.py \
  --repo /absolute/dedicated/authorized-checkout \
  --source-sha EXACT_40_HEX_COMMIT --probe-only \
  --slirp /absolute/reviewed/slirp4netns --timeout-seconds 60
```

The smoke binds the actual fixed TCP/UDP ports *inside* the owned namespace,
checks clean private X socket/lock paths, proves namespaces differ from its
caller, and executes nested ordinary unshare and bubblewrap. It publishes only
`build/jenkins-browser-ci/namespace-smoke.json`, explicitly labelled
`completeCI: not-run`. Existing host service listeners must be verified unchanged
by the parent. Passing the smoke does not prove GUI, voice or complete CI.

After the policy files are included in an exact reviewed fork commit, privately
resolve the existing unique agent label with the official Jenkins CLI. Store its
value only in a canonical owned mode-0600 file under a mode-0700 directory. Create
new-job XML without printing the selector:

```sh
python3 browser-client/ci/jenkins/create-job-xml.py \
  --agent-label-file /private/label-file --output /private/new-job.xml
```

The generator performs no Jenkins mutation. Its initial XML already declares
SOURCE_SHA and disabled concurrent builds, so the first CLI-triggered build can
validate its explicit parameter before the pipeline properties() step runs. After checking that the new job name
is unused, the parent may create **only that new job** through the official CLI:

```sh
overte-jenkins create-job overte-browser-native-ci < /private/new-job.xml
overte-jenkins build overte-browser-native-ci -p SOURCE_SHA=EXACT_40_HEX_COMMIT -s -v > /private/build-console.log 2>&1
```

Inspect the completed official CLI result and only curated artifacts. Do not
publish node labels, paths, raw console logs, private XML, profiles, operator
credentials, device identifiers or audio. No blanket second full run is required;
repeat only when a failure, meaningful change or unresolved concern justifies it.

For the current Google Chrome-only schema, all seventeen required stages must pass, including the manager-state contracts,
Google Chrome worker/UI gates,
normal kernel/network preflight, an actual domain plus independent native client,
the unchanged Google Chrome/native movement/voice/interaction/reconnect journey,
source immutability and owned cleanup. The duration remains zero; endurance was
cancelled by the user. No hardware speech or public-Hub GPU fluidness is inferred.
`CI=true` prevents Playwright reusing another server. Mesa llvmpipe is the requested
software graphics backend; actual WebGL and pixels must pass the unchanged
embedded/renderer gates. It is not assumed available merely from environment
variables. The current Google Chrome curated report is authoritative for synthetic browser
audio, using controlled file input. Historical per-engine evidence remains unchanged. The independent
native test source is a synthetic 997 Hz tone, without hardware speech claims.

Keep the actual Noble profile failures and corrected Ubuntu native-GUI diagnostic
visible. This Chrome-scope amendment retains every Chrome gate and historical nineteen-stage completion checker. Firefox launches are removed under the explicit user scope change; historical evidence is retained.
Any eventual automated fork check publication needs separately reviewed trusted
orchestration and full exact-commit effective-gate evidence; no agent credentials
or public Jenkins exposure are introduced here.

The private npm user/global configuration files are opened with `O_NOFOLLOW`
and `O_NONBLOCK`, then checked through their held descriptors. This keeps a
substituted FIFO from blocking the gate before its regular-file check. Both
files must remain distinct, owned, empty and mode 0600. The isolated actual-FIFO
regression retains a negative control for the former blocking-open expression.

## Current Chrome-only preparation contract

The current runner emits `schemaVersion: 2`, `browserScope: google-chrome-only` and seventeen required rows. `REQUIRED_STAGES`/`complete_pass` retain the historical nineteen-row schema for retrospective controls. Current completion uses the separate `GOOGLE_CHROME_REQUIRED_STAGES`/`complete_chrome_pass` checker. There is no substitution of skipped stages for passes.

Apply the separately reviewed Chrome-default and explicit-executable amendments before qualifying this runner. On the dedicated Fedora agent, supply `OVERTE_CI_CHROME_PAYLOAD_MANIFEST` (absolute manifest path) and `OVERTE_CI_CHROME_PAYLOAD_SHA256` (reviewed manifest SHA-256). They are preparation inputs, not copied into gate environments. No Playwright apt installer runs on Fedora. An absent selection refuses rather than downloading Chromium or Firefox. The operator must review the official Google Chrome package provenance and the complete extracted payload before authorizing its manifest; merely having ELF bytes is not proof of Google branding.

The selected manifest directory contains `payload/` and a manifest with exactly `{version:1, executable:"chrome", files:[{path,bytes,sha256,executable},...]}`. Each file must be listed exactly once. Paths are relative with no empty/dot/parent components, symlinks or special files. Payload limits are 512 files, 512 MiB total file bytes, 16 directory levels and a 1 MiB manifest. The known extracted Google Chrome package has 254 files and approximately 457 MB, so these bounds fit the already reviewed payload. That package was not copied or rehashed by this CPU proposal. Fixed resources and locales must be included; do not reduce a complete browser to one ELF.

Preparation copies only exact hash-matched files to the exclusively created `build/jenkins-browser-ci/google-chrome` directory, mode 0700, with files mode 0400/0500. No host install, chmod of the source, download or browser launch occurs in the admission helper. Failed copies clean only their created staging output; an existing target is never replaced. The ordinary preparation-complete marker remains the runtime readiness boundary; hard interruption can leave an incomplete target that is refused on reuse.

The existing private `/tmp` mount hides external package paths. Staging inside the dedicated checkout lets the existing pre-opened checkout FD carry the payload into the same private mount; no extra host bind or namespace/capability grant is added. `run.py` records its admitted manifest identity before entering the namespace. `gates.py` revalidates every copied file and requires that same identity, then sets only `OVERTE_BROWSER_CHROME_EXECUTABLE` to the admitted executable. All five capability sets still must be zero before the helper or gates run. Runtime file hashes and ownership checks do not claim resilience against a malicious same-UID actor rewriting the entire pre-launch checkout; this remains the existing dedicated, reviewed agent/source trust boundary.

The new helper belongs to `SOURCE_FILES`, so full CI requires exact Git-committed bytes and namespace-only smoke stages copy it with the other reviewed helpers. A new Chrome scope test module is imported by the existing runner test entry point and therefore its ordinary npm contract. Actual supplied-package dependencies, isolation, GUI, synthetic voice and all seventeen stages remain unqualified until the parent executes a fresh exact-source Jenkins run. Historical Firefox evidence is not a current launch prerequisite.
