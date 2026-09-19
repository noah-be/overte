# Pico device-free suite outcomes

The 31-case catalog is unchanged. A selected run succeeds only when every selected
case passes. `--skip-missing` preserves the skipped result kind but returns 1 for
an incomplete run. A named/category subset can succeed; it is not the complete
catalog. `--list` only lists the plan and retains exit 0.

After `--fail-fast`, all remaining selected cases appear as skipped in JUnit with
`not run after fail-fast`; none is launched. Missing tools, process-launch errors,
nonzero child exits and timeouts cannot produce a successful selection. A launch
error is recorded without exposing its executable path or environment details.

JUnit properties identify the catalog size, whether the selection passed in full,
whether all catalog cases were selected, and whether the full catalog passed.
These describe this runner only. They do not bind a build artifact, establish a
mandatory native tier, accept any hardware result, or prove original PI-001/SH-002
acceptance. Existing child output retention/redaction needs separate review.

The 12 self-tests exercise the actual CLI, runner and XML writer using short real
Python child processes and deliberately absent executables. They cover complete
and partial selections, missing tools with skip reporting, fail-fast omissions,
launch failure, timeout and an empty catalog. The original runner fails the new
outcome assertions. These fixtures do not run the original 31 suite cases.
