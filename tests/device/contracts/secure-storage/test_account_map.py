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
  if os.environ.get('OVERTE_ACCOUNT_MAP_SKIP_TYPES'):source=source.replace('if (it.value().userType() != qMetaTypeId<DataServerAccountInfo>()) { return false; }','if (false) { return false; }')
  names=['overte::security::AccountStoreCoordinator& protectedAccountCoordinator(', 'overte::security::LegacyAccountInput legacyAccountInput(', 'QVariantMap accountMapFromFile(', 'bool writeAccountMapToFile(']
  if 'bool validAccountMapBytes(' in source:names.insert(1,'bool validAccountMapBytes(')
  methods='\n'.join(block(source,n) for n in names)
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core','Qt6Network'],text=True))
  with tempfile.TemporaryDirectory(prefix='actual-account-map-') as directory:
   d=Path(directory);(d/'methods.inc').write_text(methods)
   account=(ROOT/'libraries/networking/src/DataServerAccountInfo.cpp').read_text()
   selectors=['DataServerAccountInfo::DataServerAccountInfo(const DataServerAccountInfo&', 'DataServerAccountInfo& DataServerAccountInfo::operator=', 'void DataServerAccountInfo::swap(', 'QDataStream& operator<<(', 'QDataStream& operator>>(']
   (d/'account-types.inc').write_text('\n'.join(block(account,n) for n in selectors))
   moc=Path(subprocess.check_output(['pkg-config','--variable=libexecdir','Qt6Core'],text=True).strip())/'moc'
   generated=[]
   for name in ['DataServerAccountInfo','OAuthAccessToken']:
    output=d/(name+'-moc.cpp');generated.append(str(output))
    subprocess.run([str(moc),str(ROOT/('libraries/networking/src/'+name+'.h')),'-o',str(output)],check=True,timeout=10)

   subprocess.run(['c++','-std=c++17','-fPIC','-I'+str(ROOT),'-I'+str(d),str(Path(__file__).with_name('account-map-test.cpp')),str(ROOT/'libraries/networking/src/OAuthAccessToken.cpp'),*generated,'-o',str(d/'test'),*flags],check=True,timeout=30)
   subprocess.run(['unshare','--user','--map-root-user','--net',str(d/'test')],check=True,timeout=10)
if __name__=='__main__':unittest.main()
