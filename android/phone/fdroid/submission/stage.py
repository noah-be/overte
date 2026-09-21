#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage a disabled F-Droid submission draft from one committed source revision."""
import argparse
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[4]
BASE = 'android/phone/fdroid/submission'
STORE = 'android/phone/fastlane/metadata/android/en-US'


def git_file(commit, path):
    return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT)


def stage(output, revision):
    commit = subprocess.check_output(['git', 'rev-parse', '--verify', revision + '^{commit}'], cwd=ROOT, text=True).strip()
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('invalid commit')
    # Read the template AND store text from the selected revision, never a dirty
    # working copy. Reject a commit without the actual build entry point.
    git_file(commit, BASE + '/build.py')
    template = git_file(commit, BASE + '/metadata/io.github.noah_be.overte.phone.yml.in').decode()
    if template.count('@COMMIT@') != 1:
        raise ValueError('metadata requires exactly one commit placeholder')
    if output.exists():
        raise ValueError('output must be a new directory')
    paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', commit, '--', STORE], cwd=ROOT, text=True).splitlines()
    contents = {Path(path).relative_to(STORE): git_file(commit, path) for path in paths}
    if not all(Path(name) in contents for name in ('title.txt', 'short_description.txt', 'full_description.txt')):
        raise ValueError('store text missing from selected commit')
    output.mkdir(parents=True)
    metadata = output / 'metadata'
    metadata.mkdir()
    (metadata / 'io.github.noah_be.overte.phone.yml').write_text(template.replace('@COMMIT@', commit))
    for relative, content in contents.items():
        target = metadata / 'io.github.noah_be.overte.phone/en-US' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    print(f'Staged disabled submission draft for {commit}; nothing uploaded')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', default='HEAD')
    args = parser.parse_args()
    try:
        stage(args.output.resolve(), args.commit)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'submission staging failed: {error}\n')
