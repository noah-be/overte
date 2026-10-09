# Pixel 6a physical E2E qualification

The permanent local Jenkins job is `overte-pixel6a`. It serializes device access,
checks the installed APK bytes against the candidate receipt, binds the native
and host implementations to their source hashes, and owns the controlled scene,
domain and PC voice peer for the duration of a run. Private target configuration
supplies wireless device discovery and Appium access.

## Full run and ordering

```bash
overte-jenkins build overte-pixel6a -p RUN_MODE=full-e2e -s -v
```

The full run covers all 35 catalog modules, with a fresh launch precondition for
each transport route. The deployment orders previously failed modules first,
then new or repaired modules, then unqualified coverage, then previously passing
coverage. The actual order and previous results are recorded per build. Routes
retain their launch prerequisites, and domain-entry checks precede voice checks
that use the same owned fixture.

This is not a fail-fast reduction of coverage: the remaining routes run after an
early failure so the complete result remains reviewable. A failed, errored,
skipped or unbound module cannot qualify the full catalog.

## Required Phone bindings

- Tablet and Settings actions use visible native resource IDs in the selected
  application's namespace. Semantic snapshots must be stable and unambiguous.
- Native accessibility exposes the actual Qt controls and actions. The text
  fixture uses the product QML field; editing, submit, keyboard visibility and
  dismissal are observed from live native state, including world-input isolation.
- Independent entity synchronization uses a separately authored fixture actor
  and correlated entity revisions. A local readback of the client's own write
  cannot substitute for this observation.
- Upgrade testing requires different inspected package versions, matching
  signatures, exact APK hashes and retained safe settings after the upgrade.
- Voice testing requires fresh received PCM in both directions and both mute
  controls. This qualifies the digital mixer path, not microphone or speaker
  acoustics.

The additional native hooks and embedded controlled assets require the dedicated
debug E2E build with `OVERTE_E2E_VOICE_TESTS=ON` and an explicit test launch.
The debug launcher clears stale observations and binds the fixed entity script
to its embedded `qrc:` URL. Native bindings must match the installed candidate;
host success alone does not establish physical-device success.

## Keyboard and packaging regression

Android IME visibility is independent of the occluding inset. A visible floating
keyboard can have a zero bottom inset; visibility-only transitions must still
reach the native metrics consumer. The Phone-local Qt editor preserves editor
actions and input types while disabling landscape fullscreen extraction.

The filtered Qt jar task binds its override list as an explicit Gradle input.
APK verification requires exactly one packaged definition of each replaced Qt
Java class. This prevents a warm build cache from retaining an older editor
alongside the repaired class. The normal content, signature and 16 KiB alignment
gates remain required.

## Recorded qualification

[APK 12 evidence](../../../tests/device/evidence/pixel6a-v12-qualification.json)
records Jenkins #59: 35 distinct modules and 53 checks passed, with zero failed,
errored or skipped checks. It binds the exact APK and original repair snapshot,
including post-run installed-byte verification and owned fixture cleanup.
The corresponding host checks passed 44 project groups, 36 full control-plane
groups and all 428 selected self-tests.

That receipt describes the complete pre-integration candidate. Later merge
commits require their own applicable verification and an honest binding to the
tested product version. See [project host verification](../../../tests/PROJECT_TESTING.md)
and the [Phone build guide](BUILD.md) for prerequisites and build provenance.
