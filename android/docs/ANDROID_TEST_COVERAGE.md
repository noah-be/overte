# Android test coverage matrix

This document records behavioral coverage, not a percentage estimate. A green
contract test proves its named invariant; it does not imply that the complete
feature works on an Android device.

Status meanings:

- **Covered**: an executable test exercises the production behavior.
- **Partial**: important behavior is tested, but a framework or end-to-end path
  remains untested.
- **Contract only**: source or packaging structure is checked without executing
  the production behavior.
- **Missing**: no meaningful automated coverage exists yet.

## Feature matrix

| Feature | Host/unit coverage | Android/device coverage | Status and remaining gap |
| --- | --- | --- | --- |
| Deep-link normalization | Standalone Java and JUnit tests cover schemes, controls, Unicode whitespace, encoded payloads and length bounds | AndroidX intent-boundary and launcher transport tests compile; no automated device lane | **Partial**; run instrumentation in a managed emulator/device workflow |
| Launcher state | CI-required Robolectric execution of the real Activity on API 26 and 35 covers saved-state recreation, replacement/clearing and exactly-once launch; only generated resources and the Qt-native destination are boundary stubs | AndroidX launcher tests cover canonical and absent extras; device smoke covers launch survival | **Covered** for device-free launcher behavior; configuration-driven rotation and OS process killing still belong in an emulator lane |
| Runtime microphone permission | Pure callback-policy tests and Robolectric cover already-granted, denial, repeated request after recreation, unrelated callbacks and duplicate results | Device smoke grants automatically | **Partial**; system-dialog UI, “don't ask again”, and Settings recovery require emulator/device automation |
| Activity lifecycle and Back | Robolectric executes launcher save/restore/recreation on API 26 and 35; pure pending-URL policies cover readiness, replacement, retry exhaustion and clearing; source contracts cover Qt glue | Physical smoke exercises Home, repeated resume and Back recovery | **Partial**; `PhoneInterfaceActivity` inherits Qt 5's native loader, so configuration-driven rotation, real Qt surface recreation, predictive Back registration and JNI retry timing require an Android runtime |
| Login state machine | CTest covers native state transitions; Qt Quick loads the real Phone login body with bounded host/login fakes and exercises validation, account/domain routing, pending state, success/failure, duplicate suppression and teardown | No automated real authentication/backend test | **Partial**; real credential exchange and domain authentication require a controlled integration backend |
| Phone deep-link JNI handoff | Source contracts | Neutral deep link in device smoke | **Partial**; cold/warm/background delivery assertions remain indirect |
| Tablet touch layout | Qt Quick tests execute the real `TabletTouchConfiguration.qml` for responsive columns and bounded geometry | Tablet presence/routing checked by contracts; no visual device assertion | **Partial**; validate physical display sizes |
| Audio tablet presentation | Executed Qt Quick selector test verifies expected Phone gates | No automated audio input/output behavior | **Partial**; add controlled microphone/playback scenarios |
| Avatar tablet presentation | Executed Qt Quick selector test verifies Phone layout and hidden HMD controls | No automated avatar load/change journey | **Partial** |
| Security settings presentation | Executed Qt Quick selector test verifies the scripting-plugin gate and geometry | No Android UI interaction test | **Partial** |
| General Settings presentation | Executed Qt Quick tests cover the production fail-closed category policy, bounded pages, compact footer, touch targets and orientation resize | No complete settings persistence test against the registered application backend | **Partial** |
| Emote application | Production `phoneEmote.js` executes under Node and real `PhoneEmote.qml` state behavior executes under Qt Quick Test | No touch-to-script end-to-end test | **Partial**; bridge/touch journey remains |
| Address dialog | The real QML executes with bounded Hifi/control fakes for initialization, validation, loading, close and visibility | Device smoke does not interact with the dialog | **Partial**; Android IME/touch and real C++ backends remain untested |
| Login QML body | Eleven Qt Quick tests load the production component and cover validation, account/domain submission, pending/error/success states, duplicate suppression, credential bounds, password accessibility invariants, secret scrubbing and idempotent close | No Android IME or real authentication service | **Partial**; runtime backend and touch/IME integration remain |
| Places application | Production JavaScript behavior tests cover Phone/Desktop transports, multi-metaverse selection, malformed directory entries, protocol/capacity/attendance classification, stale and duplicate callbacks, host changes, all UI actions, portal validation/distance/count/expiry and cleanup; `places.js` measures 98.25% lines / 94.98% branches / 97.92% functions and `portal.js` 98.74% / 84.21% / 100% | No real directory/render/navigation device journey | **Partial** |
| Tablet app routing | Production `mobileTabletApps.js` executes in a controlled VM with route, security and cleanup flows; extensive QML/source contracts | No app-by-app device navigation suite | **Partial** |
| Native graphics profile | Executable host tests cover production Boolean, float and unsigned parsers plus source contracts | Device benchmark harness exists; no scheduled device baseline in this suite | **Partial** |
| APK contents and metadata | Device-free package, permission, privacy, ZIP and asset gates | Device smoke validates the selected APK before install | **Covered** for currently enumerated package invariants; full app behavior is separate |
| 16 KiB compatibility | ELF/alignment/package gates and dependency sentinel tests | Physical page-size lane is documented but not automated here | **Partial** |
| Network failure/reconnect | Deterministic Places backend fakes cover repeated HTTP/transport/timeout failures, refresh cancellation, stale responses and recovery without external networking | No complete world connection/reconnect scenario | **Partial**; world-server transport and authentication reconnect need a larger integration harness |
| Accessibility | Qt Quick tests verify accessible names, descriptions, roles, password-field privacy, tab eligibility and deterministic focus requests for Phone Login, Address Bar and Emote; General Preferences Save/Cancel semantics have source contracts | No Android TalkBack, spoken traversal, contrast, font-scaling or touch-exploration test | **Partial**; semantic host coverage exists, Android assistive-technology behavior remains |
| Memory/leak endurance | No host test | No scheduled soak lane | **Missing** |
| Performance regression | Benchmark harness and telemetry contracts | No committed device baseline/threshold lane | **Missing** as a regression gate |

