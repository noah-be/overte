# Shipping Audio QML audit followup

This is a passive acceptance-audit correction only. Native application code, settings, input dispatch, microphone grants, PCM gates and original click/paint oracles remain unchanged. The original acceptance packet is immutable.

## Source evidence

The actual managed gateway process was checked against its recorded PID/start token, process group, complete command and repository working directory before and after the bounded private environment read. No native application, browser, process service or GPU test was launched.

A pure-Python parser extracted the exact `hifi/audio/Audio.qml` resource from the verified installed Qt RCC, whose SHA256 is `dd8a9efebe9b09a4b5e84e5c768ad7c7a38ea9702e681a357898dcbb9674ce01` (141862855 bytes). The uncompressed Audio page SHA256 is `4208e7f17c85d1c1bd57e515eb191fa6afb1ffb517b5506d58844922e8f99379` (35827 bytes). The installed `audio.js` SHA256 is `42f48103b327c63bdb7a22f7cfb8fe9c57010014e468ed7cda5a557cfc1d2e17`; it loads that exact resource alias. Its page lacks an `objectName` declaration. No Audio-page/RCC override is prepared by the gateway, and no source-tree resource environment flag is forwarded into the worker.

Actual native source anchors are `libraries/shared/src/PathUtils.cpp` (`getRccPath`, `qmlBaseUrl`), `interface/src/Application_Setup.cpp` (primary RCC registration), and `scripts/system/audio.js` (AUDIO app resource). These explain the runtime resource path; extracted installed bytes govern this pinned-release audit.

## Exact signature and refusal

The page must have the exact native title `Audio Settings`, `switchWidth=40`, `switchHeight=16`, and genuine boolean `pushToTalk` and `muted` properties. A unique visible owned descendant wrapper must still have the Desktop-only `Push To Talk (T)` label and genuine checked boolean; its actual descendant Switch must have background, indicator, checked/down booleans and numeric visualPosition. Parent links must agree with the traversed visual children. Unreadable property getters, cycles and inconsistent ownership mark a partial capture and cannot authorize a click. No setter is invoked.

Original acknowledgement sequence/revision/navigation equality, unique root/control, native Desktop enabled/held/muted state, full rectangle clipping, enabled/visible ancestors and painted contrast checks are unchanged. So are 4096 nodes, depth 24, 256 children, 512 emissions, 512KiB log budget, 4096-byte records, retained 32 records and all launch/acceptance deadlines. Missing/wrong primitive properties, ambiguous pages, stale frames and unowned/hidden/clipped controls fail closed.

## Reproduction and qualification

From the browser-client working directory, run:

```sh
node --test tests/integration/tablet-ptt-audit.test.mjs
```

The frozen CPU log records 15 passing cases, zero failures and zero skips. This exercises the exact QML auditor through Node VM with fixed shipping shapes and trapped native/root setters. It does not prove actual Qt pointer handling, microphone capture, PTT/audio interoperability or a native/browser session. Those remain the original genuine acceptance harness's mandatory runtime checks. Preparation must consume the updated auditor before producing its copied capture QML; an already prepared QML file retains the old auditor until regenerated.

Apply `shipping-signature.patch` with zero fuzz against the original two auditor files. The preparation-tool dependency correction is outside this patch and remains the parent's separate followup. No raw environment, process identifier, account/device selector or operator path is included in this packet.
