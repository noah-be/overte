#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run all existing browser/native gates in the job's private namespace."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from run import safe_environment, empty_npm_environment

REQUIRED_STAGES = frozenset(('production-build','unit-isolation-contracts','actual-qt-input',
    'fbx-worker-chromium','fbx-worker-firefox','vite-embedded-config-mjs',
    'vite-embedded-world-config-mjs','embedded-world','browser-renderer',
    'test_host_tools-py','test_curate_core_journey-py','test_manage_state-py','normal-native-preflight',
    'start-real-domain-native-gateway','native-core-chromium','native-core-firefox',
    'source-immutability','owned-lab-cleanup','curate-native-core'))


def complete_pass(rows):
    return len(rows) == len(REQUIRED_STAGES) and REQUIRED_STAGES == {row['stage'] for row in rows} \
        and all(row['passed'] for row in rows)


def isolated_identity():
    if os.getuid() == 0:
        raise RuntimeError('gate-process-must-not-run-as-root')
    status = Path('/proc/self/status').read_text()
    for name in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'):
        line = next(row for row in status.splitlines() if row.startswith(name+':'))
        if int(line.split()[1],16) != 0:
            raise RuntimeError('gate-process-retained-namespace-capabilities')


def main():
    isolated_identity()
    config = json.loads(Path(sys.argv[1]).read_text())
    repo = Path(config['repo'])
    runtime = repo/'build/jenkins-browser-ci'
    root = repo/'build/browser-lab'
    lab = repo/'browser-client/lab'
    package = repo/'browser-client'
    runtime_tmp = Path('/tmp/overte-ci-runtime')
    runtime_tmp.mkdir(mode=0o700)
    audio = runtime_tmp/'pulse.sock'
    env = dict(safe_environment(),OVERTE_LAB_ROOT=str(root),OVERTE_LAB_DURATION_SECONDS='0',
        **empty_npm_environment(runtime),
        XDG_RUNTIME_DIR=str(runtime_tmp),XDG_CACHE_HOME=str(runtime/'cache'),
        XDG_CONFIG_HOME=str(runtime_tmp/'config'),XDG_DATA_HOME=str(runtime_tmp/'data'),
        PLAYWRIGHT_BROWSERS_PATH=str(runtime/'browsers'),PULSE_SERVER='unix:'+str(audio),
        PULSE_RUNTIME_PATH=str(runtime_tmp),PULSE_STATE_PATH=str(runtime_tmp/'pulse-state'),
        PULSE_COOKIE=str(runtime_tmp/'pulse-cookie'),DBUS_SESSION_BUS_ADDRESS='unix:path=/dev/null',
        LIBGL_ALWAYS_SOFTWARE='true',GALLIUM_DRIVER='llvmpipe')
    for name in ('LD_LIBRARY_PATH','PULSE_SOURCE','PULSE_SINK','DISPLAY'):
        env.pop(name,None)
    tools = json.loads((root/'config/host-tools.json').read_text())
    # Tests launch the network helper with a deliberately fixed supervisor PATH.
    # Carry the absolute helper already verified during lab preparation.
    env['OVERTE_GATEWAY_SLIRP'] = tools['slirp']
    env['PATH']=str(Path(tools['xvfb']).parent)+os.pathsep+env['PATH']
    policy = runtime_tmp/'null-audio.pa'
    policy.write_text(f'load-module module-native-protocol-unix socket={audio} auth-anonymous=1\n'
        'load-module module-null-sink sink_name=ci_input rate=48000 channels=1\n'
        'load-module module-null-sink sink_name=ci_output rate=48000 channels=2\n'
        'set-default-source ci_input.monitor\nset-default-sink ci_output\n')
    rows=[]
    cancelled=False
    def cancel(_signum,_frame):
        nonlocal cancelled
        cancelled=True
    signal.signal(signal.SIGTERM,cancel)
    signal.signal(signal.SIGINT,cancel)
    def publish():
        report={'sourceSHA':config['sourceSHA'],'sourceFiles':config['sourceFiles'],
            'passed':complete_pass(rows),
            'isolation':'nonroot, zero inherited capabilities, private network/IPC/PID/mount/tmp',
            'syntheticAudio':{'browserInput':'Per-engine curated core reports are authoritative; Chromium file input and Firefox generated input differ.',
                'nativeInput':'997Hz synthetic independent native input',
                'hardwareSpeech':'not tested'},
            'endurance':'omitted at user instruction','stages':rows}
        (runtime/'gate-summary.json').write_text(json.dumps(report,indent=2)+'\n')
    def stage(name,command,*,cwd=repo,extra=None,timeout=900,cleanup=False):
        started=time.monotonic()
        with (runtime/f'{name}-private.log').open('wb') as log:
            process=subprocess.Popen(command,cwd=cwd,env={**env,**(extra or {})},
                stdout=log,stderr=log,start_new_session=True)
            deadline=started+timeout
            failure=None
            try:
                while process.poll() is None:
                    if cancelled and not cleanup:failure='cancelled';break
                    if time.monotonic()>=deadline:failure='stage-deadline';break
                    if os.fstat(log.fileno()).st_size>64*1024*1024:failure='private-log-size-limit';break
                    time.sleep(.1)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        passed=failure is None and process.returncode==0
        rows.append({'stage':name,'passed':passed,'durationSeconds':round(time.monotonic()-started,3),
            'exitCode':process.returncode,'failureCategory':failure})
        publish()
        return passed
    xvfb=[sys.executable,str(Path(__file__).resolve().parent/'owned-xvfb.py'),
        '--lab-root',str(root),'--runtime',str(runtime_tmp),'--']
    pulse=None
    startup=False
    try:
        with (runtime/'pulse-private.log').open('wb') as pulse_log:
            pulse=subprocess.Popen([str(lab/'pulseaudio-local.sh'),'-n','--daemonize=no',
                '--use-pid-file=no','--exit-idle-time=-1','-F',str(policy)],
                env=env,stdout=pulse_log,stderr=pulse_log,start_new_session=True)
            deadline=time.monotonic()+10
            while not audio.exists():
                if pulse.poll() is not None or time.monotonic()>deadline or cancelled:
                    raise RuntimeError('private-null-audio-did-not-start')
                time.sleep(.05)
            commands=[
                ('production-build',['npm','run','build'],package),
                ('unit-isolation-contracts',['npm','test'],package),
                ('actual-qt-input',[sys.executable,str(package/'tools/build-native-input.py'),'--test','--test-web-editors',
                    '--output',str(root/'native-input'),'--qt-libraries',str(root/'appimage/squashfs-root/usr/lib')],repo),
            ]
            for name,command,cwd in commands:
                if not stage(name,command,cwd=cwd):return 1
            for engine in ('chromium','firefox'):
                if not stage('fbx-worker-'+engine,['node','tests/integration/model-fbx-pool-proof.mjs'],cwd=package,
                    extra={'OVERTE_FBX_POOL_BROWSER':engine,'OVERTE_FBX_POOL_EVIDENCE':str(runtime/f'fbx-{engine}.json')}):return 1
            for config_name in ('vite.embedded.config.mjs','vite.embedded-world.config.mjs'):
                if not stage(config_name.replace('.','-'),['npx','vite','build','--config',config_name,'--configLoader','native'],cwd=package):return 1
            if not stage('embedded-world',xvfb+['bash',str(lab/'run-embedded-journey.sh')],cwd=package):return 1
            if not stage('browser-renderer',xvfb+['npm','run','test:browser','--','--headed'],cwd=package):return 1
            for test_name in ('test_host_tools.py','test_curate_core_journey.py','test_manage_state.py'):
                if not stage(test_name.replace('.','-'),[sys.executable,str(lab/test_name)]):return 1
            if not stage('normal-native-preflight',[sys.executable,str(lab/'manage.py'),'preflight']):return 1
            startup=stage('start-real-domain-native-gateway',[sys.executable,str(lab/'manage.py'),'start','--gateway'],timeout=600)
            if startup:
                # Firefox still executes following a failed Chromium assertion.
                for engine in ('chromium','firefox'):
                    stage('native-core-'+engine,xvfb+['bash',str(lab/'run-core-journey.sh')],
                        extra={'OVERTE_LAB_BROWSER':engine},timeout=900)
                stage('source-immutability',['git','diff','--exit-code','HEAD','--'])
    finally:
        # Cleanup is not skipped by a preparation, graphics or journey failure.
        stage('owned-lab-cleanup',[sys.executable,str(lab/'manage.py'),'stop'],timeout=45,cleanup=True)
        stage('curate-native-core',[sys.executable,str(lab/'curate-core-journey.py'),
            '--input',str(root/'evidence'),'--output',str(runtime/'curated-core'),
            '--commit-sha',config['sourceSHA']],timeout=30,cleanup=True)
        if pulse is not None and pulse.poll() is None:
            os.killpg(pulse.pid,signal.SIGTERM)
            try:pulse.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(pulse.pid,signal.SIGKILL);pulse.wait(timeout=3)
    return 0 if startup and complete_pass(rows) else 1


if __name__ == '__main__':
    try:raise SystemExit(main())
    except (RuntimeError,OSError,ValueError,subprocess.SubprocessError) as error:
        print(json.dumps({'passed':False,'stage':'actual-ci-gates',
             'category':str(error) if isinstance(error,RuntimeError) else type(error).__name__}),file=sys.stderr)
        raise SystemExit(1)
