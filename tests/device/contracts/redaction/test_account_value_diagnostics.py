"""Complete actual account-value class, Qt logging and host RSA; synthetic keys only."""
from pathlib import Path
import os,subprocess,tempfile,shlex,unittest
ROOT=Path(__file__).resolve().parents[4]
class AccountValue(unittest.TestCase):
 def test_actual_account_value(self):
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core','Qt6Network','openssl'],text=True))
  moc=Path(subprocess.check_output(['pkg-config','--variable=libexecdir','Qt6Core'],text=True).strip())/'moc'
  with tempfile.TemporaryDirectory(prefix='account-value-') as directory:
   d=Path(directory);generated=[]
   for name in ['DataServerAccountInfo','OAuthAccessToken']:
    p=d/(name+'-moc.cpp');generated.append(str(p));subprocess.run([str(moc),str(ROOT/('libraries/networking/src/'+name+'.h')),'-o',str(p)],check=True,timeout=10)
   source=(ROOT/'libraries/networking/src/DataServerAccountInfo.cpp').read_text()
   if os.environ.get('OVERTE_ACCOUNT_VALUE_OLD_LOGS'):
    source=source.replace('"Account username changed."','"Username changed to" << username').replace('"Account username signature created."','"Returning username" << _username << "signed with connection UUID" << connectionToken.toString()')
   if os.environ.get('OVERTE_ACCOUNT_VALUE_OLD_RSA'):
    source=source.replace('encryptReturn == 1','encryptReturn != -1').replace('signature.resize(static_cast<int>(signatureBytes));','')
   # Resolve the actual local header; no replacement account methods/fields.
   source=source.replace('#include "DataServerAccountInfo.h"','#include "libraries/networking/src/DataServerAccountInfo.h"')
   (d/'actual-account.inc').write_text(source)
   subprocess.run(['c++','-std=c++17','-fPIC','-Wno-deprecated-declarations','-I'+str(ROOT),'-I'+str(ROOT/'libraries/networking/src'),'-I'+str(ROOT/'libraries/shared/src'),'-I'+str(d),str(Path(__file__).with_name('account-value-test.cpp')),str(ROOT/'libraries/networking/src/OAuthAccessToken.cpp'),*generated,'-o',str(d/'test'),*flags],check=True,timeout=30)
   subprocess.run(['unshare','--user','--map-root-user','--net',str(d/'test')],check=True,timeout=10)
if __name__=='__main__':unittest.main()
