#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run a software renderer on a private display with hardware GPU devices absent."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import resource
import subprocess

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "build/browser-direct"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--display", choices=("104", "105"), required=True)
    parser.add_argument("--hosts-file", type=Path)
    parser.add_argument("--ca-bundle", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a renderer command is required")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    profile = STATE / "lab/software-profile" / args.display
    private_tmp = STATE / "lab/runtime/tmp"
    private_tmp.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ("config", "data", "cache", "runtime", "tmp"):
        (profile / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = {
        **os.environ, "DISPLAY": f":{args.display}", "WAYLAND_DISPLAY": "",
        "LIBGL_ALWAYS_SOFTWARE": "1", "GALLIUM_DRIVER": "llvmpipe",
        "__GLX_VENDOR_LIBRARY_NAME": "mesa", "QT_QPA_PLATFORM": "xcb",
        "XDG_CONFIG_HOME": str(profile / "config"), "XDG_DATA_HOME": str(profile / "data"),
        "XDG_CACHE_HOME": str(profile / "cache"), "XDG_RUNTIME_DIR": str(profile / "runtime"),
        "TMPDIR": str(profile / "tmp"), "DBUS_SESSION_BUS_ADDRESS": "unix:path=/dev/null",
    }
    mesa_egl = Path("/usr/share/glvnd/egl_vendor.d/50_mesa.json")
    if mesa_egl.exists():
        environment["__EGL_VENDOR_LIBRARY_FILENAMES"] = str(mesa_egl)
    authority = STATE / "lab/runtime/xauthority"
    if authority.exists():
        environment["XAUTHORITY"] = str(authority)
    # The new /dev contains only basic pseudo-devices. No DRM/NVIDIA device is
    # mounted, even when a browser ignores a renderer preference or crashes.
    arguments = ["bwrap", "--unshare-user", "--unshare-pid", "--unshare-ipc",
                 "--die-with-parent", "--new-session", "--ro-bind", "/", "/",
                 "--bind", str(STATE), str(STATE), "--bind", str(private_tmp), "/tmp",
                 "--dev", "/dev", "--proc", "/proc"]
    for supplied in (args.hosts_file, args.ca_bundle):
        if supplied is not None and (not supplied.resolve().is_relative_to(STATE.resolve())
                                     or not supplied.is_file()):
            parser.error("process-local network/trust inputs must be owned files under build/browser-direct")
    if args.hosts_file is not None:
        arguments.extend(["--ro-bind", str(args.hosts_file.resolve()), "/etc/hosts"])
    if args.ca_bundle is not None:
        candidates = ("/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/cert.pem",
                      "/etc/pki/tls/certs/ca-bundle.crt",
                      "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem")
        targets = sorted({str(Path(candidate).resolve()) for candidate in candidates
                          if Path(candidate).is_file()})
        if not targets:
            parser.error("no existing system CA bundle paths are available for a private mount")
        for target in targets:
            arguments.extend(["--ro-bind", str(args.ca_bundle.resolve()), target])
    arguments.extend(["--chdir", str(REPO), "--", *command])
    raise SystemExit(subprocess.call(arguments, cwd=REPO, env=environment))


if __name__ == "__main__":
    main()
