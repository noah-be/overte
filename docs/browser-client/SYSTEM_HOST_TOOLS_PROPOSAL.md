# System host tools for the isolated acceptance laboratory

This is a reviewed-candidate implementation in the continuation checkout. It has not changed or restarted an existing laboratory. Fedora remains the default tool preparation mode. Native Overte2026.04.1 client/server and Qt5.15.3 input artifacts retain the same reviewed checksums; system mode changes only the host Xvfb/PulseAudio/slirp selection.

## Proposed commands

A clean Ubuntu24.04 x86_64 host needs Python3.11+, Node22.12+, FFmpeg with PulseAudio/X11 input, `pactl`, Xvfb, PulseAudio with its actual modules, bubblewrap, slirp4netns, `xauth`, `ip`, unprivileged user/IPC/PID/mount/network namespaces, `rpm2cpio`, `cpio`, `ar`, `tar` with zstd support and `g++`. Packages are installed through the normal host administrator/CI image procedure; this mode never installs a service or changes the desktop audio server.

From the repository root:

```bash
python3 browser-client/lab/test_host_tools.py
python3 browser-client/lab/manage.py prepare --host-tools system
python3 browser-client/lab/manage.py preflight
python3 browser-client/lab/manage.py start --gateway
node browser-client/tests/integration/real-session.mjs
OVERTE_LAB_BROWSER=firefox node browser-client/tests/integration/real-session.mjs
python3 browser-client/lab/manage.py stop
```

Executables are discovered through the operator's PATH and then resolved/verified as absolute regular executable files. PulseAudio modules are discovered from a fixed shallow set of standard library locations, including versioned `/usr/lib/pulse-*/modules` directories; more than32versioned candidates require explicit selection. Both `module-native-protocol-unix.so` and `module-null-sink.so` must exist inside the selected canonical module directory. A host with different layouts can supply exact paths:

```bash
python3 browser-client/lab/manage.py prepare --host-tools system \
  --xvfb /usr/bin/Xvfb --pulseaudio /usr/bin/pulseaudio \
  --pulse-modules /actual/pulseaudio/modules --slirp /usr/bin/slirp4netns
```

Use `--pulse-library-path /actual/audio/library` only when that selected executable/module set requires additional shared libraries; repeat at most8times. Host audio clients and FFmpeg do not inherit native Qt/AppImage library paths. Selection persists under the lab's ignored `config/host-tools.json`; subsequent commands verify it instead of changing mode implicitly. Host selection arguments outside `prepare` are rejected. Preparation refuses to replace tools or fixture files while the recorded managed laboratory is running.

`OVERTE_LAB_ROOT=/absolute/dedicated/directory` selects another output/state directory for preparation/preflight. It does **not** change the reserved domain ports/displays: an actual `start` still refuses occupied ports/displays and cannot coexist with the existing primary fixture on the same endpoints. This option permits an isolated prerequisite check while preserving the primary fixture, and a fresh CI runner has no endpoint conflict. The root cannot be `/`, `/tmp`, the user's home or the repository itself.

## Fail-closed preflight

System preparation requires actual preflight success before saving its selected tool descriptor. Preflight executes actual unprivileged namespaces and bubblewrap namespace setup without disabling a host policy. It resolves native and host ELF dependencies through `ldd`, including domain/assignment/Interface binaries, the XCB plugin, pinned QtTest and the compiled native input extension. Missing dependencies stop preparation, rather than being skipped or described as compatible. It checks FFmpeg's actual PulseAudio/X11 input registration and starts a temporary private PulseAudio instance with only two null sinks. Actual `pactl` responses must identify the expected synthetic input monitor and output sink; this verifies the selected module ABI and client interoperability. That process is always terminated and its private directory removed. No physical devices or existing audio daemon are selected or modified.

Preflight subprocess deadlines and output are bounded. It does not establish that native GUI graphics, QML/WebEngine, domain connection or voice journeys work on Ubuntu; those remain separate actual-start/journey acceptance requirements. Ubuntu's AppArmor/user-namespace policy may reject the required isolation. Such rejection is a failed prerequisite, never permission to change global policy or run an unsandboxed worker.

## Candidate CI sequence, not yet wired

Use a separate Ubuntu24.04 native-journey job so ordinary component tests do not inherit a changed audio server or unbounded acceptance runtime. Install the listed prerequisites and actual Chromium/Firefox binaries. Build the production client, run path/CLI tests, prepare with system tools, and require the preflight. Start one real managed domain and independent native Interface participant, provision actual ATP/HTTPS assets, and lower/read back anonymous/localhost permissions using the existing private generated administrative credential. Then run the unchanged short Chromium and Firefox world/assets/native-position/interaction/bidirectional synthetic-voice/leave/rejoin assertions sequentially. Always stop only recorded owned process groups.

The hosted runner's software graphics are a functional result, not public-Hub hardware fluidness evidence. Earlier software movement failures must remain visible until the actual underlying cause is resolved; do not lower movement/pixel/audio assertions for CI. Public-Hub tests and30-minute endurance are not part of this proposed job. Endurance was explicitly cancelled by the user.

Publish only curated aggregate metadata, approved browser/native screenshots and safe failure summaries. Do not upload `runtime`, administrative credentials, profiles, raw entity/participant identifiers, session directories, unfiltered logs or audio recordings. Actual Ubuntu dependency closure and complete native journeys remain unproved until the candidate mode runs on that runner. No workflow, GitHub resource or namespace policy has been changed by this proposal.

## Verified candidate contracts

The frozen candidate passed all12Python path/CLI/negative-preflight contract tests, Python compilation and Bash syntax validation. Those tests use explicitly labelled temporary executable fixtures and mocked prerequisite failures. They do not prove an actual native dependency closure, namespace/audio preflight, GUI or shared-domain journey. Exact file/base/patch identities and these pending boundaries are recorded in `system-host-tools-prototype-manifest.json`.
