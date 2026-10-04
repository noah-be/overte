# Private preflight capture: umask-independent negative control

This supersedes prepared capture manifest92a8543395efcaf1f5b6c24fe1223555948f6845a9c6247714a48afab60dea59; original packet remains immutable. All original preflight argv/8second timeout/five-zero-cap/fsync gates and private prefix8192byte budgets remain unchanged.

The unsafe-parent negative explicitly chmods its authored temporary directory0755 after mkdir: a caller umask077 previously turned that negative into a safe0700 parent. An additional control runs the same real rejection under umask077 and restores the inherited mask in finally. No global/existing keyring or production directory is chmodded.

Only changed production files are the prior reviewed diagnostic collector and failed-result call site. This followup changes only the authored CPU fixture. observer.py is an unchanged pinned test dependency, not a proposed Root edit. Private original failed stdout/stderr stay owned0700/0600 and are not public artifacts. Atomic127 source cause remains unestablished.

Run only the pure authored module: python3 -B browser-client/lab/atomic-provisioning/test_preflight_diagnostics.py. Running test_observer.py itself is a separate actual namespace/ptrace qualification, not performed here.

Focused CPU qualification: {"actualNamespaceRun": false, "cases": 19, "durationSeconds": 0.068, "hostedPreflight": "pending", "status": "passed-focused-CPU-only"}. No actual hosted remedy or qualification is claimed.

Parent validation on 2026-10-02: the complete `python3 -B -m unittest discover -s browser-client/lab/atomic-provisioning -p 'test_*.py'` passes all86 contracts in4.330s, with the reviewed staged strace/keyring and private cache configured through `ATOMIC_DIAGNOSTIC_STRACE`, `ATOMIC_DIAGNOSTIC_TEST_KEYRING` and `ATOMIC_DIAGNOSTIC_CACHE`. The additional focused control explicitly proves the public-parent rejection under umask077. Required repository quick suites34/34 pass in149.708s. This is local contract evidence; the hosted exit127 cause and actual hosted native startup remain unqualified.
