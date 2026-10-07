#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exec one recorded helper with kernel parent-death ownership on Linux."""
import ctypes
import os
import signal
import sys


def main():
    if len(sys.argv) < 3:
        raise RuntimeError('owned-exec-requires-parent-and-command')
    parent = int(sys.argv[1])
    if parent <= 1 or not os.path.isabs(sys.argv[2]):
        raise RuntimeError('owned-exec-invalid-parent-or-command')
    libc = ctypes.CDLL(None, use_errno=True)
    # The command replaces this process, keeping Popen identity and its session.
    # Set before testing parent identity: the parent may die in either interval.
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), 'parent-death-ownership-unavailable')
    if os.getppid() != parent:
        raise RuntimeError('owned-exec-parent-exited-before-registration')
    os.execvpe(sys.argv[2], sys.argv[2:], os.environ)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError):
        # Do not disclose command arguments, workspace paths or environment.
        print('owned-helper-launch-failed', file=sys.stderr)
        raise SystemExit(1)
