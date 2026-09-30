# SafeLanding lifecycle host suite

Run from the repository root:

~~~bash
python3 tests/run-project-tests.py --suite safe-landing-lifecycle --timeout 240
~~~

This common suite belongs to the host profile. It needs c++, pkg-config, Qt 6
Core headers/libraries, and matching moc. Missing prerequisites fail rather than
skip. To test matching Qt 5 tools explicitly:

~~~bash
SAFE_LANDING_QT_CORE=Qt5Core python3 tests/safe-landing/test_safe_landing_lifecycle.py -v
~~~

The real SafeLanding header and implementation are read from this checkout.
Includes are removed to compose a standalone translation unit; the physics
readiness method is replaced with a controllable entity flag. The mutex is
wrapped with entry/release hooks. Entity, renderer, domain, and application
fixtures are lightweight; Qt connections, direct/queued delivery, event queues,
and threads are real. The old slots access annotation is normalized to private
for moc's combined-file scan, with no change to baseline method behavior.
Both ANDROID_APP_PICO_INTERFACE and the shared path compile and execute.

Coverage includes in-flight additions after stop/reset/restart, stale queued
deletions, idempotent concurrent starts, connection/priority cleanup, completion
atomicity, missing packets, empty scenes, sequence restart, status queries, and
visual handoff rules. Four negative controls in each Pico/shared mode must fail by assertion or invalid
renderer access when guard ordering, generation checks, queued-delete admission,
or completion atomicity are deliberately broken.

An archived baseline may be tested without changing it:

~~~bash
SAFE_LANDING_SOURCE_ROOT=/absolute/baseline SAFE_LANDING_BASELINE=1 \
  python3 tests/safe-landing/test_safe_landing_lifecycle.py -v \
  SafeLandingLifecycleTests.test_inflight_callback_after_stop \
  SafeLandingLifecycleTests.test_concurrent_start_is_idempotent
~~~

Baseline mode disables only fixed-source mutations; it does not alter lifecycle
methods. The baseline is expected to fail the selected scheduling assertions.
Use an isolated TMPDIR and disable core files when intentionally reproducing
failures. This suite is host regression evidence. It does not compile the actual
product dependencies, exercise real collision shapes, or certify a device.

## Integration and remaining qualification

The suite is registered once in the common host runner and mapped to the
interface area in project-coverage.json. Keep the quick profile dependency-light.
After parent-to-child propagation, replace the Pico runtime-parity lifecycle
implementation with a thin delegation to this driver and remove its duplicate
fixture/driver. A standalone Pico world suite may invoke the common driver; a
combined host plus product run should not execute it twice. Do not bring unrelated
Pico worktree changes into main.

Before integration, run the Qt 5 command with matching Qt 5 development files and
moc. Qualify a full main native build with the pinned Linux dependency image and
Conan lock from tools/native-tests/README.md; build the interface target itself,
then run the selected native tests. A core-only native build does not compile
SafeLanding or establish this product check.

After propagation into a pinned Pico candidate, resolve its exact reviewed source
inputs and build its Qt 5 APK using the child build guide. Bind the APK hash to
that candidate and inputs. In a later authorized device session, verify cold/warm
world entry, navigation during loading, disconnect/reconnect, sequence recovery,
and collision-safe movement while visual assets finish. Record device results
separately; the host fixture cannot replace those checks.

## SafeLanding fixture routing

Only the standalone host driver and fixture header under tests/safe-landing
have exact native-routing exemptions. Unknown C++ files in that directory and
build definitions still require product configuration. Real SafeLanding.cpp/.h
changes require the full graph and build the interface target plus affected
native tests. The initial combined product/router change can select broadly.
The CMake file API audit rejects compiled/header inputs that would enter this
host exception, including source-tree files marked generated. Build-directory
generated inputs remain separate from source routing.