## QML production inventory

The following Phone selector components are suitable for direct host loading
because they are plain `QtObject` configurations:

- `AudioTouchConfiguration.qml`
- `AvatarTouchConfiguration.qml`
- `SecurityTouchConfiguration.qml`
- `TabletTouchConfiguration.qml`
- `TabletPreferencesLayout.qml`
- `SettingsTouchConfiguration.qml`

They are loaded from their real production paths by the tests in `tests/qml`;
the tests do not copy their values into test-only components.

`PhoneEmote.qml` is also directly loadable when Qt Quick Controls 2 is present.
Its public inbound state behavior and production emote model are covered.

The Address Bar harness loads `AddressBarDialog.qml` directly,
with test-only QML modules standing in for its registered Hifi backend,
singleton managers and controls. It defines checks for production
initialization, visibility forwarding, address validation/trimming and close
routing, and passes under Qt 5.15 `qmltestrunner`. It does not claim to
reproduce Android IME behavior or the real C++ implementations.

The phone login body is loaded from its real production path with bounded fake
login and host objects. Its account/domain routing, validation, pending state,
completion/failure handling, duplicate suppression, credential bound, secret
scrubbing and idempotent teardown are exercised. General Preferences uses a
small production fail-closed category policy; host tests cover that policy,
compact footer constraints, minimum touch targets and landscape-to-portrait
resize behavior. The full shared preferences component graph still depends on
the application's registered preference backend and therefore remains covered
by contracts rather than a test-only imitation of that backend.

## Runtime validation

The Qt Quick tests require `qmltestrunner`, Qt Quick Test and Qt Quick Controls
2. They were executed in an isolated Ubuntu 24.04 / Qt 5.15 environment with
38 explicit `test_*` functions pass (52 QtTest result rows when suite
initialization and cleanup rows are included). The fast CI job installs the same package set and requires
the QML tier to execute; a missing tool is a failure there. Local hosts without
Qt still receive an explicit skip. This host evidence does not replace Android
IME, GPU, touch or real application-context tests.

The host QML tests also verify stable accessible names, descriptions and roles
for the phone Address Bar, Emote and Login controls, plus tab eligibility and
deterministic focus requests. General Preferences Save/Cancel semantics are
protected by source contracts because its complete production wrapper requires
the registered application preferences backend. These checks validate the Qt
accessibility properties only; they do not claim Android TalkBack traversal,
spoken output, contrast, font scaling or touch-exploration coverage.

The clean-host CI coverage job executes JaCoCo directly against the five
framework-independent Java production classes and requires 100% line and branch
coverage in that scoped set. It also installs pinned `gcovr` 8.4 in a repository
build-directory virtual environment and enforces 95% line / 90% branch coverage
for the native login, graphics-policy and pending-handoff code. These percentages
must not be interpreted as whole-application coverage. The current measured
results exceed those gates: interface policies are at 100% lines/functions and
98.9% branches; pending handoff is at 100% for all three metrics.

The clean-host CI harness executes nine Robolectric Activity behaviors on both
API 26 and 35 (18 executions); the prepared-dependency Gradle report executes
the same source tests. Their value is behavioral framework coverage, not inflating the
100% pure-policy gate: generated `R`/`BuildConfig`, Qt framework code and Android
SDK shadows remain outside that critical-class percentage.

## Generated robustness and mutation checks

Deep-link and safe-asset-path policies include deterministic, fixed-seed input
generation (1,024 generated URL checks and 512 path cases). Places additionally processes
512 generated malformed UI/message payloads and a 2,000-entry mixed
directory response. These are reproducible property-style checks, not random
or external-network fuzzing; failures can therefore be replayed exactly.

The `mutation` suite contains a fast, dependency-free mutation smoke gate for
five high-risk boundary decisions in deep-link and asset-containment code:

```bash
tests/run-tests.sh mutation
```

Every listed mutant must be detected by the production-facing tests. This
focused gate is deliberately not presented as a whole-project mutation score.
A full C++/QML/JavaScript mutation campaign would be substantially slower and
requires language-specific tooling; it is best run periodically after those
components have been split into smaller pure policies.
