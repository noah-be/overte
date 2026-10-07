# Ubuntu24.04 native journey prerequisite plan

This is a candidate plan, not a wired or passed CI gate. No live service, workflow, host security policy or GitHub resource was changed. The system-host-tools candidate contracts passed12tests. Complete native journeys on Ubuntu remain unproved.

## Verified binary requirements

Read-only `readelf` on the pinned2026.04.1 artifacts establishes that the assignment client requires GLIBC2.38, while the domain server/assignment client require GLIBCXX3.4.32 and CXXABI1.3.15. The AppImage does not supply `libstdc++.so.6`; an actual target-host library must satisfy those versions. Its packaged libraries supply Qt5.15.3, OpenSSL3, node127, WebRTC audio processing and systemd dependencies. Presence of a bundled top-level SONAME does not prove its transitive closure.

The parent's cached official Ubuntu24.04 image reports24.04.5, libc2.39-0ubuntu8.9 and libstdc++14.2.0-4ubuntu2~24.04.1. These exceed the directly inspected symbol-version floors. The actual target binaries/plugins still need a target-host dynamic-loader check.

The [official current runner inventory](https://raw.githubusercontent.com/actions/runner-images/main/images/ubuntu/Ubuntu2404-Readme.md) reports image20260920.314.1 and GCC12/13/14, Firefox156 and Chrome153. Record the actual versions and package identities in each run; this mutable inventory cannot replace runtime attestation.

## Narrow isolated dependency experiment

The reviewed closure-only Containerfile and Python auditor are under `/tmp/overte-ubuntu-native-closure`. Pin the official base image to the digest inspected from the cached image. Install the candidate runtime/system-host packages from its ordinary signed Ubuntu repositories during image construction. Do not select an arbitrary third-party package source or change host services.

Copy only release `appimage/squashfs-root/usr/lib`, `usr/bin/interface`, `usr/plugins/platforms`, `server/opt/overte`, the matching pinned `qt-tablet` tree and compiled `native-input` output into a dedicated temporary directory. These are artifact trees, not runtime profiles. Copy that directory into a newly owned container at `/native` with `podman cp`; do not bind-mount/relabel an existing live laboratory. Run its auditor with network disabled. It records actual Ubuntu package versions and six ELF hashes; missing libraries, required symbol versions, missing targets or loader failures must fail.

This experiment proves dependency closure only. It does not start a domain, invoke physical audio, initialize QtGUI/WebEngine or prove actual worker isolation. A default container may deny nested namespace operations independently of the hosted runner. Do not add privileged mode, remove seccomp/AppArmor restrictions or treat a denied preflight as successful. The exact Ubuntu host/runner must subsequently pass the normal unmodified kernel/audio preflight.

## Proposed dedicated runner sequence

A separate `ubuntu-24.04` job keeps the real native journey distinct from component checks. Keep checkout/setup-node action identities pinned as in the existing browser workflow. Use a bounded ordinary job timeout sufficient for artifact preparation and two short journeys; no endurance test is required.

1. Install Node22 and locked dependencies; build the production distribution. Install the actual Playwright Chromium and Firefox engines with dependencies.
2. Install `python3`, `g++`, `binutils`, `rpm2cpio`, `cpio`, `zstd`, `ffmpeg`, `pulseaudio`, `pulseaudio-utils`, `xvfb`, `xauth`, `bubblewrap`, `slirp4netns`, `iproute2`, Mesa/OpenGL and the native GUI runtime dependencies. The loader preflight, rather than package names alone, decides compatibility.
3. Run the host-tools contract tests. Execute `python3 browser-client/lab/manage.py prepare --host-tools system`, then `preflight`. Preparation retains the pinned native and Qt5.15.3 SDK/artifacts. Missing ELF dependencies, private Pulse module ABI or required namespaces fail the job; no skip, policy relaxation or unsandboxed fallback is allowed.
4. Start the real domain/assignments/independent native observer/gateway with `manage.py start --gateway`. Existing private generated administration, asset provisioning, anonymous/localhost permission lowering/readback, isolated IPC/profile/displays and owned PID/group cleanup remain intact.
5. Run the unchanged short core journey sequentially in both actual engines. Use a separate Xvfb display for browser presentation and software Mesa, for example:

```bash
xvfb-run --auto-servernum --server-args='-screen 0 1280x900x24' \
  env LIBGL_ALWAYS_SOFTWARE=true GALLIUM_DRIVER=llvmpipe \
  bash -c 'OVERTE_LAB_BROWSER_DISPLAY="$DISPLAY" node browser-client/tests/integration/real-session.mjs && OVERTE_LAB_BROWSER_DISPLAY="$DISPLAY" OVERTE_LAB_BROWSER=firefox node browser-client/tests/integration/real-session.mjs'
```

The same real domain and independent observer verify world/ATP/HTTPS assets, keyboard/mouse movement, shared avatars/position agreement, bidirectional generated440Hz/997Hz audio at actual output sinks, object interaction, leave and rejoin. A software renderer can prove those functional assertions; it is not public-Hub hardware fluidness evidence. Retain failing movement/pixel/audio observations without reducing any assertion.

6. An always-run cleanup step invokes `python3 browser-client/lab/manage.py stop`, which checks recorded PID start ticks/process-group ownership. Publish only curated aggregate metadata and approved screenshots. Do not upload raw profiles, credentials, runtime directories, entity/participant identifiers, unfiltered logs or audio recordings.

A preparation cache may retain only checked download artifacts, never generated tokens, live PID state, profiles or permissions files. Actual native/gui/audio journeys, safe artifact curation and CI job wiring remain pending review and execution. No30-minute session is proposed; the user explicitly cancelled endurance tests.
