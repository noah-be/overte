# Foreground preparation lifetime followup

The parent integrated this followup on2026-10-01. All63 combined focused CPU
cases and twelve actual foreground GPU cases pass, including real KTX sampler
allocations and strict zero resource teardown. The experiment remains off by
default. [Current actual reports](evidence/foreground-textures-gpu-20261001.json)
do not establish public-world latency improvement. The original proposal record
below describes the agent's earlier isolated verification, not the later runtime
acceptance.

Prepared with substantial AI assistance. Apply after the frozen initial foreground proposal (`20ca10a9...`), not against the original production World. This is still default-off, source/CPU-verified only. No runtime, service, browser or GPU was launched here.

The independent review found a real owned-lifetime gap: texture preparation with shader warmup off awaited the original `compileAsync` promise directly. Aborting the private owner did not settle a stalled compiler promise. Three's already-submitted driver work cannot be canceled by this helper, but our readiness counter and model-reader listener must not remain held by it.

This followup exports the existing abort-aware readiness waiter from `graphics-warmup.ts` and reuses it for that opt-in path, with its actual original compiler promise and a 30-second bound. The unchanged default-off path still awaits its original compiler directly. Cancellation immediately rejects our wait, clears its timer/listener, releases the private owner/model-reader listener, and consumes any late driver failure. The waiter permits finite fractional millisecond budgets because existing total-deadline code derives remaining time from `performance.now`; it does not weaken the trusted caller's configured bounds.

Optional planning/queue resource refusals now have explicit private implementation classes. Only these capacity errors can fall back to the normal renderer, after a fresh approval/current-owner check. The diagnostic is informational and the fallback count observable. Invalid configuration, revocation, deadline and driver errors still propagate. A final authority check after diagnostics prevents even a callback-triggered revocation from publishing readiness. The plan and aggregate bindings are released on every path; unrelated queued owners retain their resources.

CPU verification executes physical local test copies, ensuring their relative imports exercise the candidate rather than resolving through an older symlinked source tree:

- 18/18 actual World cases: includes never-settling compiler cancellation by reader, root and whole World without resolving that compiler, prompt refusal within 500ms, zero remaining reader abort listeners/counters/texture references, deadline and consumed late rejection, typed optional-capacity normal-renderer fallback, and refusal to swallow driver/authority errors.
- 15/15 foreground eligibility cases.
- 11/11 original initializer cases.
- 7/7 original actual World shader-warmup lifetimes.
- 12/12 original sliced compiler/readiness cases.
- Full TypeScript check passed.

The first verification exposed an overly strict integral timeout check; the source was corrected to accept the same finite fractional remaining budgets already used by the original implementation. All existing compiler tests now pass against the changed helper. No test oracle, deadline, ownership boundary or source limit was weakened.

The initial proposal's actual HTMLImage/ImageBitmap/approved KTX GPU scaffold is unchanged and pending parent execution. This followup makes no GPU or loading-speed claim. Review before activation; preserve the experimental production option as off until the real visual/resource/load comparison proves it useful.
