"""Fresh own Python parent/child and same-UID adopter controls; no namespace/native."""
import ctypes,importlib.util,json,os,signal,subprocess,sys,tempfile,time,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent

def load():
 spec=importlib.util.spec_from_file_location('cpu_actual_final_guard',HERE/'native_launch.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def identity(pid):
 try:
  directory=Path('/proc')/str(pid);fields=(directory/'stat').read_bytes().rsplit(b') ',1)[1].split()
  return {'pid':pid,'birth':fields[19].decode(),'parent':int(fields[1]),'group':int(fields[2]),'session':int(fields[3]),'uid':directory.stat().st_uid,'state':fields[0].decode()}
 except(FileNotFoundError,ProcessLookupError):return None

def owner(root,adoption):
 m=load();row=m._process_identity(os.getpid());expected={key:row[key]for key in('pid','startTicks','uid','gid')}
 fd=m.sealed_record(json.dumps(expected).encode())
 try:p=subprocess.Popen([sys.executable,'-B',__file__,'--guarded-child',str(root),str(fd),'adoption'if adoption else'normal'],pass_fds=(fd,),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 finally:os.close(fd)
 (root/'child-identity.json').write_text(json.dumps(identity(p.pid)))
 if adoption:return
 p.wait()

def child(root,fd,mode):
 m=load();expected=json.loads(os.pread(fd,65537,0));os.close(fd)
 if mode=='adoption':
  deadline=time.monotonic()+2
  while not(root/'go').exists()and time.monotonic()<deadline:time.sleep(.01)
  if not(root/'go').exists():raise SystemExit(3)
 try:m.bind_managed_parent(expected)
 except ValueError:
  (root/'refused.json').write_text(json.dumps({'refused':True,'adopterPidGreaterThanOne':os.getppid()>1}))
  return
 library=ctypes.CDLL(None,use_errno=True);actual=ctypes.c_int()
 assert library.prctl(2,ctypes.byref(actual),0,0,0)==0 and actual.value==signal.SIGKILL
 (root/'ready.json').write_text(json.dumps({'binding':True,'getReadback':True}))
 while True:time.sleep(.1)

class RealParent(unittest.TestCase):
 def setUp(self):
  self.lib=ctypes.CDLL(None,use_errno=True);self.prior=ctypes.c_int()
  self.assertEqual(self.lib.prctl(37,ctypes.byref(self.prior),0,0,0),0);self.assertEqual(self.lib.prctl(36,1,0,0,0),0)
  self.tmp=tempfile.TemporaryDirectory(prefix='actual-parent-only-CPU-');self.root=Path(self.tmp.name);self.root.chmod(0o700);self.known={};self.process=None
 def signal_known(self,pid,number):
  row=self.known[pid];fresh=identity(pid)
  if fresh is None:return
  self.assertEqual(tuple(fresh[k]for k in('birth','uid','group','session')),tuple(row[k]for k in('birth','uid','group','session')))
  try:fd=os.pidfd_open(pid)
  except ProcessLookupError:return
  try:
   again=identity(pid)
   if again is None:return
   self.assertEqual(again['birth'],row['birth']);signal.pidfd_send_signal(fd,number)
  except ProcessLookupError:pass
  finally:os.close(fd)
 def reap(self):
  for pid,row in self.known.items():
   fresh=identity(pid)
   if fresh is None:continue
   self.assertEqual(fresh['birth'],row['birth'])
   if fresh['parent']==os.getpid():
    fd=os.pidfd_open(pid)
    try:os.waitid(os.P_PIDFD,fd,os.WEXITED|os.WNOHANG)
    except ChildProcessError:pass
    finally:os.close(fd)
  return all(identity(pid)is None for pid in self.known)
 def absent(self):
  deadline=time.monotonic()+2.5
  while time.monotonic()<deadline:
   if self.reap():return True
   time.sleep(.01)
  return False
 def tearDown(self):
  for pid in self.known:self.signal_known(pid,signal.SIGKILL)
  self.assertTrue(self.absent(),'own parent CPU cleanup incomplete')
  if self.process is not None:self.process.wait(timeout=.5)
  self.assertEqual(self.lib.prctl(36,self.prior.value,0,0,0),0);self.tmp.cleanup()
 def start(self,adoption=False):
  self.process=subprocess.Popen([sys.executable,'-B',__file__,'--owner',str(self.root),'adoption'if adoption else'normal'],start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  row=identity(self.process.pid);self.assertIsNotNone(row);self.known[row['pid']]=row
  deadline=time.monotonic()+2
  while time.monotonic()<deadline:
   try:child=json.loads((self.root/'child-identity.json').read_text());break
   except FileNotFoundError:time.sleep(.01)
  else:self.fail('own child creation not observed')
  self.assertIsNotNone(child);self.known[child['pid']]=child;return row,child
 def waitfile(self,name):
  deadline=time.monotonic()+2
  while time.monotonic()<deadline:
   try:return json.loads((self.root/name).read_text())
   except FileNotFoundError:time.sleep(.01)
  self.fail('own fixed result not observed')
 def test_after_exec_real_set_get_binding_parent_death_retires_child(self):
  row,child=self.start();self.assertEqual(self.waitfile('ready.json'),{'binding':True,'getReadback':True})
  self.signal_known(row['pid'],signal.SIGTERM);self.assertTrue(self.absent())
 def test_same_uid_subreaper_adoption_before_capture_is_refused(self):
  row,child=self.start(adoption=True);self.process.wait(timeout=2)
  fresh=identity(child['pid']);self.assertIsNotNone(fresh);self.assertEqual(fresh['parent'],os.getpid())
  (self.root/'go').touch(mode=0o600)
  self.assertEqual(self.waitfile('refused.json'),{'refused':True,'adopterPidGreaterThanOne':True});self.assertFalse((self.root/'ready.json').exists());self.assertTrue(self.absent())

if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='--owner':owner(Path(sys.argv[2]),sys.argv[3]=='adoption')
 elif len(sys.argv)>1 and sys.argv[1]=='--guarded-child':child(Path(sys.argv[2]),int(sys.argv[3]),sys.argv[4])
 else:unittest.main(verbosity=2)
