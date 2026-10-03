# Trusted network entrypoint qualification plan (not activated)

The existing Ubuntu extra profiles must remain byte-for-byte unchanged. Both
hosted runs on fork checkpoint `09c062bf5a371df78b01014dccfdbc4c37febcb9`
reported `unshare-unpriv`, effective/permitted/bounding NET_ADMIN present and
RTNETLINK EPERM. The named setup executable is attached before CLONE_NEWUSER;
it never inherits the existing `unshare//unpriv` exec transition. Loading or
loosening that existing profile is not proposed.

Both entrypoints are statically linked; no dynamic loader processes untrusted
environment before fixed admission. The build rejects an ELF interpreter.
The candidate is not a setuid helper and does not accept command arguments. Its
only configuration input is an owned regular descriptor at FD 3. It creates
only its own user/network namespaces. The fixed C code waits for the original
slirp setup, installs the same twelve RTN_PROHIBIT routes, checks all ACKs and a
bounded complete kernel route dump, seals an attestation, retires all five
capability sets, and executes the pinned isolated distro Python interpreter.
Only root-owned, hash-checked sealed modules are imported outside the root-trusted
isolated standard-library import tree. The capability-free owner admits the
original bwrap mount/PID/IPC/UTS/session boundary and authenticates its fixed
policy. The original owner bridge, exact managed UDP scope, subreaper,
parent-death binding and cleanup remain in that stage. The added fixed native
entry guard verifies NNP, the exact distro payload label, and all five capability
sets zero before launching the exact admitted native executable.

The setup uses one exact identity-preserving UID/GID map (`id id 1`), retaining
the caller's numeric identity at the next user-namespace boundary. The trusted
gateway records the native environment from its pre-delimiter `--setenv` pairs;
immutable admission still checks every key/value and boundary. The host bwrap
launcher receives only fixed PATH and LANG, including when native Qt loader
settings are present. Native loader settings take effect after bwrap clears its
environment and establishes the original inner boundary.

The optional runtime patch adds only `OVERTE_GATEWAY_TRUSTED_NETWORK_SETUP=1`.
Without it, the current entry path is unchanged. No default activation is
proposed before all qualification gates pass. No new debug endpoint is added.

## Ephemeral hosted browser job

1. Install through the existing signed apt repositories: `gcc`, `libc6-dev`, `libssl-dev`, `binutils`,
   `python3`, `bubblewrap`, `slirp4netns`, `iproute2`, `apparmor-profiles` and the
   existing X/audio/build dependencies. Run the unchanged existing exact-package
   AppArmor preparation helper first. It must preserve every loaded policy.
2. Run the pure candidate Python and Node tests, with the opt-in unset. Build a
   private stage using `workflow/policy.py --output <private-policy-file>` followed
   by `workflow/build.py --policy <private-policy-file> --stage <new-empty-stage>`.
   This policy admits only the canonical signed distro system interpreter for the
   displayless real network contract probes. It does not grant host capabilities.
3. Inspect the frozen source hashes, generated header, exact policy, profile and
   complete stage manifest. Explicitly pass its reviewed SHA256 to the root
   `workflow/install.py --bundle <stage> --manifest-sha256 <reviewed-hash>`.
   Installation creates a new fixed root-owned prefix and adds only its two named
   profiles. Existing prefix/profile/loaded names are refused, never replaced.
   It also refuses exact existing disable/force-complain source-file markers, including dangling links, before any installation writes. It requires the exact reviewed Noble bwrap source SHA, existing enforcing bwrap
   and unpriv_bwrap profiles, signed/root-trusted interpreter/import roots and a
   no-load parser check. This is an explicit administrator operation, not native
   visitor input. No profile is unloaded automatically on partial failure.
4. Set the opt-in only for the qualification command. Apply `actual-tests.patch`
   and run `node --test gateway/network-sandbox.test.mjs`: all current actual
   endpoint, private-route, host-loopback, scoped bridge, exact managed UDP,
   forbidden UDP and abrupt-parent-death/descendant checks remain unchanged.
   The three probes now use the canonical interpreter, an owned session prefix
   and forward the sealed config descriptor; they do not introduce fake routes. The probe additionally verifies all twelve
   prohibit routes, all five native capability sets zero and native NNP.
   `preparation-diagnostics.test.mjs` keeps its scoped mocked namespace tests on
   the original default branch. The genuine network probes exercise the new
   entrypoint. All component tests, production builds and browser tests still
   need to pass. Installation success alone is not runtime proof.

## Ephemeral hosted actual native job

Prepare the existing pinned native artifacts before building the stage, without
starting any domain. Build the policy with the **actual resolved** extracted
`native-root`, Qt package root and native-input QML package root using all three
explicit options to `workflow/policy.py`. It admits the real AppRun and those
exact readonly runtime roots, plus the canonical interpreter for the real
network checks. Do not guess paths or add the runner home as a mount root.

Then install the reviewed stage once, set the opt-in in the native laboratory
job environment, and run the existing preflight and actual Chromium/Firefox
core journeys unchanged. The native/browser auth/readback, world, movement,
mutual avatar, voice, interaction, clean leave/rejoin and owned cleanup gates
remain mandatory. Preserve the private-X test and all final capabilities-zero
checks. Keep failed negative source-bound reports. The existing QSaveFile
atomic-persistence/OAuth provisioning failure is a separate unresolved gate;
this candidate does not claim to fix it.

The installer is deliberately a first-install ephemeral-runner tool. It cannot
update a live installed prefix. Future production upgrades require a separately
reviewed atomic/versioned deployment procedure. A different/stronger AppArmor
stack or a modified bwrap profile is refused; support must be demonstrated
explicitly, not guessed or weakened.

## Qualification that is still absent

Hosted startup diagnostics and their exact tested commits are recorded in
[the stabilization evidence](../../../../docs/browser-client/STABILIZATION.md).
The current identity/environment corrections still require the actual original
route/endpoint/cleanup controls and final native label/zero-capability guard to
pass on Ubuntu. Full browser/native journeys remain required. A refusal at any
boundary is a failed qualification result; installation or CPU tests alone
cannot establish working hosted confinement.
