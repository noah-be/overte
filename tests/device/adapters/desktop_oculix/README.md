# Desktop adapter

The directory name is historical. One adapter exposes the common Overte
desktop behavior contract, but it deliberately uses three automation
boundaries:

| Target session | Input backend | Screenshot evidence |
| --- | --- | --- |
| Visible Fedora/GNOME Wayland | XDG RemoteDesktop portal v2 plus a persistent `libei` sender | Not advertised; use the in-client probe and adapter logs |
| Headless Linux | Private GPU-backed Mutter/Xwayland session plus `xdotool` | ImageMagick, restricted to the owned X11 window |
| Interactive Windows and macOS | OculiX 4.x | OculiX, restricted to the resolved Overte window |

The in-client probe verifies the camera, avatar, scene, process, and tablet
state after each input operation. A successfully delivered key or pointer
event alone never counts as passed behavior.

Copy `targets.example.json` outside the checkout, keep that file mode 0600, and
export `OVERTE_DESKTOP_TARGETS` to it. Selectors, local paths, permissions, and
executable hashes belong to this private target configuration and must not be
published in test artifacts.

## Visible Fedora/GNOME

Visible debugging runs keep Overte in the logged-in, GPU-accelerated GNOME
session. Input is sent only through the XDG RemoteDesktop portal v2 and
`libei`; it is never sent with direct `xdotool`, XTEST, Java Robot, or OculiX
automation on the host display. Those direct paths cause GNOME permission
prompts without providing the persistent, scoped session needed by the lab.

Provisioning includes one deliberate portal run while the user is present.
That run requests `persist_mode=2` and stores the returned single-use restore
token in the user's private state directory. The token is atomically replaced
after each successful restore. Normal suites omit the authorization option,
start one daemon for the whole suite, reuse its private same-UID socket for all
actions, and stop it during cleanup. If a restore unexpectedly opens another
GNOME dialog, stop the run and repeat the separately announced provisioning
step; never retry prompts in a loop.

The visible Fedora target does not currently advertise screenshot capture.
The RemoteDesktop grant requests keyboard and pointer devices only, not a
ScreenCast/PipeWire source. This keeps screen sharing outside the test's
authority while the shared Overte probe still supplies behavioral evidence.

Build, authorization, runtime, and command details are in
[`README.wayland-libei.md`](README.wayland-libei.md). The daemon binary is built
from the repository source and its SHA-256 is pinned in the private lab
configuration before it is started.

## Headless Linux

Unattended Linux runs use `isolatedX11: true`. The lifecycle owner starts
SHA-256-pinned `dbus-run-session`, its explicitly selected `dbus-daemon`, and
Mutter with `--headless`, one configured
virtual monitor, and a unique Wayland socket in mode-0700 runtime/state
directories. A repository sentinel atomically hands off Mutter's generated
`DISPLAY` and mode-0600 Xauthority file. The lifecycle accepts exactly one
Mutter-owned Xwayland process, bound by PID, PGID, start token, executable,
argv, and digest; reuse, crash recovery, and cleanup fail closed on ambiguity.
Inside the private D-Bus session, a lifecycle-owned guard prevents desktop
portal and accessibility-bus activation and returns Mutter's defined
`org.gnome.SessionManager.NotInInitialization` response to activation-
environment exports. Mutter therefore starts Xwayland without
`-enable-ei-portal`; the lifecycle rejects any Xwayland that still advertises
that switch. This keeps XTEST local to the owned display without making a
RemoteDesktop, ScreenCast, or RemoteInteraction request.

Before Interface starts, `xrandr` must report exactly one monitor and the
configured root extent. `glxinfo -B` must report direct rendering and match the
target's explicit vendor and renderer allowlists. `llvmpipe`, `softpipe`,
`swrast`, Software Rasterizer, and SwiftShader are always rejected. Interface
receives only the private Xwayland `DISPLAY`/`XAUTHORITY` with
`QT_QPA_PLATFORM=xcb`; the compositor's Wayland socket and private D-Bus
address are not inherited.

Only this owned X11 session may use the configured, SHA-256-pinned `xdotool`.
ImageMagick captures the resolved Overte window into a mode-0600 artifact.
Headless look uses a bounded right-button drag on the exact PID-owned X11
window. Movement and tablet open/close use the fixture's strict, same-origin
`key-hold` command and the probe's allowlisted `Controller.Actions` mapping.
This avoids layout-dependent XTEST key translation while still requiring the
real Overte movement/tablet effects; commands cannot set avatar or UI state
directly and every hold is timer-released. PID-scoped `windowactivate --sync`
remains mandatory before pointer input. Raw `windowfocus`/XSetInputFocus and
`xdotool --window` keyboard injection remain forbidden.
Mutter, Xwayland, `dbus-run-session`, `dbus-daemon`, Python, `glxinfo`, `xrandr`,
`xdotool`, and ImageMagick must have absolute paths and verified digests in the private
target file. Headless execution is GPU-only; a software renderer is an
infrastructure failure, not a slower fallback. Visible-session acceptance
remains a separate gate.

Disabled target slots may retain placeholder paths and hashes. All runtime
paths and digests are validated when the target is enabled, before discovery
can expose it or any lifecycle process can start.

## Windows and macOS

Windows and macOS use the platform OculiX IDE JAR because the API-only JAR has
no `-r` script runner. Pin the JAR digest in the private target, run it with an
open-source OpenJDK 17 or newer, and configure the executable inside a macOS
application bundle, for example
`/Applications/Overte.app/Contents/MacOS/Overte`, rather than the `.app`
directory.

Portable-baseline targets additionally pin an open-source FFmpeg executable
and arguments containing `{durationSeconds}` and `{output}`. Use `x11grab` on
the private Linux display, `gdigrab` on Windows, and the audited AVFoundation
screen input on macOS. The adapter rejects unknown placeholders and accepts
only a non-empty MP4 containing an `ftyp` header. OculiX supplies the scoped
window screenshot on Windows/macOS; private Linux uses ImageMagick.

On macOS, run Jenkins as a LaunchAgent of the logged-in lab user, grant
Accessibility and Screen Recording to the stable Java/agent paths, and define
an explicit `PATH` in the LaunchAgent environment.

On Windows, run Jenkins as an interactive user process, never as a Session 0
service. The adapter rejects Session 0. Keep Jenkins/Java and Overte at the
same integrity level; UAC secure desktop and higher-integrity windows
intentionally block synthetic input.

Use a dedicated OS account/profile for every desktop lab. The adapter disables
launcher, updater, and multi-instance inheritance, but Overte preferences,
keymaps, and plugins otherwise come from that account.
