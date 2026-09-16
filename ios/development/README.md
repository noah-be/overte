# iOS QML and client JavaScript development without rebuilding

This foundation selects an immutable development revision at app startup. It
requires one **new E2E Full Client IPA containing this implementation**, launched
once. Afterwards QML, QML JavaScript imports, pure-QML modules/singletons, client
scripts and their include/require dependencies can be edited and transferred
without rebuilding or resigning the IPA. Close and reopen Overte to apply a
revision. This is restart-based resource reload, not in-place state migration.

Native C++/Objective-C, shaders compiled into the renderer, new native QML types,
Qt plugins and entitlements still require a build. Downloaded entity scripts
keep their existing URL identity, consent checks and cache behavior. This does
not add a network code server or enable Qt's debugger in release builds.

## Production path

`interface/src/main.cpp` selects the revision before `app.initialize()` creates
ScriptEngines and OffscreenUi. Only `Q_OS_IOS && OVERTE_IOS_E2E_TEST_BUILD` calls
this initializer. It passes the selected complete scripts directory into the
existing `PathUtils::defaultScriptsLocation()` API. ScriptEngines continues to
normalize saved built-in script URLs through `/~/`, and scripts keep their
relative include/require base. Explicit launch `--scripts` takes precedence;
omit it when testing revision scripts.

On iOS Qt 6, `OffscreenSurface::initializeEngine()` installs a URL interceptor
before QQmlFileSelector. It covers QML, imported JS, pure-QML qmldir files and
resource URL properties, including dependent components and `+ios` variants.
Other platforms and Qt 5 retain their current behavior. Files absent from the
revision use bundled qrc resources; Qt's installed native modules stay in the
IPA. A complete `interface/resources/qml` tree is transferred by default, so new
QML components and new pure-QML modules are included too.

The app verifies the complete file manifest before selecting either root. A
missing/corrupt revision or request from a different app installation falls
back to the IPA and records `rejected`, with a reason. This is integrity checking,
not a signature or a claim that edited code is compatible with native APIs.
Changing `active.json` cannot mutate the running engine, singleton or script
set. No cache clearing on live QML objects is needed.

## Prepare and transfer

Use the existing local Python environment with asynchronous `pymobiledevice3`.
On this workstation it is the pinned runtime already used for House Arrest.
Keep this private JSON profile outside the repository, with mode 0600:

```json
{"udid":"<paired device>","bundle_id":"<existing installed signed Overte ID>","locks":["<installation lock>","<device-test lock>"]}
```

The tool does not sign or install anything and cannot allocate a new bundle ID.
It requires the capabilities receipt from the installed foundation before
writing. Device identity is never passed on the command line or printed.

```sh
python3 ios/tools/development-sync.py pack --output /path/to/private/revisions
python3 ios/tools/development-sync.py --profile /path/to/private/profile.json push /path/to/private/revisions/REVISION
# Close and reopen Overte, then read back the actual selected revision:
python3 ios/tools/development-sync.py --profile /path/to/private/profile.json status
```

`pack` includes all client scripts and supporting assets (currently about
128 MiB), plus the complete QML tree (about 7 MiB). Use `--qml-only` if scripts
should remain bundled. Add e.g. `--resource images/example.png` for changed
resource assets; paths are relative to `interface/resources`. New revisions
are content-addressed and include the source commit and hashes of working-tree
bytes, so uncommitted QML/JS edits are included. Do not edit generated packs.

Transfers verify every file by readback, resume matching files after interruption
and publish `active.json` by rename only after completion. `push` reports
`restart-required`, never "running" or device acceptance. An unsupported AFC
rename fails while retaining the previous activation and all staged data. Use
`--timeout SECONDS` before the subcommand if a first large transfer needs more
than 120 seconds. The same tool supports `--documents /path/to/Documents` for
the simulator container or offline tests; this is not device evidence.

## Rollback, disable and failures

```sh
python3 ios/tools/development-sync.py --profile /path/to/private/profile.json activate PREVIOUS_REVISION
python3 ios/tools/development-sync.py --profile /path/to/private/profile.json disable
```

Restart after either command. `disable` restores bundled scripts/QML and also
suppresses the older `OverteQmlOverrides/.enabled` mechanism for that session;
it leaves both old overrides and revision data on disk. Nothing deletes app
preferences, logs, caches or reusable revisions. Without a new protocol request,
the old individual-QML override mechanism still works as before.

`status.json` distinguishes `selected`, `bundled` and `rejected`; selection proves
manifest integrity and chosen roots, not successful UI execution. A syntax error
can still prevent a screen from opening. Read ordinary QML/script errors, fix and
publish another revision, or disable/rollback and restart. Do not present such a
failure as a native build or hardware acceptance result. After an IPA update,
launch it once and explicitly activate a compatible revision again.

## Verification and remaining device acceptance

`timeout 120 python3 ios/tests/development-reload-test.py` compiles the production
initializer/interceptor against real host Qt and executes QML, imported JS,
selector-specific components and a new pure-QML singleton. It also exercises the
actual publisher, rollback, install binding, corrupted/missing files, symlinks,
interrupted transfer/resume and traversal rejection. It is not iPad/V8 proof.

On the next foundation IPA: transfer a harmless Tablet text change and client
script change, restart, verify both visibly and read the matching revision;
repeat with a second revision, then rollback/disable. Check keyboard, navigation,
sound and world startup still work. A rejected revision must start bundled
content. Measure transfer/startup latency before claiming instant hot reload.

Qt API references: [URL interception](https://doc.qt.io/qt-6/qqmlabstracturlinterceptor.html)
and [engine interceptor lifetime/thread constraints](https://doc.qt.io/qt-6/qqmlengine.html).
