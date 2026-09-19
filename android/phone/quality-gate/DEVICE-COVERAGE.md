# Device acceptance matrix

Only a dedicated, explicitly configured physical Android Phone is eligible.
Use the existing `tests/device/README.md`, `CROSS_PLATFORM_OPERATIONS.md`,
`TOOLCHAIN.md` and bound Phone adapter README. No selector belongs in this repo.
All automated suites require complete capability support, current source and
candidate SHA-256 and installed-byte verification. Missing support fails.
A successful input injection alone does not prove application behavior.

| Requirement | Existing automated suite / required extra evidence |
|---|---|
| Installation, first start, no data | `smoke`; install/clear-data procedure and first-run permission outcomes must be documented on the dedicated device. The runner does not erase user data automatically. |
| Domain entry, assets | `domain-smoke`, `asset-smoke` with controlled fixtures and probe observations. |
| Movement, look, jump | `e2e-core` (also input isolation/collision/flight); actual touch gesture ergonomics reviewed physically. |
| Sound | `sound-smoke` resource/decode/injector proof; audible output and routing/microphone privacy reviewed physically. |
| Tablet, touch UI | `tablet-e2e`, `text-input-smoke`, `e2e-core`; Phone flat-touch policy. |
| Minimize/restore | `lifecycle-stability`, `lifecycle-under-load`. |
| Stop/restart | `e2e-recovery`. |
| Network loss/recovery | `network-fault-recovery`; real WLAN/AP changes need a controlled lab procedure. |
| Permission denial | `permission-recovery`; inspect microphone-denied first-run UX separately. |
| Domain leave/re-enter | `domain-recovery`, repeated in long group. |
| Upgrade | Existing `update_upgrade.py` contract is available, but bound Phone adapter deliberately disallows changing candidate identity. Supply previous/new signed versions, signature continuity, version increase, retained settings/data and new installed-byte verification as manual evidence until an approved upgrade adapter exists. |
| Screen lock/unlock | Controlled physical lock/unlock, verify rendering/input/audio and foreground recovery. Do not disable the user's screen security. |
| Unreachable domain / missing assets | Controlled fixture fault, bounded wait, usable UI, meaningful error, retry recovery; ordinary network recovery alone is insufficient. |
| Slow/unstable network | Dedicated router/network namespace or lab proxy, documented latency/loss/bandwidth, restoration in cleanup; do not change the host's default network. |
| Low storage | Dedicated disposable test target with bounded storage pressure and cleanup, prove graceful cache/write handling. Do not fill the workstation or personal device automatically. |
| Hours of use / RAM | Long group uses repeated 7200-second `stability` sessions with telemetry and memory trend reports. |
| CPU/GPU/energy/leaks | Capture local Perfetto/simpleperf/Android system profiling on the dedicated device where supported. Review CPU utilization, frame/GPU timing, PSS/RSS slope after warm-up, allocation retention, battery charge/level and thermal throttling. Document unsupported GPU counters explicitly; absence is not zero usage. |
| Repeated tablet/lifecycle/domain | Interleaved long suites; each cycle preserves the original runner's target reservation and cleanup semantics. |

Manual evidence must identify exact source commit, clean unsigned APK hash,
signed candidate hash, previous candidate hash for upgrades, device class/OS
(without serials), procedure, timings/thresholds, observations and limitations.
Store screenshots/traces privately and reference their SHA-256 from the review
record. Do not mark PASS based on planned steps or mock evidence.

The shipped Phone APK excludes the debug launcher and E2E probe. Existing
adapter capability/identity contracts must not be weakened to get a green gate.
Until release-compatible observation is qualified, affected functional suites
remain a real readiness blocker; no debug-build substitution is performed.
