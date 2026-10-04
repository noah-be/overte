# Isolated build and runtime laboratory

This AI-assisted laboratory prepares this worktree's own domain-server and
assignment-client binaries. The gateway session at
`/home/user/Documents/github/overte-browser-client` is read-only: none of its
services, mutable caches, profiles, files, branches, or test resources are changed.

Software and synthetic-audio qualification below is separate from the proposed
[manual hardware and physical speech check](MANUAL_ACCEPTANCE.md). That check
requires available physical devices and an agreed exclusive desktop/GPU window;
its hardware launch and human acceptance remain unqualified.

## Native dependency and compiler environment

The Fedora 44 host has CMake 4.3.0, Ninja 1.13.2, GCC 16.2.1, Conan 2.25.2,
Node.js 24.21.0, Python 3.14.7 and Firefox 156.0. Qt 5 development files are
absent from the host. Native compilation therefore uses the locally available
qualified fork-owned image:

```text
ghcr.io/noah-be/overte/native-dependencies@sha256:a692b477cd2efdfc1f3d0f059a8eebba4852d37509a2efa945937ef2fe073373
```

`tools/native-tests/packages.py` verified that all three dependency input hashes
match this image's metadata. Its baseline is
`ce02a328adde278323272b3866162b5c6eb348d9`, qualification run `36281406269`.
The image's immutable cache is copied into this worktree's ignored
`build/browser-direct/conan`. Compiler objects and all generated files have
separate directories under `build/browser-direct`. Existing configured builds
in other worktrees are not reused or modified. Container compilation has no
network or GPU device access and uses four compiler jobs.

