# Closed diagnostics are not runtime acceptance evidence

Revision 09 consumes General `px16-apple-runtime-diagnostics/v001`, source
`a28ca2bd933a1f15ad87e2af0eeff920e1e5776b`, manifest
`825228455dbc4b089971d532bc618cdbcefdb83ce1df2960db746405053aafa6`.
The actual Shared `IOSRuntimeLogging.h` now sends only closed diagnostic events
to Qt and Apple's public OS log. Legacy marker arguments are not formatted or
emitted. NodeList's first-connection block no longer exports domain/session IDs.
Application state and internal entity correlation are preserved.

General `px16-apple-vulkan-diagnostics/v001`, source
`c9a8aaae61716bba46c028e1a9681a515235fe7f`, manifest
`d127126f2c0fcf901f509eebeb2b9ea5557ea440d88845b8e9b202acb1c2ed76`,
also closes all 41 direct OS calls in VKBackend and three in VKPipelineCache.
Only call arguments change; each info/fault severity and all nonlogging bytes
are preserved. The original 44-expression/raw-transport test passes. This is
not a full renderer compilation or native renderer execution.

Consequences for the current iOS candidate:

- `OVT_REDACTED` and `OVT_CONNECTION_READY` do not prove navigation, entity decode,
  render handoff, world identity, presentation, source SHA or artifact identity.
- Existing validators remain strict. Do not substitute those events for the old
  `OVERTE_IOS_*` marker sequence, relax assertions, create marker receipts or
  reuse old logs/screenshots as evidence for the changed candidate.
- `ios/tests/entity-gate-telemetry-test.py` currently fails because the old
  `domain_list_connected` marker is removed. The old
  `ios/tests/ios-offscreen-qml-backend-audit-test.py` fails its config-reload-marker
  assertion. Neither failure is hidden or changed to PASS by this migration.
  They record an unfulfilled evidence-source contract, not a reason to restore
  public private-data logging. Configuration reload itself is exercised by the
  new original Shared runtime-logging test.
- After the Vulkan delta, three more old source guards fail on intentionally
  removed output: `ios-vulkan-scissor-state-contract-test.py` (frame progress
  marker), `ios-render-forensics-contract-test.py` (texture fallback marker),
  and `ios-vulkan-pipeline-key-contract-test.py` (raw pipeline context call).
  They remain unchanged. Closed diagnostics are not replacement scissor,
  descriptor, pipeline, frame or safety evidence.
- General must supply a reviewed generation/source/artifact-bound structured
  world/render evidence producer and compatible consumers before those gates
  can be accepted. IO-001/003/006/008/009 and dependent handoffs stay unaccepted.
- Other direct sinks, in-memory diagnostic data/calculations, pipeline quarantine
  persistence, retained logs, export/crash and full PX-16 review remain outstanding.

`python3 ios/tests/privacy/diagnostic-evidence-separation-test.py` calls the actual
existing entity/world validators and verifies that closed diagnostics cannot
satisfy them. It changes no production validator or schema and provides no
positive device/world evidence. General's complete-header test uses real host
Qt with only the Apple OS transport substituted. Native SDK/Qt5/os_log delivery,
simulator/device, signing and original node acceptance remain unperformed.
