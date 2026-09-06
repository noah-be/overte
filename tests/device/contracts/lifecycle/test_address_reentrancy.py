"""Six actual AddressManager functions, real Qt signals/replies/tickets."""
import pathlib,os,shlex,subprocess,tempfile,unittest,resource
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
ROOT=pathlib.Path(__file__).resolve().parents[4]
def method(s,name):
 a=s.index(name);i=s.index('{',a)+1;depth=1
 while depth:
  depth+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[a:i]+'\n'
class AddressReentrancy(unittest.TestCase):
 def test_actual_reentrant_paths(self):
  source=(ROOT/'libraries/networking/src/AddressManager.cpp').read_text();names=['void AddressManager::handleAPIResponse(', 'void AddressManager::goToAddressFromObject(', 'void AddressManager::handleAPIError(', 'bool AddressManager::setHost(', 'bool AddressManager::setDomainInfo(', 'void AddressManager::addCurrentAddressToHistory('];extracted='\n'.join(method(source,n) for n in names)
  if os.environ.get('OVERTE_ADDRESS_IGNORE_GENERATION'):
   assert 'lookup.current()' in extracted;extracted=extracted.replace('lookup.current()','true')
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core','Qt6Network'],text=True))
  with tempfile.TemporaryDirectory(prefix='address-reentrancy-') as d:
   d=pathlib.Path(d);cpp=pathlib.Path(__file__).with_name('address-reentrancy-test.cpp');(d/'production.inc').write_text(extracted)
   subprocess.run(['/usr/lib64/qt6/libexec/moc',str(cpp),'-o',str(d/'address-reentrancy-test.moc')],check=True,timeout=10)
   binary=d/'test';subprocess.run(['c++','-std=c++17','-fPIC','-I',str(ROOT),'-I',str(d),str(cpp),'-o',str(binary),*flags],check=True,timeout=30)
   subprocess.run(['unshare','--user','--map-root-user','--net',str(binary)],check=True,timeout=5)
if __name__=='__main__':unittest.main()
