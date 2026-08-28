# Linux distribution matrix

Fedora, Ubuntu, openSUSE, display servers, desktop environments, and GPU
drivers are execution dimensions of `linux-main`; they are not permanent Git
branches. Every lab machine uses the same `linux-desktop` adapter manifest and
a private target entry. Distribution-specific differences therefore remain in
provisioning, executable paths, pinned digests, and CI parameters rather than
forking the behavior contract.

The initial acceptance matrix is:

| Distribution family | Release lane | Visible session | Unattended session |
| --- | --- | --- | --- |
| Fedora Workstation | current stable | GNOME Wayland + portal v2/libei | private Mutter/Xwayland GPU session |
| Ubuntu Desktop | current LTS | GNOME Wayland + portal v2/libei | private Mutter/Xwayland GPU session |
| openSUSE | Tumbleweed snapshot | GNOME Wayland + portal v2/libei | private Mutter/Xwayland GPU session |

Rows are enabled only after the machine satisfies the adapter's fail-closed
runtime checks. A green row must record the distribution/release, desktop
session type, GPU vendor/renderer, Overte build, and suite in Jenkins metadata;
private selectors and local paths remain redacted. Adding a KDE, X11-visible,
new GPU-vendor, or additional distribution row requires provisioning and an
acceptance run, not a new permanent branch.

For visible sessions the target must provide RemoteDesktop portal interface v2
or newer, a compatible libei sender, a logged-in operator-owned session for the
one deliberate authorization, and `QT_QPA_PLATFORM=xcb` when Interface runs
through Xwayland. The adapter never falls back to direct input on the host
display.

For unattended sessions the target pins every lifecycle executable and digest,
accepts exactly one compositor-owned Xwayland, rejects `-enable-ei-portal`,
proves one configured monitor, and verifies a hardware renderer against the
target allowlists. Software rendering is an infrastructure failure on every
distribution.

Changes first pass all hardware-free tests once on `linux-main`. Jenkins then
fans the same commit and manifest out across provisioned rows. A row-specific
failure stays attached to that target; adapter changes remain shared and are
reviewed once against `linux-main`.
