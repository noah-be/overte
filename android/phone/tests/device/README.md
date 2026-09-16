# Phone result consumer: implementation, not acceptance

result_adapter.py consumes original SH-004 v001 (source
5c6354555a88fac2e089b033eb52ebe750171cd5, manifest
d92c7710551fe134029d2243cea84350a18000934acbd765bd1ef138b3cfa85b).
The published patch and byte-identical terminal_evidence.py prerequisite are
imported separately. Existing newer Phone catalog entries are preserved; each
Phone-required suite's exact module membership is checked for drift.

The result root holds one original Shared runner directory per named suite.
Emulator requires smoke, permission-recovery, tablet-e2e and text-input-smoke.
Core adds controlled domain, touch interaction, audio control/playback, network
recovery, loaded lifecycle and at least 30 minutes of stability. All required
modules must be present, complete and passing with the exact source/APK identity.
Actual registered adapter IDs are android-phone-adb or appium-android. Emulator
requires virtual Android; core requires physical Android. No target is selected,
device operation run, identity sidecar written or receipt retroactively created.

Example offline consumption (only after separately authorized execution):

    python3 android/phone/tests/device/result_adapter.py \
      --result-root RESULT_DIRECTORY --expected-source-sha SOURCE_SHA \
      --expected-artifact-sha256 APK_SHA256 \
      --expected-adapter android-phone-adb --milestone core

Successful output is PHONE_RESULTS_BOUND_NOT_ACCEPTED. This consumer validates
integrity and scope, not producer trust, installation truth or sensor observation.
PH-003 additionally verifies its packaging/deep-link AndroidJUnit plan through
emulator/phone_acceptance.py, whose CLI now requires these canonical results.
The independent AndroidJUnit files still lack a Shared execution-time identity
binding and cannot prove candidate equivalence merely by being provided together.

Pending: actual execution-time identity producer, AndroidJUnit identity binding,
exact candidate/ABI/API acceptance, actual module capabilities, physical device
label provenance, microphone/route evidence, screenshots and module/crash-log
privacy scans, SH-005/006/PX-17 and original node dependency acceptance.
Host fixture success is never a device or emulator PASS.

Focused synthetic tests (no device):

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
      -s android/phone/tests/device -p test_result_adapter.py
