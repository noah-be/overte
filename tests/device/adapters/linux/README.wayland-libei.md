# Visible Linux Wayland input

`wayland_libei_daemon.c` is the native, GPU-visible Linux input path for a
logged-in GNOME/Wayland device-lab session. It does not capture or share the
screen. It asks XDG RemoteDesktop portal v2 for keyboard and pointer control,
obtains the private EIS file descriptor with `ConnectToEIS`, and sends all
input through a libei sender. The Overte window therefore stays on the user's
real Wayland/GPU desktop; unattended runs use the separately owned GPU-headless
Mutter/Xwayland lifecycle described in the adapter README.

The first deliberate setup run requests `persist_mode=2`. If GNOME grants
persistence, the portal returns a single-use `restore_token`. The daemon stores
that opaque value in a target-specific, user-owned mode-0600 file and replaces
it atomically with the newly returned token after every successful restore.
The token is never printed or sent through the command socket. Subsequent runs
require the saved token and omit `--authorize`.

Portal behavior has one important boundary: the portal specification says an
invalid or revoked restore token is ignored and the normal prompt is shown.
There is no portal-v2 `no-prompt` flag. Keep one daemon alive for the entire
suite so individual test actions never recreate a portal session, and treat an
unexpected prompt as an expired lab permission that must be re-authorized in a
separately announced maintenance step.

## Fedora build

All runtime and build components below are open source Fedora packages:

```sh
sudo dnf install gcc make pkgconf-pkg-config glib2-devel libei-devel
cd tests/device/adapters/linux
make -f wayland-libei.mk
```

The runtime needs `xdg-desktop-portal` and the desktop-specific portal backend;
Fedora GNOME uses `xdg-desktop-portal-gnome`. The implementation is compiled
against GIO's Unix-fd D-Bus API and libei 1.6 or newer. It requires
RemoteDesktop portal interface version 2 or newer and fails closed otherwise.

The source follows the installed, authoritative interfaces and upstream API:

- [XDG RemoteDesktop portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html)
- [libei client API](https://libinput.pages.freedesktop.org/libei/api/libei_8h.html)
- [libei sender API](https://libinput.pages.freedesktop.org/libei/api/group__libei-sender.html)

## Deliberate first approval

Run this only while the user is present and after announcing that one GNOME
remote-interaction approval is expected. The adapter owns the resulting daemon
process and records its exact process identity for later cleanup:

```sh
OVERTE_LINUX_TARGETS=/private/targets/linux.json \
  python3 adapter.py authorize-input \
  --target linux-desktop-01
```

Accept keyboard/pointer control and persistent access in GNOME. No screen or
PipeWire source is selected. Stop the daemon with the control command below;
the rotated restore token remains private under
`$XDG_STATE_HOME/overte-device-lab/wayland-input/fedora-visible/restore-token`
(`~/.local/state` is GLib's fallback when `XDG_STATE_HOME` is unset).

Every later `app.launch` starts the same foreground daemon without
`--authorize`, or reuses the exact adapter-owned process if the authorization
step left it running. To exercise the daemon directly during its own
development, the equivalent restore-only command is:

```sh
./_build/wayland-libei/wayland-libei-daemon --target fedora-visible
```

The process writes exactly one non-secret readiness line after the portal and
libei devices are usable:

```text
READY socket=/run/user/1000/overte-device-lab/wayland-input/fedora-visible/input.sock
```

The adapter should start this process once, wait for `READY`, use it for all
modules, and send `shutdown` during cleanup. SIGTERM/SIGINT also close the
portal session and release held keys/buttons. A per-target state lock rejects
parallel daemons. State/runtime target directories are mode 0700, the token and
command socket are mode 0600, and command clients must have the same UID.

## Adapter integration API

`wayland_libei_client.py` can be imported or used as a strict CLI. The CLI
prints JSON only for `status`; successful input commands are silent.

```sh
python3 wayland_libei_client.py --target fedora-visible status
python3 wayland_libei_client.py --target fedora-visible motion 80 0
python3 wayland_libei_client.py --target fedora-visible button 273 down
python3 wayland_libei_client.py --target fedora-visible button 273 up
python3 wayland_libei_client.py --target fedora-visible key 17 down
python3 wayland_libei_client.py --target fedora-visible key 17 up
python3 wayland_libei_client.py --target fedora-visible shutdown
```

Codes are Linux evdev codes from `linux/input-event-codes.h`, not X11 keycodes:
`BTN_RIGHT=273`, `KEY_W=17`, and `KEY_TAB=15`.
For example, mouse-look is right-button down, one or more relative motions,
then right-button up. Forward movement is W down, an adapter-controlled bounded
wait, then W up. Tablet open and close both hold Tab for 100 ms, matching
Overte's `Keyboard.Tab` to `Actions.ContextMenu` mapping. The bounded hold is
intentional because an immediate same-tick press/release is not reliably
consumed by the application input mapper.

The wire protocol is intentionally narrow and same-UID only:

```text
status
motion <finite-dx> <finite-dy>
button <evdev-code> down|up|click
key <evdev-code> down|up|tap
shutdown
```

Each connection carries exactly one bounded line and one response. The daemon
remains alive, so these short connections do not create new portal sessions or
GNOME dialogs. Use `python3 -m unittest -v tests/test_wayland_libei_client.py` for
the hardware-free endpoint/protocol tests. Those tests never contact D-Bus or
the portal.

## Visible debug coordination

Visible debug runs share the operator's desktop and do not synthesize window
activation. Before starting an input phase, the operator explicitly signals
readiness after Overte and the pointer are on the intended monitor. The adapter
then uses the configured logical `desktopSize`; it does not change desktop
focus or invoke a separate focus-confirmation mechanism.
