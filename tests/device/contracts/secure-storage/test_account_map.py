"""Actual AccountManager map/file functions plus coordinator; protected OS is a seam."""
from pathlib import Path
import os,sys,subprocess,tempfile,shlex,unittest
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(Path(__file__).parents[1]/'lifecycle'))
from test_login_dialog_domain_receiver import block
class AccountMap(unittest.TestCase):
 def test_actual_map_migration(self):
  source=(ROOT/'libraries/networking/src/AccountManager.cpp').read_text()
  if os.environ.get('OVERTE_ACCOUNT_MAP_SKIP_VALIDATOR'):source=source.replace(',\n        validAccountMapBytes','')
  names=['overte::security::AccountStoreCoordinator& protectedAccountCoordinator(', 'overte::security::LegacyAccountInput legacyAccountInput(', 'QVariantMap accountMapFromFile(', 'bool writeAccountMapToFile(']
  if 'bool validAccountMapBytes(' in source:names.insert(1,'bool validAccountMapBytes(')
  methods='\n'.join(block(source,n) for n in names)
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
  with tempfile.TemporaryDirectory(prefix='actual-account-map-') as directory:
   d=Path(directory);(d/'methods.inc').write_text(methods)
   subprocess.run(['c++','-std=c++17','-fPIC','-I'+str(ROOT),'-I'+str(d),str(Path(__file__).with_name('account-map-test.cpp')),'-o',str(d/'test'),*flags],check=True,timeout=30)
   subprocess.run(['unshare','--user','--map-root-user','--net',str(d/'test')],check=True,timeout=10)
if __name__=='__main__':unittest.main()