The browser transport dependency is [libdatachannel v0.24.6](https://github.com/paullouisageneau/libdatachannel/releases/tag/v0.24.6),
the latest primary release observed on 2026-10-02. The annotated tag resolves to
commit `6b1e2e620f1e37f0eafeee702eaea0043cb305fd`; its recursive submodule
commits are checked before building and recorded in the ignored dependency
manifest. The local prefix is `build/browser-direct/deps/prefix`, seen as
`/src/build/browser-direct/deps/prefix` inside the container. Its exported target
is `LibDataChannel::LibDataChannel`. This build uses bundled libjuice/usrsctp,
OpenSSL, no media transport, and no dependency WebSocket implementation;
Overte retains its own signaling WebSocket and audio packet path.

```bash
python3 browser-direct-client/lab/build-native.py prepare
python3 browser-direct-client/lab/build-native.py configure
python3 browser-direct-client/lab/build-native.py build
# An individual target in the same pinned environment:
python3 browser-direct-client/lab/build-native.py build networking
python3 browser-direct-client/lab/build-native.py exec -- ctest --test-dir build/browser-direct/native -N
# Match the explicit direct-client native lane:
python3 browser-direct-client/lab/build-native.py build \
  networking-PacketTests networking-ReceivedMessageTests networking-SequenceNumberStatsTests \
  browser-direct-transport-WebRTCTransportTests \
  browser-direct-transport-BrowserEntityProjectionTests \
  browser-direct-transport-NativeAvatarAudioWireTests
python3 browser-direct-client/lab/build-native.py exec -- ctest \
  --test-dir build/browser-direct/native --no-tests=error --timeout 45 \
  --output-on-failure -R '^(browser-direct-transport-|networking-(PacketTests|ReceivedMessageTests|SequenceNumberStatsTests))'
```

Preparation performs the frozen Conan install with `--build=never --no-remote`.
Configuration enables `OVERTE_BROWSER_TRANSPORT`, disables Interface and tools,
and enables the networking and direct-transport test groups. Domain and assignment binaries belong
to this source checkout; the pinned image supplies dependencies only.
The headless compiler/test environment explicitly sets `QT_QPA_PLATFORM=offscreen`;
existing GUI-capable Qt test entry points still run their normal assertions.
The separate default-OFF compatibility build completed under
`build/browser-direct/native-default-off`, with no libdatachannel prefix and
read-only access to the source and existing Conan generators. Its successful
fresh configuration omitted the feature argument and recorded CMake's actual
default `OVERTE_BROWSER_TRANSPORT:BOOL=OFF`. It built the two server components and the
existing generic-policy headless networking programs PacketTests,
ReceivedMessageTests and SequenceNumberStatsTests: exactly three JUnit cases
passed, with Qt totals of 8, 7 and 7 and zero failures or skips. This does not
qualify all five ordinary networking programs, the complete 33-program generic
native lane or Interface. The existing external-service QtNetworkTests and
ResourceTests policy exclusions remain unchanged. All 739 generated compile
commands, expanded native linker commands, ELF NEEDED entries and resolved
dependencies exclude the DataChannel transport. The ordinary pinned shared
WebRTC audio-processing library remains an actual linker input for the native
targets; these server ELF dependency lists omit that unused input. No audio
disable flag or forced ELF dependency was introduced. Compilation ran offline
with four jobs only after the functional journey and four Chrome comparisons
ended; source fingerprint `191ba56a` and the live `b24` selection stayed unchanged.
The first configure's missing build-local `ConanToolsDirs.cmake` input is retained
as a negative; the fresh retry copied that exact pinned generated file into its
own build directory. Inspection then expanded Ninja's response-file commands
without rerunning the successful compiler or tests. The ignored
`runtime/default-off-build-qualification.json` binds all completed evidence and
preserves both inspection and configure history.

## Own test domain and process ownership

The checked resource plan is
[`browser-direct-client/lab/resources.json`](../../browser-direct-client/lab/resources.json).
The domain address is `overte://127.0.0.3:46102`; this loopback alias avoids
legacy native localhost-port discovery. Reserved ports are 46100–46120;
signaling is 46104, the browser's HTTP origin is 46106, assignment UDP sockets
are 46110–46115, native visitor UDP is 46116, fixture HTTPS is 46119, and the assignment monitor UDP is 46120.
Server ICE candidates bind only `127.0.0.3` in the separately checked UDP range
46130–46229. Server startup checks its own ports without requiring the browser
or fixture HTTP origin to stop.
Startup refuses occupied ports and verifies PID start ticks, process group,
executable, working directory and container ownership before cleanup.
Before live testing, `snapshot-runtime.py` copies the compiled binaries, shared
libraries, runtime resources and pinned transport prefix into an owned snapshot.
The launcher binds that snapshot read-only at the original container paths, so
subsequent compiler checks cannot replace mapped libraries under live clients.
Its ignored manifest records exact runtime byte hashes and the source fingerprint
at capture; source capture alone is explicitly not a compilation attestation.
After further source changes, rebuild and retest in a coordinated CPU window.
`snapshot-runtime.py candidate --output <new-owned-runtime-evidence.json>` hashes
the built binaries and resources without selecting a snapshot or changing live
services. If the bytes match the selected runtime, preserve its original manifest
and keep the existing server processes. `qualify-native-build.py` records the
unchanged before-build/final source fingerprints, observed successful build exit,
exact six passing test programs and candidate bytes in a separate private record.
That record supplements immutable history and does not replace live qualification.
For a fresh acceptance build, use the following public sequence after dependency
preparation/configuration, in place of the plain build/CTest commands above.
Choose a new evidence name for each build; source/build records are not overwritten.
The source-only step calls the versioned helper's public fingerprint function;
it neither selects a runtime nor attests that compilation has occurred. `set -e`
ensures the recorded build exit of zero follows an actually successful command.

```bash
set -e
umask 077
export DIRECT_NATIVE_RUN=qualification-1
python3 - <<'PY'
import importlib.util, json, os, pathlib, re, sys
repository = pathlib.Path.cwd().resolve()
sys.path.insert(0, str(repository / 'browser-direct-client/lab'))
spec = importlib.util.spec_from_file_location('native_snapshot', repository / 'browser-direct-client/lab/snapshot-runtime.py')
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)
name = os.environ['DIRECT_NATIVE_RUN']
if not re.fullmatch(r'[A-Za-z0-9._-]+', name):
    raise ValueError('Use a new simple evidence name')
sources, fingerprint = snapshot.source_fingerprint()
output = repository / 'build/browser-direct/lab/runtime' / (name + '-source-before.json')
output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
with output.open('x') as record:
    json.dump({'sourceFiles': sources, 'sourceFingerprint': fingerprint}, record, indent=2)
    record.write('\n')
PY
python3 browser-direct-client/lab/build-native.py build domain-server assignment-client \
  networking-PacketTests networking-ReceivedMessageTests networking-SequenceNumberStatsTests \
  browser-direct-transport-WebRTCTransportTests browser-direct-transport-BrowserEntityProjectionTests \
  browser-direct-transport-NativeAvatarAudioWireTests \
  > "build/browser-direct/${DIRECT_NATIVE_RUN}-build.log" 2>&1
python3 browser-direct-client/lab/build-native.py exec -- env QT_QPA_PLATFORM=offscreen ctest \
  --test-dir build/browser-direct/native --no-tests=error --timeout 45 -V \
  --output-junit "/src/build/browser-direct/${DIRECT_NATIVE_RUN}-checks.xml" \
  -R '^(browser-direct-transport-(WebRTCTransportTests|BrowserEntityProjectionTests|NativeAvatarAudioWireTests)|networking-(PacketTests|ReceivedMessageTests|SequenceNumberStatsTests))-test$' \
  > "build/browser-direct/${DIRECT_NATIVE_RUN}-checks.log" 2>&1
python3 browser-direct-client/lab/snapshot-runtime.py candidate \
  --output "build/browser-direct/lab/runtime/${DIRECT_NATIVE_RUN}-candidate.json"
python3 browser-direct-client/lab/qualify-native-build.py \
  --source-before "build/browser-direct/lab/runtime/${DIRECT_NATIVE_RUN}-source-before.json" \
  --candidate "build/browser-direct/lab/runtime/${DIRECT_NATIVE_RUN}-candidate.json" \
  --build-log "build/browser-direct/${DIRECT_NATIVE_RUN}-build.log" --build-exit-code 0 \
  --test-log "build/browser-direct/${DIRECT_NATIVE_RUN}-checks.log" \
  --junit "build/browser-direct/${DIRECT_NATIVE_RUN}-checks.xml" \
  --output "build/browser-direct/lab/runtime/${DIRECT_NATIVE_RUN}-build-qualification.json"
```

If the runtime bytes differ, stop the owned services, select a fresh snapshot,
and restart only when active browser tests have finished.
`python3 browser-direct-client/e2e/native-build-evidence.test.py` checks these
helpers with temporary fake files, including symlink copy/hash equivalence,
immutable history, source changes at both qualification boundaries and rejection
of zero executed checks, skips, errors or a different six-program inventory.
The browser CI lane runs this lightweight fixture without native services.
`qualify-runtime.py` records the six passing native test logs/JUnit report,
checks the selected snapshot against both live process identities, and verifies
actual loopback UDP sockets and assignment endpoints. Its output is the
private `runtime/native-qualification.json`; qualification reads do not change
the domain or its permissions.

```bash
python3 browser-direct-client/lab/manage.py preflight
python3 browser-direct-client/lab/manage.py prepare
python3 browser-direct-client/lab/snapshot-runtime.py
python3 browser-direct-client/lab/manage.py start
python3 browser-direct-client/lab/manage.py status
```

Use the successful build and verbose six-program CTest/JUnit evidence above
when recording live qualification. Its selected runtime must match that build's
candidate hash; keep the separate source/build record beside the live record.
No fields from either record need to be manually copied or sealed:

```bash
python3 browser-direct-client/lab/qualify-runtime.py \
  --test-log "build/browser-direct/${DIRECT_NATIVE_RUN}-checks.log" \
  --build-log "build/browser-direct/${DIRECT_NATIVE_RUN}-build.log" \
  --junit "build/browser-direct/${DIRECT_NATIVE_RUN}-checks.xml"
```

The build log must be retained from the corresponding completed native build;
select and start its own immutable snapshot before recording live qualification.
Keep those services alive for participant/browser qualification. After the
owned tests have ended, `python3 browser-direct-client/lab/manage.py stop`
performs ownership-checked cleanup.

All credentials, scene files, logs, profiles and the process registry live under
ignored `build/browser-direct/lab`; the admin credential is generated locally,
stored with mode 0600, and never printed. Guest permissions permit connection,
avatar entities and asset URL access, while world entity creation, asset writes,
administration and private user data remain unavailable. Packet verification stays enabled.
The assignment allowlist is explicitly `security.ac_subnet_allowlist` with
`127.0.0.3/32`; the built-in default only accepts `127.0.0.1/32`.
Startup also waits for all six real assignment services to register through the
authenticated admin endpoint before reporting domain readiness.
Its ignored `runtime/assignment-readiness.json` binds that observation to the
selected runtime hash and both domain/assignment PID/start ticks. All six types
must remain registered for three seconds across several child-status intervals.
Browser tests must check both current process identities and the hash before joining; stopping the
owned domain removes the marker.
The domain's index path supplies the actual selected Hub spawn
`/155.084,-98.5,-397.328/0,0,0,1` through its ordinary path response.
Domain/assignment containers have separate IPC namespaces and no GPU devices.
The launcher supplies `OVERTE_DOMAIN_SERVER_HTTP_ADDRESS=127.0.0.3`, using the
corresponding server bind-address support. Administration is at
`http://127.0.0.3:46100`. The first source-built runtime verified HTTP and signaling
loopback binds, but its native UDP sockets bound `0.0.0.0`; an advertised alias
and loopback-only permissions do not establish a loopback-only UDP bind. The
launcher now supplies the opt-in `OVERTE_NODE_UDP_ADDRESS=127.0.0.3` for domain
and assignment sockets. It preserves the reply source and the advertised local
address across socket rebinds; the production default remains `AnyIPv4`.

The legacy gateway owns ports 45100–45110, 45200–45205 and 45290, its own browser
ports including 8090/8095, and displays 94/95. They are not used here.

## Rendering resources and lease protocol

Software tests use private Xvfb displays 104/105, private profiles and private
audio servers. Current browser acceptance is Chrome-only; earlier Firefox
bootstrap observations are retained as historical evidence. Native rendering must set `LIBGL_ALWAYS_SOFTWARE=1`,
`GALLIUM_DRIVER=llvmpipe` and `__GLX_VENDOR_LIBRARY_NAME=mesa`; Chromium must use
SwiftShader with `--disable-gpu --use-angle=swiftshader`. Run render processes in
an isolated device namespace without `/dev/dri` or `/dev/nvidia*`, and verify
the renderer reported by the actual test. These tests do not consume the other
session's GPU or desktop and do not establish hardware fluidity.

Hardware rendering requires an exclusive cross-session window. The read-only
`graphics-status` command reports whether known external native/gateway owners
are alive. Their absence alone is not a lease: agree on the exclusive window,
check it again immediately before launching, record owner/start/expiry in this
laboratory's registry, and terminate only owned processes before releasing it.
A lock created only by this session cannot coordinate another session that does
not participate. Hardware tests remain unavailable until that coordination is
established; no external process is stopped to obtain a resource.

The dependency image lacks Xvfb, PulseAudio and FFmpeg. The optional software
tool bootstrap copies only checksum-verified immutable official Overte release
and Fedora package archives from a read-only cache, then extracts them into this
laboratory. It records every archive identity. It copies no live profile,
service state or existing extracted runtime. No user system package manager
configuration is changed.

```bash
python3 browser-direct-client/lab/prepare-software-tools.py \
  --artifact-cache /home/user/Documents/github/overte-browser-client/build/browser-lab
python3 browser-direct-client/lab/software-manage.py start
python3 browser-direct-client/lab/software-manage.py status
python3 browser-direct-client/lab/software-manage.py stop
# Wrap native/browser commands with actual GPU device isolation:
python3 browser-direct-client/lab/software-run.py --display 104 -- \
  python3 -c 'from pathlib import Path; assert not Path("/dev/dri").exists(); assert not list(Path("/dev").glob("nvidia*"))'
```

The software wrapper mounts the host filesystem read-only, permits writes only
under this worktree's ignored direct-client state, and creates private device,
PID and IPC namespaces. Its `/tmp`, including X11 sockets and locks, is also
private under `build/browser-direct/lab/runtime/tmp`. X11 clients must run
through this same wrapper to see those sockets. Browser arguments and measured renderer identities are
still required to distinguish llvmpipe/SwiftShader from unsupported rendering.
The separate Chrome permission UI diagnostic also requires Python's
`python-xlib` and Pillow modules on the host. The Ubuntu browser CI job installs
the `python3-xlib` and `python3-pil` packages; other distributions may package
Pillow as `python3-pillow`. Its X11 reader and trusted input helper verify only
this laboratory's registered Chrome process, profile and private display window.
Its bounded viewport must fit the private Xvfb screen. The lightweight
`python3 browser-direct-client/e2e/chrome-permission-ui.test.py` command checks
these ownership, UTF-8 title and window/input guards with fake window fixtures.
`software-manage.py` registers actual parent and descendant PID identities and
stops only those verified processes. Its authenticated X displays and two
separate PulseAudio servers use private sockets; audio servers load only null
sinks, the Unix client protocol, and the browser-only virtual capture remap
described below. Browser audio uses
`build/browser-direct/lab/runtime/b.sock`, native audio uses
the matching `n.sock`. These deliberately short socket paths fit Linux's Unix
socket path limit. The `software-profile/104` and `/105`
directories are separate from native/server and ordinary user profiles.

The optional `native-visitor.py start|status|stop` owns one checksum-pinned
2026.04.1 native Interface on display 105. Its ordinary domain path selects the
Hub spawn; its local observer reports the actual pose, nearby entity count,
remote avatar identities and synthetic input level into a private log. Ordinary
spawn evidence precedes the separately recorded native participant placement
described below. Compatibility with the newly built domain must be measured
before reporting native/browser coexistence.
The actual release's `--protocolVersion` output matches
`5622e88718593136a572e50ac20b3ade`. Its `--display Desktop` argument collides
with Qt's X11 display option, so the launcher selects the default desktop by
disabling VR plugins and uses `DISPLAY=:105` from the sandbox instead.
This pinned release accepts `hifi://127.0.0.3:46102` in its command-line URL;
using the modern `overte://` scheme leaves its domain hostname empty.
The native helper supplies a private CA bundle containing existing system roots
and this fixture's certificate through its own `SSL_CERT_FILE` and
`CURL_CA_BUNDLE` environment. The packaged Qt network backend did not honor
those variables for its actual FST request, so the same bundle is also mounted
read-only over existing CA bundle paths in that visitor's private filesystem
namespace. Certificate verification remains enabled and the host trust store
is unchanged. Actual native HTTPS loading is measured separately from a TLS
probe and a merely assigned skeleton URL.

The visitor also uses a private read-only `/etc/hosts` copy mapping only
`stun1.l.google.com` to unused loopback STUN port 19302. This explicitly
restricted network setup exercises the packaged native client's normal STUN
fallback for an entirely loopback domain. Its original external STUN mapping
was advertised to the loopback assignment services; native scene delivery
still requires independent evidence after the fallback. No host DNS, firewall, native
authentication, or other session's files are changed.

The wildcard native visitor can advertise a LAN address while its replies to
the explicitly bound loopback servers come from `127.0.0.1`. Reliable UDT
handshake state must use the same endpoint in both directions. The server
selection correction applies only to a verified, registered native UDP peer
when the server is explicitly bound to loopback and the observed loopback
port equals the selected advertised port. Its regression uses actual native
Ping/PingReply authentication and completes a real UDT reliable handshake;
native world receipt is measured separately through the visitor.

The qualified endpoint-correction runtime has SHA-256
`f114b8dc5d0541e813f580ce33b9e26353d61e14b8a3bfb82f2afe8ce3381177`.
All six selected native CTest targets passed in 1.40 seconds with zero skipped
tests. The unchanged packaged visitor then received 53 nearby entities,
loaded 34 ATP models and the historical HTTPS bridge, and rendered the real
world on its isolated software display. These are view-dependent native
counts, rather than proof that its current frustum contains every selected
entity. The ignored `runtime/native-visitor-qualification.json` and
`runtime/native-loopback-endpoint-proof.json` bind observations to the live
process, source asset hashes and actual EntityServer endpoint
`127.0.0.1:46116`; the ordinary-spawn screenshot is
`runtime/native-world-f114-ordinary.png` under the same lab state.

The later RTC generation qualification uses immutable runtime
`4534e078914a7efa22d37f78661ea5a805cda745db69d71b8e486b807a2aab9a`.
All six native checks passed in 1.89 seconds without failures or skips. Its
packaged visitor's initial automatic spawn remained at the origin; both
negative startups are retained. After an explicitly recorded normal native
`/` path retry, the actual Hub pose yielded 64 nearby entities and 45 loaded
ATP models, with the real HTTPS bridge and 69-joint, two-mesh mannequin.
That ordinary-path observation precedes the separate native participant
placement. It qualifies native world receipt after the retry; the initial
automatic spawn is not reported as passed.

A historical native-observer-only restart added the bounded motion test
control while retaining the same server runtime and scene. That particular
launch reached the ordinary Hub pose automatically, before its separate
initial placement, and loaded 53 nearby entities and 34 ATP models with the
actual HTTPS bridge and mannequin. Its archived qualification records no
ordinary-path retry. The earlier failed startups and their successful retry
remain in the private history; this later observation does not turn those
negative startups into successes or establish reliable automatic startup.

The later version-2 observer on `4534` used a separately recorded supervised native
launch. Its initial automatic spawn remained near the origin; an ordinary
`/` retry then yielded 64 nearby entities and 45 loaded ATP models before the
separate participant placement. Two earlier version-2 launches disappeared
before qualification and remain archived as negatives, with their termination
cause unknown. The final observer script has SHA-256
`d45e18cd1f8b80aba49c3f5511262a80df2b164972b6e7ffd60bb73f0759a9d1`;
the qualification binds that source, motion-control version 2 and the current
registered native process. That qualification retained the `4534` core runtime.
Its getter-only evidence records Hips, Head, LeftArm and RightArm using both
the parent-relative SkeletonModel getters and the avatar-object-frame absolute
getters, which include the native rig-to-avatar Y180 conversion. Those spaces
are labeled separately; the getter observations do not themselves establish
network-frame or rendered-pose parity.

The final ON source/build qualification uses source fingerprint
`191ba56a74169a1cc4b2ecf6a8fd2bd2eb5fa9df155a9883393c1ed8367b0dec`
and immutable runtime
`b24fe1e9aa4268574864e3d359a862588917d1876053f044af81e1ef8737efe0`.
The six complete native programs passed in 1.92 seconds with no failures or
skips. Its separate final build record retains the observed compiler exit,
verbose test/JUnit hashes, unchanged source inventory and candidate bytes;
the earlier immutable manifests remain unchanged. The first packaged-native
launch after this upgrade exited 139 before world qualification. An unchanged
supervised native-only retry reached the ordinary Hub pose automatically,
before participant placement, and loaded 53 nearby entities, 34 ATP models,
the genuine HTTPS bridge and the 69-joint, two-mesh mannequin. Actual same-launch
Qt HTTPS FST/FBX hashes and all six loopback service endpoints were verified.
The first launch remains a negative result; the successful retry does not
establish reliable automatic startup. This final observer retains the exact
version-2 source hash and getter-only joint evidence described above.

`prepare-native-avatar.py` verifies the six real Overte mannequin files against
both their fixed browser fixture hashes and the tracked native resource bytes,
then copies those unchanged files and their license into the owned HTTPS
fixture. The native observer explicitly selects
`https://127.0.0.1:46119/default-avatar/defaultAvatar_full.fst` through
`MyAvatar.useFullAvatarURL` after observing the actual ordinary Hub pose, then
observes `MyAvatar.skeletonModelURL`. The model setup waits for that pose rather
than assuming a connected socket has completed native initialization. Its private provenance record and separate
`DIRECT_LAB_NATIVE_MODEL_SETUP` marker identify this participant test setup.
Actual `Graphics.getModel` mesh/vertex counts, joint counts and HTTPS bridge
`Entities.isLoaded` observations supplement resource-load diagnostics; an
assigned model URL alone does not establish that the native renderer loaded it.

```bash
python3 browser-direct-client/lab/prepare-native-avatar.py
python3 browser-direct-client/lab/native-visitor.py start
python3 browser-direct-client/lab/native-visitor.py status
```

If the packaged visitor logs the correct ordinary path response but remains
at the origin, preserve that negative startup before using the bounded
`native-visitor.py retry-path` diagnostic. This sends the exact same ordinary
`hifi://127.0.0.3:46102/` address through native `location.handleLookupString`,
requiring another actual domain path response. It records the before pose and
navigation separately in `DIRECT_LAB_NATIVE_PATH_RETRY`; it neither supplies
coordinates nor moves the browser. Only one retry is accepted per owned native
launch. A successful lookup log alone does not qualify the resulting pose.

`qualify-native-visitor.py capture-ordinary` binds the actual Hub observation
to the current native PID, start ticks and qualified server runtime before
placement. After `place-ahead`, its `qualify` operation requires current loaded
world/model graphics, actual same-launch native Qt HTTPS FST/FBX hashes and all
six services' activation of that native session's loopback UDP endpoint. It
records any ordinary path retry explicitly. These counts describe the native
view; they do not qualify the browser's complete selected scene.
Both operations require an actual version-2 observer sample no older than six
seconds and the exact source digest recorded when the current owned process
started. Qualification also rejects an observed or already attempted motion
trial in that session. The helper writes the validated `nativeMotionControlVersion`
and `observerScriptSHA256` fields required by the browser launcher itself;
no private post-processing helper is needed. A later trial needs a newly started
and independently qualified visitor, preserving the earlier evidence.

```bash
python3 browser-direct-client/lab/qualify-native-visitor.py capture-ordinary
python3 browser-direct-client/lab/native-visitor.py place-ahead
python3 browser-direct-client/lab/qualify-native-visitor.py qualify
```

`python3 browser-direct-client/e2e/native-visitor-qualification.test.py` exercises
that public command sequence against temporary synthetic observations and an
owned local test process, then submits its result to the actual browser-start
guard. It also rejects changed source/process identity, stale or malformed
samples, consumed trials and missing ordinary world/placement/service/Qt asset
evidence. These helper tests neither launch a native client nor establish real
browser/native interoperability.

After independently recording its ordinary spawn, `native-visitor.py place-ahead`
can move only this owned native participant three metres forward through its
own `MyAvatar.position` API. Its separate `DIRECT_LAB_NATIVE_SETUP` observation
and private control record distinguish this explicit avatar/audio test setup
from the domain's spawn response. The browser is not relocated. The packaged
Qt XMLHttpRequest implementation returns an empty error for a custom `file:`
GET, so the same bounded, session-bound JSON instruction is exposed as a
static file by this lab's HTTPS fixture. This contains only the native
participant's public pose/session and forwards no domain protocol traffic.

The separate `motion-move` and `motion-restore` operations exist only for a
coordinated native-to-browser position test after that initial qualification.
Version 2 allows one native-only one-metre movement along world minus Z and one
return per process and session, preserving the original ordinary-spawn and
initial-placement records. This follows the existing bridge's long direction;
the earlier X trial crossed its lateral edge and is retained as a failed test.
The host verifies the current qualified runtime, native process, session and
placement request; the native observer rejects stale, repeated or mismatched
instructions. Commands expire after six seconds, the host waits at most eight
seconds for a newer matching actual native observation, and the static command
is disabled after either outcome. `nativeMotionTest` records the apply-time
origin, target, actual applied positions, phase and native sequence. The real
browser must independently observe a newer loaded remote-body displacement and
continued mesh draws; the control receipt alone does not prove network sync.
Restore retains the original one-metre height tolerance, together with the
session, process, placement, sequence, expiry and replay guards. Source-contract
checks reject the obsolete X offset and late callbacks; they do not substitute
for the actual native-to-Chrome motion test.
Do not invoke these operations outside the agreed live test step:

```bash
python3 browser-direct-client/lab/native-visitor.py motion-move
python3 browser-direct-client/lab/native-visitor.py motion-restore
```

Chrome's real media API filtered the initial monitor-only input environment.
The owned browser PulseAudio server now exposes `browser_microphone`, a
`module-remap-source` over its verified private `browser_input.monitor` null
sink, at mono 48 kHz. The browser launcher selects that virtual source; native
input remains `native_input.monitor`. `prepare-browser-microphone` refuses an
active browser registry, verifies the owned Pulse process and null-sink master,
and changes only this private server. No host default source, physical card or
fake Chrome media-device flag is used. An independent stock Chrome capability
probe obtained and then stopped an actual live 48 kHz mono capture track.

```bash
# Only in a coordinated browser-idle window:
python3 browser-direct-client/lab/software-manage.py prepare-browser-microphone
```

`synthetic-audio.py tone|capture --participant browser|native` sends PCM only
to that participant's private input null sink or records its real output
monitor. Captures retain sample hashes, RMS and frequency amplitudes, without
equating an output signal with proof of a particular remote sender. Native and
browser reference tones can use 523.25 Hz and 659.25 Hz respectively; physical
microphone capture remains untested.

`asset-stats.py` samples the existing authenticated DomainServer view of
AssetServer metrics for a bounded period. It binds samples to both current
native process identities and the runtime hash, retaining only numeric
connection/window/RTT/ACK/retransmission metrics and public session IDs.
It prints no administrator credential or usernames and opens no new server.
The own domain has no positive `asset_server.max_bandwidth` override;
the native UDT default is `-1`, while congestion control still governs transfer.

```bash
python3 browser-direct-client/lab/asset-stats.py --duration 45 --interval 1 \
  --output build/browser-direct/lab/runtime/asset-stats-probe-1.json
```

On the qualified `f114` runtime, the renderer-free Chrome diagnostic received
the unchanged 4,143,539-byte Day EXR in 2.605 seconds and the 1,824,496-byte
waves model in 0.869 seconds, with matching hashes. During the subsequent
full-scene probe, reported AssetServer RTT increased from 0–2 ms to
350–861 ms, throughput peaked at 0.920 Mbit/s instead of 13.513 Mbit/s,
and the browser reported prolonged main-thread tasks. Full model/skybox
loading therefore remained unqualified. The separate timing contexts must
be retained when evaluating a loading optimization. After both natural
leaves, the admitted browser Agent and its AssetServer stats entry disappeared;
the later full-scene observation contained no post-leave RTC write-error records.

The subsequent `30b` CPU probe recorded up to 747 ms AssetServer RTT and
0.279 Mbit/s peak throughput. Its sampled CPU profile mostly contained opaque
native V8 frames, so it does not identify a particular renderer function.
The first actual session-worker probe `h` on `4534` reached native admission,
83 entities and the Hub path. Its 180-second server trace observed the browser
peer for the first 20 samples, with 0–5 ms RTT and 4.211 Mbit/s peak throughput.
That probe then ended with a browser-side disconnect before complete model
or skybox qualification. Native logs show an explicit client disconnect
request before Agent removal; they do not identify the initiating browser
error. After its natural close, only the native Agent and two native/DS
AssetServer peers remained, with no RTC write-error records. These short-run
metrics support improved network scheduling, without establishing full-scene
completion or hardware performance.

The later coalescing-qualified worker probe `j` retained the same `4534` runtime,
scene, assets, image quality and 120-second model limit. It rendered the real
HTTPS bridge and original Day EXR skybox without an initiating worker failure,
but did not complete all 55 models within that limit. Its 180-second native
trace measured 0–8 ms RTT and 11.182 Mbit/s peak throughput. Those measurements
end before the normal leave/reconnect stage. Six unsuppressed RTC write warnings
were printed during initial admission, and six suppression summaries during
fresh reconnect; individual suppressed occurrence times are unavailable.
After the probe, only the native Agent and two native/DS AssetServer peers
remained, with no subsequent failed-write records. This does not establish zero
write failures during the admitted main stage or complete scene acceptance.

The later mandatory journey `direct-a` completed all 55 model geometries and
available textures in 155 seconds under the measured 180-second software limit,
with the unavailable original PSD recorded explicitly. The same run measured
the synthetic native 523.25 Hz tone in 383,814 actual browser output frames.
Its host-PID test harness failed before any native motion operation; reverse
audio and the complete journey were not qualified. The host relay corrected
that namespace assumption in `direct-b`, which retained the scene-rendering
positives but exposed a braced entity UUID conversion error. No native motion
operation occurred in either run. Both post-run native checks retained one
native Agent, two native/DS AssetServer peers and zero subsequent failed-write
records. The bounded AS traces end before the journeys' final cleanup stages.

The subsequent `direct-c` journey passed complete selected-scene geometry,
available textures, real native rig draws, trusted movement/picking/jump,
native-to-browser synthetic audio and lifecycle cleanup. Its actual X motion
settled 1.086 metres below the apply-time origin; the unchanged height guard
rejected restore. Chrome also found no capture device in the then monitor-only
environment. These failures remain archived separately from the version-2
bridge-direction and virtual-source repairs.

The historical `direct-d` journey used the frozen version-2 observer and private
remap. Both synthetic audio directions passed: the native 523.25 Hz reference
reached 383,397 browser output PCM frames, and the actual browser capture counter
advanced from 130 to 1,050 audio frames while the 659.25 Hz reference appeared
in 384,480 native output PCM frames. Complete 83-entity/55-model geometry,
available maps, the explicitly unavailable original PSD, real HTTPS/Day skybox
draws, upright native rig, trusted inputs and lifecycle checks also passed.
Its one-shot native minus-Z move produced a measured 1.0257-metre displacement
and then restored the exact original pose within the unchanged strict guard.
Chrome's loaded remote owner/body bounds stayed stale, so ongoing
native-to-Chrome position synchronization and the overall journey remain
unqualified. The consumed trial and its primary failure are retained.
The bounded 180-sample AssetServer trace measured 0–7 ms RTT and
11.306 Mbit/s peak throughput before the final stages. After the actual end,
the native Agent and two native/domain AssetServer peers remained, with zero
subsequent failed-write records. There were 54 failed-write records over the
whole current runtime; no zero-during-run claim is made.

The final `direct-chrome-20261003-e` journey on `b24` passed all 25 criteria,
including complete selected-scene geometry and available maps, the explicit
original PSD warning, real HTTPS bridge and Day skybox draws, upright native
rig draws, both ongoing position directions, trusted input/collision checks,
both real synthetic voice directions and fresh reconnect/error cleanup.
The guarded native minus-Z movement reached the actual loaded remote body
and its rendered bounds, then restored within the unchanged strict guard.
That version-2 trial is consumed and restored; it must not be reset or reused.
The result SHA-256 is
`2c3b0f9afaf351601cbe9d9920d2c44ca068691333bcba69063eaa8224065dab`.
Its bounded AssetServer trace covers only the early 180 seconds of the nearly
12-minute journey, with 0–5 ms RTT and 10.328 Mbit/s peak throughput. After its
natural end, one native Agent and two native/domain AssetServer peers remained,
with zero subsequent RTC failed-write records. This is separate from the
18 records accumulated over the runtime before that cleanup observation.

The subsequent four fresh Chrome profiles tested image sharing in the fixed
ON/OFF/OFF/ON order over the same 83-entity/55-model scene, source assets,
image quality, runtime and restored native participant. All four cases passed;
the result SHA-256 is
`4cce98e7975664333f9754dbcfd49673db81d14e905eaa6601bb92ccfd5a8b9d`.
No native transition, scripted motion or supplemental lab sampler ran during
these cases. Their post-end cleanup again retained one native Agent and two
AssetServer peers, with zero subsequent RTC failed-write records. The 42 records
over the whole runtime are retained without a zero-during-run claim. These are
software-only comparisons between two Chrome settings; the native visitor's
view-dependent subset does not establish a browser-versus-native loading result.

`inspect-cleanup.py` records the actual result end time, current native process
identities, Agent and AssetServer peer counts, and post-end failed-write records.
It refuses an active browser registry and emits only filtered private evidence:

```bash
python3 browser-direct-client/lab/inspect-cleanup.py \
  --probe-result build/browser-direct/e2e/scene-probe-chrome-20261003-j/results.json \
  --statistics build/browser-direct/lab/runtime/asset-stats-worker-scene-j-4534.json \
  --output build/browser-direct/lab/runtime/new-cleanup-proof.json
```

## Actual Hub scene provenance

`prepare-scene.py` reads this repository's actual historical Hub snapshot,
`interface/resources/serverless/overte-hub-original.json`, with SHA-256
`f104f22166f4a085240291bb3ac800eb510b08aee19320055a7e32a16599a509`.
Its last file commit is `5ac64721763a8423bea82b744a58513ab3d7017c`; its embedded
Content Info identifies content version `2019-12-06_12-12-23`.
This is historical Hub data, not a current public-server observation.

The local selection retains entities whose bounds intersect a 30 m spawn region,
all Zones, and complete parent/child trees. It preserves real model, texture,
material, collision and transform data. Remote executable scripts and their
userData are excluded from the isolated test world. The current selection has
83 entities and SHA-256
`13017c3233d1cb9edfb1b9a9df80445b002c5ed700409964c4c30bba255c46a2`.
Original HTTPS asset references are retained; downloaded third-party asset
bytes and the copied scene are never added to Git. The ignored provenance
manifest records the selection and exact source/output identities.
It does not establish licenses for the individual CDN assets; those bytes stay
in the private local cache and are excluded from distributable artifacts.

```bash
python3 browser-direct-client/lab/prepare-scene.py
```

The source CDN's observed model FST and material responses omit browser CORS
permission. The first models-only ATP adaptation changed the 55 model URLs in
the same 83 entities and had SHA-256
`41f60920188877f1fc65c6cc8b2e0b0d841c767360f4877f974764fb9c260e79`.
It is retained as a separate local artifact. The current ATP base also adapts
eight actual Zone skybox/ambient URL fields and has SHA-256
`9982ab70d21b1421bcd7b4bdccf9fe8806a31d0b46a4a46b8a174a037b937e55`.
All other entity properties and the original historical selection remain unchanged.

The import initially completed 237 actual files and 32,185,785 source bytes.
Adding native compressed alternatives yielded 375 files and 133,652,513 bytes.
The enumerated model and Zone closure has 389 files, 239,553,156 source bytes,
144 KTX files and three EXR files, with zero failed enumerated downloads. The
importer's supported-extension discovery omits PSD references: the actual dock
material additionally declares an unavailable original `bridges_d.psd`. The
native and browser retain geometry with incomplete-texture evidence; full
original texture completeness is not claimed. The imported closure remains
within the 512-file, 512 MiB total and 64 MiB individual-file limits.
Geometry and image bytes retain their original hashes. Textual manifest changes
only replace absolute references to the same CDN with the matching ATP paths;
the ignored asset manifest records both source and served hashes.
The Zone import also includes the explicitly referenced historical host
`files.thingvellir.net`, mapped under `/hub-external/files.thingvellir.net/`.

The shared test scene `hub-with-atp-and-https.json.gz` changes one existing bridge
model from that ATP base to the isolated HTTPS origin. Its SHA-256 is
`7038f0e796b069a1e0f3ceaa64456e13ba2c0a8bf7306b326d9031bf19aa96ad`.
Bridge entity `{b42a2c92-2a33-400d-a6b4-30e3d3ff2282}` is 1.68 m from the ordinary
spawn; its FST, geometry, material, texture metadata and JPEG/KTX alternatives
form a seven-file relative closure with unchanged original bytes. Other models
and all Zone assets retain their ATP paths. This allows actual rendered HTTPS
and ATP evidence in the same unchanged scene, without a protocol proxy.

Four original `compoundShapeURL` fields and five `animation.url` fields still
reference the original public CDN. They are retained in the private scene and
listed in its audit, rather than rewritten without a verified asset closure.
The browser's measured collisions use loaded visual-mesh triangles; compound
collision hull and entity animation parity are outside the current claim.

Native baking is disabled for these imported assets using its existing hidden
mapping convention: the baked path maps to the original file's hash. The native
AssetServer still answers ordinary ATP packets, without recompressing the selected
geometry or images. This is a separately labeled transport adaptation, not a
claim that the public Hub already supports ATP or direct browser connections.

```bash
# Run while this owned domain is stopped:
python3 browser-direct-client/lab/prepare-assets.py --all-models --include-zones
python3 browser-direct-client/lab/manage.py prepare
python3 browser-direct-client/lab/https-fixtures.py start
```

The optional static fixture server at `https://127.0.0.1:46119` serves the same
recorded actual bytes and permits only the reserved browser origin in its CORS
header. It has a private, short-lived self-signed certificate; only the local test
context trusts its specific public key. It performs no domain/protocol forwarding,
directory listing or out-of-tree file access. `https-fixtures.py stop` cleans up
only its verified owned process.

Before accepting requests, it freezes exact URL names to an inventory of prepared
in-tree files. Requests only select an inventoried path; the handler opens that
same file without a second request-path translation and hashes the opened stream
for its audit. Traversal, directories, missing files and out-of-tree symlinks
remain unavailable. Assets added after inventory cannot expand its authority.
The fixture directory is trusted and immutable while serving; this does not
provide atomic protection against a hostile local writer changing filesystem
entries between validation and open. `python3
browser-direct-client/e2e/https-fixtures.test.py` checks the actual handler on
ephemeral loopback HTTP with temporary assets, without certificates or a browser.

The initial Ed25519 fixture certificate worked with the packaged Qt HTTPS
client but produced Chrome `ERR_SSL_VERSION_OR_CIPHER_MISMATCH`. The fixture
now generates RSA-2048 certificates with SHA-256, retaining TLS 1.2 or newer.
`rotate-tls` requires the owned server to be stopped and retains the prior
certificate/key in a versioned private directory. After rotation, restart the
native visitor with its new process-local CA bundle and recalculate Chrome's
specific SPKI pin. The result must be verified by actual Chrome requests.
The bounded private `runtime/https-fixture-requests.jsonl` records successful
static GET/HEAD paths, byte counts and served hashes, without request headers.

This private-domain fixture does not prove direct access to the live
`overte_hub`. The real public server must support the new transport before a
public direct-access test can pass. Synthetic audio evidence and physical
microphone evidence must remain separate.
