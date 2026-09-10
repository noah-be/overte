"""Complete original run/stop/wait bodies; real Qt dispatch and explicit VM seam."""
from pathlib import Path
import os
import resource
import shlex
import subprocess
import tempfile
import unittest
from test_login_dialog_domain_receiver import block

ROOT = Path(__file__).resolve().parents[4]
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class ScriptRunCompletion(unittest.TestCase):
    def test_actual_run_terminal_paths(self):
        relative = 'libraries/script-engine/src/ScriptManager.cpp'
        baseline = os.environ.get('OVERTE_SCRIPT_RUN_BASELINE')
        source = (subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline + ':' + relative], text=True)
                  if baseline else (ROOT / relative).read_text())
        mutation = os.environ.get('OVERTE_SCRIPT_RUN_MUTATION')
        if mutation == 'queued-quit':
            source = source.replace('workerThread, &QThread::quit, Qt::DirectConnection', 'workerThread, &QThread::quit')
        if mutation == 'running-only-reconnect':
            source = source.replace('if (_isThreaded && (workerThread = thread()))',
                'if (_isRunning && _isThreaded && (workerThread = thread()))')
        methods = '\n'.join(block(source, signature) for signature in (
            'void ScriptManager::run(', 'void ScriptManager::runInThread(', 'void ScriptManager::stop(',
            'bool ScriptManager::isStopped(', 'void ScriptManager::waitTillDoneRunning(',
            'void ScriptManager::disconnectNonEssentialSignals('))
        header = (ROOT / 'libraries/script-engine/src/ScriptManager.h').read_text()
        state = next(line for line in header.splitlines() if 'std::atomic<bool> _hasRunStarted' in line)
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        moc = Path(subprocess.check_output(['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip()) / 'moc'
        driver = Path(__file__).with_name('script-run-completion-test.cpp')
        with tempfile.TemporaryDirectory(prefix='overte-script-run-') as temporary:
            scratch = Path(temporary)
            (scratch / 'run.inc').write_text(methods)
            (scratch / 'run-state.inc').write_text(state)
            subprocess.run([str(moc), str(driver), '-o', str(scratch / 'run.moc')], check=True, timeout=15)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-pthread', '-I', str(ROOT), '-I', str(scratch),
                str(driver), str(ROOT / 'libraries/shared/src/shared/LocalFileAccessGate.cpp'),
                '-o', str(binary), *flags], check=True, timeout=40)
            modes = ('normal', 'prestop', 'globalstop', 'initstop', 'runningstop', 'reentrant', 'release', 'threaded', 'threadlaunch', 'threadlaunch-disconnect')
            if os.environ.get('OVERTE_SCRIPT_RUN_CASES'):
                selected = tuple(os.environ['OVERTE_SCRIPT_RUN_CASES'].split(','))
                self.assertTrue(set(selected) <= set(modes))
                modes = selected
            for mode in modes:
                with self.subTest(mode=mode):
                    run = subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary), mode],
                        capture_output=True, text=True, timeout=5)
                    self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
