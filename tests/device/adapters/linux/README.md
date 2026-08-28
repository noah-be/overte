# Linux desktop adapter

This target-owned adapter exposes the common Overte desktop behavior contract
through two Linux automation boundaries:

Fedora, Ubuntu, and openSUSE are CI/lab rows rather than code branches; see
[`DISTRIBUTION_MATRIX.md`](DISTRIBUTION_MATRIX.md) for the acceptance model.

| Target session | Input backend | Screenshot evidence |
| --- | --- | --- |
| Visible Fedora/GNOME Wayland | XDG RemoteDesktop portal v2 plus a persistent `libei` sender | Not advertised; use the in-client probe and adapter logs |
| Headless Linux | Private GPU-backed Mutter/Xwayland; `xdotool` pointer plus bounded probe Controller actions | ImageMagick, restricted to the owned X11 window |

The in-client probe verifies the camera, avatar, scene, process, and tablet
state after each input operation. A successfully delivered semantic input or pointer
event alone never counts as passed behavior.

Targets that set both `probe.kind: injected-test-script` and
`clientControl.kind: fixture-command-http` additionally advertise
`navigation.enter-domain`, `asset.load`, `scene.load`, and `sound.play`. At
launch the adapter copies the repository probe into the target's private state
directory. Commands are POSTed to the controlled fixture's same-origin
`/e2e-client-command.json` route and must be echoed exactly before success is
reported. The running probe accepts only versioned scene reload, navigation,
controlled Image-entity, sound-channel, and semantic input-hold commands. Scene
reload and navigation assign `Window.location` inside the existing Interface
process; asset loading creates exactly one client-local tagged Image entity.
Sound commands are POSTed
unchanged to the controlled fixture's
`/sound-command.json` endpoint, and the probe polls that endpoint directly.
Probe snapshots and fixture HTTP telemetry remain independent completion
evidence. A missing probe, command route, fixture acknowledgment, or stable
Interface process identity fails closed.

This in-client path never uses the clipboard, global keyboard shortcuts,
external URL handlers, or desktop portals. It therefore behaves identically on
visible Wayland/Xwayland and private GPU-backed X11 without expanding their
input or screen-capture authority. Omitting `clientControl`
keeps the four capabilities disabled; pairing it with a host-file probe is a
configuration error.

Copy `targets.example.json` outside the checkout, keep that file mode 0600, and
export `OVERTE_LINUX_TARGETS` to it. Selectors, local paths, permissions, and
executable hashes belong to this private target configuration and must not be
published in test artifacts.

## Visible Fedora/GNOME

Visible debugging runs keep Overte in the logged-in, GPU-accelerated GNOME
session. Input is sent only through the XDG RemoteDesktop portal v2 and
`libei`; it is never sent with direct `xdotool`, XTEST, or Java Robot
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
Headless look uses a bounded right-button drag. PID-scoped
`windowactivate --sync` precedes every input; raw `windowfocus`/XSetInputFocus
is forbidden because it bypasses the window-manager activation contract.

Mutter headless Xwayland discards both global XTEST keyboard events and
window-directed XSendEvent keyboard events on the validated Fedora host. The
headless adapter therefore sends only semantic `forward`, `backward`, `left`,
`right`, `down`, `jump`, and `tablet` input holds through the controlled local
probe. The fixture validates the whitelist and a 50-10000 ms duration before
the probe routes the hold to its corresponding temporary Controller action;
replacement, timer expiry, and probe shutdown all release the held action.
The probe never assigns avatar position or velocity. Movement, jump, flight,
grounding, and tablet behavior still require independent probe evidence. Tablet toggles
stop as soon as the probe observes the requested state, with at most three
pulses in five seconds.
Mutter, Xwayland, `dbus-run-session`, `dbus-daemon`, Python, `glxinfo`, `xrandr`,
`xdotool`, and ImageMagick must have absolute paths and verified digests in the private
target file. Headless execution is GPU-only; a software renderer is an
infrastructure failure, not a slower fallback. Visible-session acceptance
remains a separate gate.

Disabled target slots may retain placeholder paths and hashes. All runtime
paths and digests are validated when the target is enabled, before discovery
can expose it or any lifecycle process can start.

Use a dedicated OS account/profile for every desktop lab. The adapter disables
launcher, updater, and multi-instance inheritance, but Overte preferences,
keymaps, and plugins otherwise come from that account.
