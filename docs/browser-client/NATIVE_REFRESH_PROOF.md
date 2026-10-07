# Experimental native refresh readback

The production gateway refresh QoS experiment is now **default off**. The runner explicitly evaluates the current actual worker Interface.json payload with `OVERTE_GATEWAY_NATIVE_REFRESH_QOS=1`; it does not enable that environment flag on any gateway or change a running worker.

The parent reported three actual negative experimental Tablet cohorts: the first accepted ten graphics pointer changes but rejoin UI timed out; two subsequent cold starts stayed connected on Home yet produced zero Tablet frame metadata within the existing 30-second bound. Those failures remain evidence against enabling this cap by default. Their exact source-bound reports and timestamps are maintained by the parent. This readonly test cannot resolve or replace those failed Tablet/voice/pose/rejoin checks.

The proposed runner starts only its own fresh f91/2026.04.1 native Interface profile and process group on the same isolated managed .2 laboratory domain, using the exact reviewed production settings expression and fixed private lab audio endpoints. Its trusted script consists only of the production readonly refresh reader and six-record probe, plus a print wrapper adding `location.isConnected`. It runs no Entities, Settings, Performance or graphics setter, microphone request, account workflow or default application scripts. The snapshot is private; native logs are discarded rather than saved. The public report contains only six validated numeric/boolean refresh records, source/binary hashes, bounded timestamps and an independent three-second owned-process CPU delta. This checks the actual CUSTOM3/preset5 getter behavior; a requested target is not actual frame cadence.

It is an ordinary standalone native process, **not** the actual sandboxed gateway worker. It does not prove Qt Tablet rendering, audio transport, participant poses, rejoin behavior or CPU gains against an equal-workload baseline. The already running owned observer and all unrelated processes remain untouched. Existing domain entities are not edited; the same seven-entity baseline should be independently verified by the parent when the actual run executes.

The runner captures the detached leader starttime/PGRP/SID immediately after spawn. Before any group signal it rechecks that original identity; after leader exit, every remaining member must have a previously recorded matching starttime and original session, with a live known-member anchor checked again immediately before signaling. Reused leaders, reused members, unrecorded members and changed sessions refuse signaling and retain the private profile for owner review. It never uses a blind negative-PID signal-zero probe. It checks both root/process-group exit and removes only its unique private profile after the verified group has exited. No debug endpoint is added. Proposed commands after the parent copies the two test files into the actual package and starts the existing isolated lab:

```sh
cd browser-client
node tests/integration/native-refresh.test.mjs
node tests/integration/native-refresh.mjs
```

Source checks only: seven actual-runner CPU contracts passed (including leader/member PID reuse, post-leader cleanup and session refusal) and node syntax check passed. Native execution, actual getter readback, CPU delta and successful process-group/profile cleanup are **pending** the parent-run proof. Errors expose bounded reviewed captions/codes, not filesystem paths or raw native log text.
