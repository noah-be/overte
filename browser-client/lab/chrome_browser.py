# SPDX-License-Identifier: Apache-2.0
"""Open the laboratory in Google Chrome without a system-browser fallback."""
import os
from pathlib import Path
import re
import shutil
import subprocess


def chrome_executable(environment=None):
    environment = os.environ if environment is None else environment
    configured = environment.get("OVERTE_BROWSER_CHROME_EXECUTABLE")
    if configured is not None:
        if not isinstance(configured, str) or not configured or "\0" in configured or not Path(configured).is_absolute():
            raise RuntimeError("OVERTE_BROWSER_CHROME_EXECUTABLE must be an absolute Google Chrome executable")
        candidate = configured
    else:
        candidate = shutil.which("google-chrome-stable") or shutil.which("google-chrome")
    if not candidate:
        raise RuntimeError("Install Google Chrome or set OVERTE_BROWSER_CHROME_EXECUTABLE to its absolute executable")
    try:
        executable = Path(candidate).resolve(strict=True)
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise OSError()
        version = subprocess.run([str(executable), "--version"], env=dict(environment),
                                 capture_output=True, text=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("The selected Google Chrome executable could not be verified") from error
    if not re.fullmatch(r"Google Chrome(?: for Testing)? \d+\.\d+\.\d+\.\d+\s*", version.stdout):
        raise RuntimeError("The selected executable is not Google Chrome")
    return str(executable)


def open_chrome(url, environment=None, executable=None):
    environment = os.environ if environment is None else environment
    executable = chrome_executable(environment) if executable is None else executable
    return subprocess.Popen([executable, "--new-window", url], env=dict(environment),
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
