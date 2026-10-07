# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Exercise the actual confined owner's launch boundary without starting a child."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'src'
sys.path.insert(0,str(SOURCE))
spec=importlib.util.spec_from_file_location('reviewed_owner_launcher',SOURCE/'trusted_owner.py')
owner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


class LauncherEnvironment(unittest.TestCase):
    def test_native_loader_configuration_does_not_enter_host_launcher_environment(self):
        args=['--clearenv','--setenv','LD_LIBRARY_PATH','/reviewed/native/lib','--','/reviewed/native']
        config={'command':'/usr/bin/bwrap','args':args,
                'environment':{'LD_LIBRARY_PATH':'/reviewed/native/lib','HOME':'/owned/private-worker'}}
        with patch.object(owner.subprocess,'Popen')as launch:
            child=owner.launch_sandbox(config)
        self.assertIs(child,launch.return_value)
        launch.assert_called_once_with(['/usr/bin/bwrap',*args],
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        self.assertEqual(config['environment']['LD_LIBRARY_PATH'],'/reviewed/native/lib')


if __name__=='__main__':unittest.main()
