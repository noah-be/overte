#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepare only a dedicated checkout's dependencies; no fixture startup."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import signal
import time
from run import checked_source, checked_executable, safe_environment, stop_owned, checkout_clean


def installer_command(command):
    # Downloads retain normal networking. Only the installer's process tree is
    # private; no fixture services start here. Kernel PID-init destruction also
    # covers descendants that create independent sessions during installation.
    return [sys.executable, str(Path(__file__).resolve().parent/'owned-exec.py'),
        str(os.getpid()), checked_executable('unshare'), '--user', '--map-current-user', '--keep-caps',
        '--pid', '--fork', '--mount-proc', '--kill-child=KILL', '--',
        checked_executable('setpriv'), '--bounding-set=-all', '--inh-caps=-all',
        '--ambient-caps=-all', '--', sys.executable, str(Path(__file__).resolve()),
        '--execute-installer', *command]


def main():
    if len(sys.argv)>2 and sys.argv[1]=='--execute-installer':
        # Namespace setup retains only its setup authority until setpriv.
        # Verify the actual non-root, five-zero-set result before any installer.
        from gates import isolated_identity
        isolated_identity()
        os.execvpe(sys.argv[2],sys.argv[2:],os.environ)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    if os.getuid() == 0 or not Path('/etc/fedora-release').is_file():
        raise RuntimeError('qualification-requires-reviewed-nonroot-Fedora-agent')
    checked_source(repo, args.source_sha)
    if not checkout_clean(repo):
        raise RuntimeError('dependency-preparation-requires-clean-exact-source')
    if (repo/'build/browser-lab').exists():
        raise RuntimeError('qualification-must-not-reuse-or-replace-an-existing-laboratory')
    for name in ('node','npm','git','python3','g++','ar','tar','rpm2cpio','cpio','dnf',
                 'ffmpeg','pactl','bwrap','unshare','mount','setpriv','ip','xauth','xvfb-run'):
        checked_executable(name)
    runtime = repo / 'build/jenkins-browser-ci'
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime.chmod(0o700)
    npm_config = runtime/'empty-npmrc'
    npm_config.write_text('')
    env = {**safe_environment(), 'PLAYWRIGHT_BROWSERS_PATH': str(runtime/'browsers'),
           'NPM_CONFIG_USERCONFIG':str(npm_config),'NPM_CONFIG_GLOBALCONFIG':str(npm_config),
           'XDG_CACHE_HOME':str(runtime/'cache'), 'OVERTE_LAB_ROOT':str(repo/'build/browser-lab')}
    version = subprocess.check_output(['node','-p','process.versions.node'],text=True,timeout=10,env=env).strip()
    major,minor,_patch = map(int,version.split('.'))
    if major < 22 or (major == 22 and minor < 12):
        raise RuntimeError('Node-does-not-meet-reviewed-package-engine')
    commands = [
        (['npm','ci'],repo/'browser-client'),
        (['npx','playwright','install','chromium','firefox'],repo/'browser-client'),
        ([sys.executable,'browser-client/lab/manage.py','prepare'],repo),
    ]
    stages = []
    cancelled=False
    def cancel(_number,_frame):
        nonlocal cancelled
        cancelled=True
    signal.signal(signal.SIGTERM,cancel)
    signal.signal(signal.SIGINT,cancel)
    for number,(command,directory) in enumerate(commands):
        with (runtime/f'prepare-{number}-private.log').open('wb') as log:
            result = subprocess.Popen(installer_command(command),cwd=directory,env=env,
                stdout=log,stderr=log,start_new_session=True)
            deadline=time.monotonic()+1200
            failure=None
            try:
                while result.poll() is None:
                    if cancelled:failure='cancelled';break
                    if time.monotonic()>deadline:failure='dependency-deadline';break
                    if os.fstat(log.fileno()).st_size>64*1024*1024:failure='private-log-size-limit';break
                    time.sleep(.1)
            finally:
                stop_owned(result)
        stages.append({'stage':['npm-ci','browser-downloads','pinned-native-artifacts'][number],
                       'passed':result.returncode==0 and failure is None,'failureCategory':failure})
        (runtime/'prepare-summary.json').write_text(json.dumps({'sourceSHA':args.source_sha,
            'nodeVersion':version,'passed':all(row['passed'] for row in stages),'stages':stages})+'\n')
        if result.returncode or failure:
            return 1
    marker=runtime/'preparation-complete'
    descriptor=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as output:output.write(args.source_sha+'\n')
    return 0


if __name__ == '__main__':
    try:raise SystemExit(main())
    except (RuntimeError,OSError,ValueError,subprocess.SubprocessError) as error:
        print(json.dumps({'passed':False,'stage':'dependency-preparation',
             'category':str(error) if isinstance(error,RuntimeError) else type(error).__name__}),file=sys.stderr)
        raise SystemExit(1)
