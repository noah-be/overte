#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Online dependency acquisition into a NEW store; never builds the Android app."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
from test_store import verify_inventory, write_inventory, stage_runtimes, store_paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-store', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    base, output = store_paths(args.base_store, args.output, root)
    if any(p.is_symlink() for p in base.rglob('*')):
        raise ValueError('Base store must not contain symlinks')
    for name in ('gradle.properties', 'init.gradle', 'init.gradle.kts', 'init.d'):
        if (base / name).exists():
            raise ValueError('Base store must not contain user initialization')
    verify_inventory(base)
    os.umask(0o077)
    shutil.copytree(base, output)
    (output / 'COMPLETE').unlink()
    project = output / 'quality-gate-acquisition'
    shutil.copytree(Path(__file__).with_name('gradle-tests'), project)
    home = output / 'acquisition-home'
    home.mkdir()
    env = {key: os.environ[key] for key in ('PATH', 'JAVA_HOME', 'LANG') if key in os.environ}
    env.update(HOME=str(home), GRADLE_USER_HOME=str(output))
    with (output / 'test-acquisition.log').open('wb') as log:
        subprocess.run([root / 'android/common/gradlew', '--no-daemon', '-p', project,
                        'resolveGateTestInputs'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=1800)
    stage_runtimes(output, output / 'robolectric-sdk')
    write_inventory(output)
    verify_inventory(output)
    print('Android Phone test dependency acquisition: PASS')


if __name__ == '__main__':
    main()
