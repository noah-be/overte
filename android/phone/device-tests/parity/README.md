# Current-artifact Phone parity journeys

[`journeys.json`](journeys.json) covers the same fourteen PHONE-P2 issues
[#1124–#1137](https://github.com/noah-be/overte/milestone/4), with 51 concrete
actions, expected visible/audible outcomes, evidence kinds and cleanup. These
are operator-assisted physical Phone journeys through normal app entries.
They supplement existing automatic smoke tests. They are not new implemented
device adapter operations, a green catalog, or completed device acceptance.

Select the artifact deliberately after its full build and package checks.
Bind its independent full source revision, APK SHA256, build configuration,
installed-byte evidence, UTC date, OS and browser-provider version. Use the
same shared world, peers and fixtures on iOS and Pico. Evidence stays private;
use invented text, harmless provider files and lab accounts, never record a
credential, device selector or serial. Logins should be demonstrated with
sanitized outcome records; pause recording during credential entry.

## Prepare and review

The following commands operate only on local files. They do not discover,
install, reserve, contact, launch or stop a device or Jenkins job:

```bash
python3 android/phone/device-tests/parity/packet.py list
python3 android/phone/device-tests/parity/packet.py template \
  --source-sha "$ACCEPTANCE_SOURCE_SHA" \
  --artifact-sha256 "$ACCEPTANCE_APK_SHA256" \
  --utc "$ACCEPTANCE_UTC" --output "$PRIVATE_PACKET"
python3 android/phone/device-tests/parity/packet.py review \
  --packet "$PRIVATE_PACKET" --artifact "$ACCEPTANCE_APK" \
  --expected-source "$ACCEPTANCE_SOURCE_SHA" \
  --expected-artifact-sha256 "$ACCEPTANCE_APK_SHA256" \
  --evidence-root "$PRIVATE_EVIDENCE_ROOT"
```

Every generated observation starts `pending`. Record `observed`, `failed` or
`blocked`, its UTC time, actual outcome note and relative evidence files with
their SHA256/kind. Keep a blocked provider/runtime capability explicit. Do not
replace it with a supported page or silently omit the journey. An installation
binding attachment is mandatory; obtain it from the existing independently
bound candidate/installed-APK workflow, not by copying the expected flags.

The review tool checks coverage, identity expectations, actual candidate and
attachment bytes, required evidence kinds and contained paths. It cannot
authenticate an operator, installed-byte receipt producer, physical target,
file MIME/content, media pixels, audible audio or the truth of an observation.
Its output always says `deviceAcceptance: false`; `readyForHumanReview` means
only a complete packet is ready for assessment. Review exit 2 means pending,
failed or blocked observations remain. No registry/issue/JUnit pass is written.

## Media and provider observations

Use the shared ordinary reference script and original MP4 in
[`tests/device/fixture/parity`](../../../../tests/device/fixture/parity/README.md).
Record its served digest and browser provider version. Approve `scriptURL`
normally; do not substitute a debug script transport for the actual EventBridge.
World video evidence must show the encoded moving square, burned-in counters
and red/green/blue cycles **inside the final world texture**. Record that region
on the physical Phone at several times, with the world context visible. The
native Tablet overlay is a separate surface. A DOM animation, player clock,
network request, frame-transport counter or unchanged bitmap cannot pass this.
Record physical audible output separately; an Android screen recording can omit
or reroute audio and therefore must not be assumed to prove speaker/headset sound.

Test DOM selection/composition after foreign-origin navigation while bridge
echo is refused. Real OS file selection belongs to the visible Tablet grant;
a world surface must not acquire that grant. Cancel the provider, replace the
owner while it is open and resume after background. Observe both the useful
document and rejected late callbacks. Do not collect the actual entered text.

For Snapshot Save, wait for publication and open the result in an independent
normal app. For Share, inspect the system chooser/receiver and cancellation;
successful handoff does not assert recipient persistence. Inspect real still,
moving GIF and 360/cubemap contents, not merely a preview/status signal.

The original [companion fixtures](fixtures/README.md) provide actual selectable input.
For Scripts choose a folder containing a main script and nested includes.
For Assets choose actual glTF/external-bin/textures and OBJ/nested-MTL/textures
fixtures, review the selected main, and observe rendered geometry/materials.
Matching copied/uploaded hashes alone do not prove model rendering or script
execution. Whole-selection failure, provider cancellation and companion-upload
failure must not publish a truncated primary asset. Keep successful local copies
until the real script/upload no longer needs them.

## Existing laboratory boundaries

The repository Phone pipeline currently offers seven suites; its generic ADB
adapter covers lifecycle/telemetry and opt-in debug scene/jump/flight. Shared
ADB/Appium provide additional tablet/text/voice/domain/asset/sound primitives,
but the catalog has no full media/provider/export/bundle journeys. `asset-smoke`
is a controlled asset load, not native model-companion import. `sound-smoke`
and render health are not browser MP4 audio/pixel acceptance.

Read-only official Jenkins CLI inspection on 2026-10-13 found the installed
`overte-pixel6a` job offers sixteen `RUN_MODE` choices and delegates to local lab
wrappers. The wrapper has a historical source/artifact binding and copies a
historical test catalog. Do not execute it against an assumed new candidate.
The coordinator must deliberately bind the new verified APK and reviewed test
source and preserve private target reservation/cleanup before a separately
authorized run. Use `overte-jenkins`; no raw Jenkins HTTP or implicit rebuild/install.

Automatic parity modules need genuine adapter support before shared catalog
registration: bound final-screen capture and audio evidence; native provider and
export terminal outcomes; ordinary Scripts/Assets controls; scoped source/page
callback observations. Until available, the physical operator supplies the
evidence. Camera/screen captures and independent receiver/provider checks can
observe these outcomes without adding a native application probe. Any later
native probe must retain debug gating, freshness/owner fences and privacy.
