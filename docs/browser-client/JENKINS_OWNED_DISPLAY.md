# Owned headed display and early preparation evidence

The first exact-source Jenkins attempt failed before dependency preparation:
`xvfb-run` was absent. This was a wrapper dependency, not a missing native display
capability: pinned lab preparation already extracts/verifies Xvfb. No complete
nineteen-stage qualification was obtained from that failed attempt.

Preparation now requires the real `xauth` tool and the existing verified native
packages, without requiring the redundant distribution `xvfb-run` shell wrapper.
Every headed stage runs through the attested `owned-xvfb.py` helper using the
prepared `host_tools.load_tools()` executable, preserving its normal 1280×900×24
screen and all unchanged browser/native commands. TCP listening is disabled.

Xvfb selects an unused display through its bounded `-displayfd` readiness pipe.
Before any headed command starts, an actual Unix peer credential check binds the
socket to the recorded Xvfb PID/current UID and a cookie-authenticated X11 setup
must succeed. The ephemeral cookie is passed to xauth on stdin, never argv or
published output. Authority/log files reside in a 0700 job-private directory.

The existing kernel parent-death helper owns each direct executable. Cancellation
only changes a flag in signal callbacks; normal control flow terminates/reaps the
recorded gate group before its Xvfb group, checks group identity, and applies the
existing five-second TERM/five-second KILL bounds. No process-name discovery,
broad killing, public/desktop X socket or another job's server is used. The job's
existing private PID namespace remains the final ownership boundary for further
descendants. Startup retains the ten-second readiness deadline. The root host qualification actually authenticated the verified Xvfb through
this helper, completed its owned command and left the preexisting X sockets and
laboratory PIDs unchanged. A headed browser and the complete nineteen-stage
qualification still require the new exact-source Jenkins run.

A bounded 0600 failed `prepare-summary.json` is initialized in the dedicated
workspace before source/host preflight, and safe failure categories update it.
Early missing tools therefore produce an archiveable truthful failed result.
Arbitrary exception paths/credentials are not copied into the artifact.
The archived artifact requirement, exact fork/SHA checks and all nineteen stages
remain unchanged. Missing or failed stages never become a complete pass.

Eight new CPU contracts exercise real owned child groups and actual SIGTERM,
synthetic private Unix X11 authentication/peer checking, bounded display-pipe
records/deadlines, early artifacts and error redaction. Synthetic peers are
explicitly not real Xvfb/rendering evidence. The unchanged standard 23 contracts
remain included; the combined suite is wired into the existing npm unit gate on
Linux. Under the child execution sandbox seven of eight new tests passed; the
Unix bind test was genuinely blocked by EPERM. The root host executor ran all
eight unmodified new tests successfully (1.167 seconds). All31 combined contracts pass on the root host. The actual nineteen-stage job
remains required.
