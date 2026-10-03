# SPDX-License-Identifier: Apache-2.0
"""Use the same reviewed launcher as the managed lab, including staged copies."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if (HERE.parent / 'native_launch.py').is_file():
    sys.path.insert(0, str(HERE.parent))
from native_launch import (CAPS, PROFILE, tmpfile_filter, sealed_filter, private_directory,
                           base_command, confinement, require_confinement, exec_confined,
                           exec_final, owned_native_confinement, launch_managed_document,
                           host_policy, managed_confinement)
