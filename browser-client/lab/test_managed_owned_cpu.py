"""Fresh own Python groups only; no bwrap/native/namespace/browser/service execution."""
import argparse,ctypes,hashlib,importlib.util,json,os,signal,subprocess,sys,tempfile,time,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent

def birth(pid):
    try:
        raw=(Path('/proc')/str(pid)/'stat').read_bytes()
        fields=raw.rsplit(b') ',1)[1].split()
        return dict(pid=pid,birth=fields[19].decode(),parent=int(fields[1]),group=int(fields[2]),session=int(fields[3]),uid=(Path('/proc')/str(pid)).stat().st_uid,state=fields[0].decode())
    except(FileNotFoundError,ProcessLookupError):return None

def load(path):
    spec=importlib.util.spec_from_file_location('owned_cpu_launch',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def supervisor(source,root):
    m=load(Path(source));popen=m.subprocess.Popen
    def own_cpu_popen(command,**options):
        # Substitute only process execution. The exact actual supervise() chooses
        # whether the source-owned --new-session argument reaches this CPU stub.
        assert command[0]=='/usr/bin/bwrap'
        return popen([sys.executable,'-B',__file__,'--cpu-stub',str(root),'--',*command[1:]],**options)
    m.subprocess.Popen=own_cpu_popen
    command=['/usr/bin/bwrap','--die-with-parent','--new-session','--', 'CPU_ONLY_FIXED_PAYLOAD']
    raise SystemExit(m.supervise(command,()))

def stub(root,args):
    prefix=args[:args.index('--')]
    if '--new-session'in prefix:os.setsid()
    # Exercise the documented credential-transition boundary: PDEATHSIG may
    # be cleared. This CPU stub is not evidence of Bubblewrap's actual cause.
    library=ctypes.CDLL(None,use_errno=True)
    assert library.prctl(1,0,0,0,0)==0
    if (root/'ignore-term').exists():signal.signal(signal.SIGTERM,signal.SIG_IGN)
    (root/'payload.json').write_text(json.dumps(birth(os.getpid())))
    while True:time.sleep(.1)

class OwnedCPU(unittest.TestCase):
    def setUp(self):
        self.lib=ctypes.CDLL(None,use_errno=True);self.prior=ctypes.c_int()
        self.assertEqual(self.lib.prctl(37,ctypes.byref(self.prior),0,0,0),0)
        self.assertEqual(self.lib.prctl(36,1,0,0,0),0)
        self.root=Path(tempfile.mkdtemp(prefix='stop-only-own-CPU-'));os.chmod(self.root,0o700)
        self.known={};self.process=None
    def tearDown(self):
        # Birth-bound pidfds, never global /proc inventory or waitpid(-1).
        for pid,row in list(self.known.items()):
            fresh=birth(pid)
            if fresh is None:continue
            self.assertEqual(tuple(fresh[k]for k in('birth','uid','group','session')),tuple(row[k]for k in('birth','uid','group','session')))
            try:fd=os.pidfd_open(pid)
            except ProcessLookupError:continue
            try:
                if birth(pid) is not None:signal.pidfd_send_signal(fd,signal.SIGKILL)
            except ProcessLookupError:pass
            finally:os.close(fd)
        deadline=time.monotonic()+2.5
        while time.monotonic()<deadline:
            remaining=[]
            for pid,row in self.known.items():
                fresh=birth(pid)
                if fresh is None:continue
                self.assertEqual(fresh['birth'],row['birth'])
                if fresh['parent']==os.getpid():
                    try:os.waitpid(pid,os.WNOHANG)
                    except ChildProcessError:pass
                if birth(pid) is not None:remaining.append(pid)
            if not remaining:break
            time.sleep(.01)
        self.assertFalse([p for p in self.known if birth(p) is not None],'own CPU cleanup incomplete')
        if self.process is not None:self.process.wait(timeout=.5)
        self.assertEqual(self.lib.prctl(36,self.prior.value,0,0,0),0)
        __import__('shutil').rmtree(self.root)
    def ready(self,source):
        # The short-lived controller exits normally. No service ownership is
        # tied to that controller's lifetime; the reviewer is a local subreaper.
        completed=subprocess.run([sys.executable,'-B',__file__,'--controller',str(source),str(self.root)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2)
        self.assertEqual(completed.returncode,0)
        recorded=json.loads((self.root/'supervisor.json').read_text())
        row=birth(recorded['pid']);self.assertIsNotNone(row)
        self.assertEqual(row['birth'],recorded['birth']);self.known[row['pid']]=row
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            try:payload=json.loads((self.root/'payload.json').read_text());break
            except FileNotFoundError:time.sleep(.01)
        else:self.fail('owned CPU payload not ready')
        fresh=birth(payload['pid']);self.assertIsNotNone(fresh);self.assertEqual(fresh['birth'],payload['birth']);self.known[payload['pid']]=fresh
        self.assertNotEqual(fresh['state'],'Z');self.assertNotEqual(birth(row['pid'])['state'],'Z')
        return row,fresh
    def group_retirement(self,row):
        self.assertEqual(birth(row['pid'])['birth'],row['birth']);self.assertEqual(os.getpgid(row['pid']),row['pid'])
        os.killpg(row['pid'],signal.SIGTERM)
        deadline=time.monotonic()+2.5
        while time.monotonic()<deadline:
            pending=[]
            for pid,old in self.known.items():
                fresh=birth(pid)
                if fresh is None:continue
                self.assertEqual(fresh['birth'],old['birth'])
                if fresh['parent']==os.getpid():
                    try:os.waitpid(pid,os.WNOHANG)
                    except ChildProcessError:pass
                if birth(pid) is not None:pending.append(pid)
            if not pending:return True
            time.sleep(.01)
        return False
    def test_exact_old_session_split_with_cleared_pdeath_retains_cpu_payload(self):
        supervisor,payload=self.ready(HERE/'fixtures/native-launch-original-fda.py')
        self.assertNotEqual(payload['group'],supervisor['group'])
        self.assertFalse(self.group_retirement(supervisor))
        self.assertIsNotNone(birth(payload['pid']))
    def test_exact_corrected_supervise_same_group_all_cpu_payloads_retire(self):
        supervisor,payload=self.ready(HERE/'native_launch.py')
        self.assertEqual(payload['group'],supervisor['group'])
        self.assertTrue(self.group_retirement(supervisor))
        for pid in self.known:self.assertIsNone(birth(pid))
    def test_actual_corrected_stop_retires_own_escaped_cpu_descendant(self):
        from test_managed_stop import module
        m=module(HERE/'manage.py')
        (self.root/'ignore-term').touch(mode=0o600)
        supervisor,payload=self.ready(HERE/'fixtures/native-launch-original-fda.py')
        self.assertNotEqual(payload['group'],supervisor['group'])
        state=self.root/'registry.json';state.write_text(json.dumps({'owned':{'pid':supervisor['pid'],'startTicks':supervisor['birth']}}))
        m.update(STATE=state,load_state=lambda:json.loads(state.read_text()),alive=lambda pid:birth(pid)is not None,start_ticks=lambda pid:birth(pid)['birth'],REPO=HERE)
        started=time.monotonic();m['stop']()
        self.assertLess(time.monotonic()-started,3.1)
        self.assertEqual(json.loads(state.read_text()),{})
        for pid in self.known:self.assertIsNone(birth(pid))

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--controller':
        root=Path(sys.argv[3])
        process=subprocess.Popen([sys.executable,'-B',__file__,'--supervisor',sys.argv[2],str(root)],start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        (root/'supervisor.json').write_text(json.dumps(birth(process.pid)))
    elif len(sys.argv)>1 and sys.argv[1]=='--supervisor':supervisor(sys.argv[2],Path(sys.argv[3]))
    elif len(sys.argv)>1 and sys.argv[1]=='--cpu-stub':stub(Path(sys.argv[2]),sys.argv[4:])
    else:unittest.main(verbosity=2)
