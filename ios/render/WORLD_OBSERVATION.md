# Full Client world observation

The actual Overte target links `WorldObservation.cpp` and
`InstallWorldObservation.cpp`. An iOS Full Client configured with
`configure --client-graph --world-observations` (simulator or device), or an
existing device E2E build, must also be launched with the existing
`--ios-world-evidence` option installs the exporter. It samples once per second
for at most ten minutes, stops on write failure, and publishes an inactive
snapshot when the application leaves the foreground. It atomically replaces
`Documents/overte-world-observation.json` with owner-only permissions and no
direct-write fallback. The output is bounded to 4096 bytes; no URL, entity,
account, device identifier, credentials or raw diagnostic text is exported.

The assigned Shared baseline supplies bounded counts of expected entities and
their intersections with renderable, scene and drawn sets. Those are internal
observations, not independently approved expected-world identity. This baseline
exports `producer=entity-counts-only` and omits unavailable generation/present
fields rather than filling them with a plausible value.

The separately reviewed Shared proposal adds `OVERTE_IOS_WORLD_OBSERVATION_VERSION=1`.
Its consumer branch exports the single locked snapshot's generation, WSI
accepted/rejected present-call counters, last frame index and produced software
QML image count. Decimal strings preserve full uint64 values in JSON. The
GraphicsEngine records the generation before rendering and carries it on the
actual gpu::Frame. Splash-only frames and a generation changed during recording
have a zero stamp. VulkanDisplayPlugin reports the actual queuePresent return
against that carried stamp. World clearing retires it. A successful WSI call
does not prove scanout, entity visibility, correct scissor/pipeline/descriptor
state or screen-QML composition; QML image production is also not composition.

`ios/tools/inspect-world-observation.py` retains only this closed observation
shape. The real simulator smoke caller invokes it for supplementary diagnostics,
including failure cleanup, outside the strict world evidence directory. It
does not bypass or replace the legacy world validator, its waits, screenshots,
candidate identity checks or five unaccepted migration guards. Ordinary
candidates without either build opt-in have no exporter and remain explicitly unavailable.
The observation build switch defaults to OFF on every configure, including a
reconfigure. It does not enable or relax the separate device-only E2E contract.

Every sample says `OBSERVATION_NOT_ACCEPTANCE`,
`EXTERNAL_CANDIDATE_REQUIRED` and `EXTERNAL_INSTALLED_CODE_REQUIRED`. The file
contains neither a fabricated source SHA/artifact hash nor a runtime receipt.
Before future acceptance, an independently verified candidate/install/run
transport must bind these observations, approved scene identity and screenshots
to exact source/artifact/process observations; the local file alone is
replaceable and cannot attest them.

Host validation runs the actual C++ adapter, Shared state, startup registration,
Qt event loop, QSaveFile and Python consumer. Only the native container path is
substituted for the installer. Native UIKit/WSI/Qt6 iOS, GPU pixels, complete
Full Client linkage and simulator/device behavior remain unexecuted.
