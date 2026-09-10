"""Complete original profile request/completion methods at the real Qt GET seam."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from test_login_dialog_domain_receiver import block

ROOT = Path(__file__).resolve().parents[4]


class ProfileContext(unittest.TestCase):
    def test_profile_is_bound_to_current_credential_and_request(self):
        baseline = os.environ.get('OVERTE_ACCOUNT_PROFILE_BASELINE')
        relative = 'libraries/networking/src/AccountManager.cpp'
        source = (subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline + ':' + relative],
                                         text=True) if baseline else (ROOT / relative).read_text())
        methods = block(source, 'static void observeAccountTokenDeadline(') + '\n'
        methods += '\n'.join(block(source, 'void AccountManager::' + name + '(')
                              for name in ('requestProfile', 'requestProfileFinished', 'requestProfileError'))
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Network'], text=True))
        moc = Path(subprocess.check_output(['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip()) / 'moc'
        driver = Path(__file__).with_name('account-profile-context-test.cpp')
        with tempfile.TemporaryDirectory(prefix='overte-profile-context-') as temporary:
            scratch = Path(temporary)
            (scratch / 'profile.inc').write_text(methods)
            subprocess.run([str(moc), str(driver), '-o', str(scratch / 'profile.moc')], check=True, timeout=15)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), '-I', str(scratch),
                            str(driver), '-o', str(binary), *flags], check=True, timeout=30)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)], check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
