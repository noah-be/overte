#!/usr/bin/env python3
"""Keep Mutter's private Xwayland XTEST path local to the lifecycle."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402


SESSION_MANAGER_NAME = "org.gnome.SessionManager"
SESSION_MANAGER_PATH = "/org/gnome/SessionManager"
DENIED_DESKTOP_SERVICES = (
    "org.freedesktop.portal.Desktop",
    "org.a11y.Bus",
)
SESSION_MANAGER_XML = """
<node>
  <interface name="org.gnome.SessionManager">
    <method name="Setenv">
      <arg type="s" name="name" direction="in"/>
      <arg type="s" name="value" direction="in"/>
    </method>
  </interface>
</node>
"""


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mutter", required=True)
    parser.add_argument("mutter_arguments", nargs=argparse.REMAINDER)
    values = parser.parse_args()
    if values.mutter_arguments[:1] == ["--"]:
        values.mutter_arguments = values.mutter_arguments[1:]
    if not os.path.isabs(values.mutter) or not values.mutter_arguments:
        parser.error("an absolute Mutter path and arguments are required")
    return values


def main() -> int:
    args = arguments()
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    interface = Gio.DBusNodeInfo.new_for_xml(SESSION_MANAGER_XML).interfaces[0]

    def reject_setenv(_connection, _sender, _object_path, _interface_name,
                      method_name, _parameters, invocation) -> None:
        if method_name != "Setenv":
            invocation.return_dbus_error(
                "org.freedesktop.DBus.Error.UnknownMethod", "unsupported method")
            return
        # Mutter treats this documented gnome-session response as a failed
        # environment export.  It consequently omits Xwayland's
        # -enable-ei-portal switch, keeping XTEST entirely inside this private
        # display instead of requesting a RemoteDesktop portal connection.
        invocation.return_dbus_error(
            "org.gnome.SessionManager.NotInInitialization",
            "private headless session does not export an activation environment",
        )

    registration = connection.register_object_with_closures2(
        SESSION_MANAGER_PATH, interface, reject_setenv, None, None)
    if registration == 0:
        raise RuntimeError("failed to register private session manager guard")
    for name in (SESSION_MANAGER_NAME, *DENIED_DESKTOP_SERVICES):
        reply = connection.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus",
            "org.freedesktop.DBus", "RequestName",
            GLib.Variant("(su)", (name, 4)), GLib.VariantType("(u)"),
            Gio.DBusCallFlags.NONE, -1, None)
        if reply.unpack()[0] != 1:
            raise RuntimeError(f"private D-Bus name is already owned: {name}")

    # Owning the portal and accessibility bus names without exporting either
    # interface prevents toolkit helpers from auto-starting those desktop
    # services inside this deliberately minimal session.  Interface itself
    # receives no session-bus address at all.
    child = subprocess.Popen([args.mutter, *args.mutter_arguments])

    loop = GLib.MainLoop()
    result = {"status": 1}

    def child_exited(_pid: int, status: int) -> None:
        result["status"] = os.waitstatus_to_exitcode(status)
        child.returncode = result["status"]
        loop.quit()

    def forward_signal(signum: int, _frame) -> None:
        try:
            child.send_signal(signum)
        except ProcessLookupError:
            pass

    GLib.child_watch_add(child.pid, child_exited)
    signal.signal(signal.SIGTERM, forward_signal)
    signal.signal(signal.SIGINT, forward_signal)
    loop.run()
    connection.unregister_object(registration)
    return result["status"]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GLib.Error, OSError, RuntimeError, ValueError) as error:
        print(f"GPU headless session guard failed: {error}", file=sys.stderr)
        raise SystemExit(2)
