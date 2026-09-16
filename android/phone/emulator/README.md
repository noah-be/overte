# Android Phone emulator acceptance preparation

This directory is a local, admission-neutral PH-003 preparation slice. It does
not launch an emulator, build an APK, define the SH-004 device schema, or claim
Phone parity.

`acceptance-plan.tsv` binds a bounded x86_64 acceptance set to existing Phone
production policies and already established AndroidJUnit entry points.
`phone_acceptance.py check-plan` fails closed if a guarded interface drifts;
`phone_acceptance.py selectors` emits only fully qualified AndroidJUnit
class/method selectors and never a device identifier.

After a later admitted emulator run, `phone_acceptance.py verify-results`
accepts bounded regular AndroidJUnit XML files and writes a new mode-0600 local
summary. It rejects missing, duplicate, failed, errored, or skipped planned
cases. Test output, stack traces, file paths, target identifiers, URLs, and
secrets are never copied into the summary or diagnostics. The summary is a
Phone-local preparation format, not the canonical SH-004 device schema.

Revision 09 explicitly activates the reused cases in the existing
`apps/phoneInterface/src/androidTest/java/org/overte/phone/` source set.
No Gradle file edit or emulator run is performed. These policy assertions do
not replace live Tablet/text/permission modules; execution remains a later
authorized `phone-emulator-test.sh` x86_64 operation with candidate binding.

Host-only preparation checks:

```bash
python3 android/phone/emulator/phone_acceptance.py check-plan
python3 -m unittest android/phone/tests/emulator/test_phone_acceptance.py
```

Result verification is deliberately a later-run operation:

```bash
python3 android/phone/emulator/phone_acceptance.py verify-results \
    --result TEST-result.xml --output phone-emulator-summary.txt \
    --runner-result-root RESULT_DIRECTORY --expected-source-sha SOURCE_SHA \
    --expected-artifact-sha256 APK_SHA256 --expected-adapter android-phone-adb
```

Revision 09 binds this operation to the original SH-004 v001 verifier through
the Phone tests/device/result_adapter.py consumer. Its complete virtual suite
set is mandatory; success is PHONE_EMULATOR_RESULTS_BOUND_NOT_ACCEPTED.
The private summary explicitly preserves unverified AndroidJUnit execution
identity. Co-located XML and Shared results do not prove candidate equivalence.
General's execution-time identity producer and an AndroidJUnit binding remain
requested; this tool never manufactures their receipts or runs an emulator.
