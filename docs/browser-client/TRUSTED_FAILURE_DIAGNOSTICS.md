# Trusted setup refusal phase observation

Actual hosted trusted-network setup passed its reviewed build/install/profile steps and emitted owner-ready, then exited 78 with only the original 31-byte refusal. This identifies a pre-Python failure interval but not the failed operation. Its actual cause is still unknown. This separate source-only packet adds a fixed refusal marker and a strict safe collector projection; it neither repairs a hypothesized route issue nor installs or activates a profile or trusted entrypoint.

## Preserved boundary

The installed profile is still checked before creating the user namespace; UID/GID/self maps, fresh network namespace, exact twelve RTN_PROHIBIT routes, kernel-peer and ACK/readback validation, sealed root-owned source/policy/interpreter admission, import-root verification, parent-death/subreaper/parent identity checks, ten-second setup bound, all-five capability retirement and exact authenticated FD/isolated interpreter handoff remain mandatory and in their original evaluation order. The original setup helpers and route-contract.c are byte-identical. The main's existing compound refusal guards are split only to label their already-required operations and to capture errno before cleanup. No additional argument, environment selector, executable, command, socket permission, profile or route is admitted.

On refusal, the launcher writes one fixed `OVERTE_NET_TRUSTED_FAILURE=` JSON marker followed by the original `Trusted network setup refused.` line and returns the unchanged exit 78. Successful output/handshake is unchanged. There are thirty fixed phases, including the observed owner-ready continuation: tap readiness, route socket, bind, ACK option, exact route install/ACK, readback, attestation, capability retirement, handoff/close and isolated Python exec. No field contains a raw profile, path, descriptor, PID, namespace token, capability mask, source value, argv, environment value or operator/browser identity.

`errnoObserved` is an integer from zero through 4095. The launcher clears older errno before each fixed operation and captures it before descriptor cleanup. It is explicitly an observed value, not a proven cause for semantic identity/format checks inside a helper; zero and a nonzero value must not be overinterpreted. No strerror or exception-like strings are emitted. In particular, a future independently measured kernel ACK correction must remain separate from this observation-only patch.

## Safe pipe and summary projection

The existing bounded stderr observer continues to count and retain at most its existing 16KiB tail. A small pure parser recognizes only the exact canonical C JSON wire form and one marker. Duplicate keys/markers, reordered or escaped lookalikes, unknown phase/fields/version, aliases and noninteger/out-of-range values refuse. The returned nested `trustedSetupFailure` record has exactly `version`, `phase`, `errnoObserved` and is freshly reconstructed/frozen. Original failure categories, phase/exit/signal validation, helper event limits and failure behavior are unchanged. No raw pipe data is returned.

This companion is necessary because a C marker alone would still collapse to unclassified-child-exit/byte count in the hosted safe artifact. It adds fixed context to the existing diagnostic rather than using another endpoint or artifact. Diagnostics never grant admission, alter retries/deadlines or make failure successful.

## CPU verification and remaining acceptance

All 57 trusted-network CPU contracts passed: the original 52 contracts plus five pure formatter/gate contracts. The existing real static launcher/build/hash/bundle/refusal/preload and original exact route wire contracts remain intact. The original refusal test now additionally requires the exact safe marker and still requires original refusal/exit78/no stdout/no namespace changes. Six pure Node collector/privacy contracts also passed. Commands, actual UTC intervals, exact source/patch/log hashes are recorded in `CPU_EVIDENCE.json`. Tests compile/run only pure formatters and existing pre-namespace refusal cases, plus private temporary staging validation; they never install profiles, create namespaces/routes, start Interface, signal host services or launch GPU/network workloads. The existing reviewed Fedora archive-only static libraries are CPU tooling, not Ubuntu runtime qualification.

Parent integration reviews `trusted-failure.patch` against exact before hashes and copies the two new tests. The normal trusted Python discovery and existing `gateway/*.test.mjs` discovery include them automatically. Required parent-owned hosted qualification must rebuild and root-install the exact reviewed immutable bundle through the existing workflow; no mutable workspace executable or ambient capability path is acceptable. Capture the new safe `trustedSetupFailure` alongside unchanged failure/route/helper diagnostics. Actual Ubuntu route and all-five-capability/native/own-X endpoint checks remain required. No hosted cause or fix is claimed by CPU tests.

```sh
OVERTE_SETUP_STATIC_LIBRARIES=<existing-reviewed-archive-only-directory> python3 -B -m unittest discover -s browser-client/tools/trusted-network/tests -p 'test_*.py'
node --test browser-client/gateway/trusted-setup-diagnostic.test.mjs
```

This packet was substantially authored with AI assistance and awaits independent review. The atomic-stage diagnostics are a different immutable packet and are not stacked into this proposal.
