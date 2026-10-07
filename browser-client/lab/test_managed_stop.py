"""Pure mock-kernel tests; import only the actual candidate's stop class/functions."""
import ast,json,os,signal,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
HERE=Path(__file__).resolve().parent

def module(path):
    tree=ast.parse(path.read_text())
    body=[node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in ('_OwnedStop','stop')]
    scope={'Path':Path,'os':os,'signal':signal,'time':time,'json':json,'REPO':Path('/owned-reviewed-repo')}
    exec(compile(ast.Module(body=body,type_ignores=[]),str(path),'exec'),scope)
    return scope

class StopContracts(unittest.TestCase):
    def setUp(self):
        self.m=module(HERE/'manage.py');self.owner=self.m['_OwnedStop']
        self.dir=tempfile.TemporaryDirectory();self.addCleanup(self.dir.cleanup)
        self.state=Path(self.dir.name)/'state.json';self.document={'owned':{'pid':10001,'startTicks':'101'}}
        self.state.write_text(json.dumps(self.document));self.m.update(STATE=self.state,load_state=lambda:dict(self.document),alive=lambda pid:True,start_ticks=lambda pid:'101')
        self.rows={10001:self.row(10001,101,10,10001),10002:self.row(10002,102,10001,10002)}
        self.clock=0.;self.sent=[];self.nextfd=50;self.fds={};self.reused=False;self.retire=False
    def row(self,pid,birth,parent,group):
        return dict(pid=pid,birth=str(birth),parent=parent,group=group,session=group,uid=os.getuid())
    def identity(self,pid):return dict(self.rows[pid])if pid in self.rows else None
    def children(self,own,row):return [pid for pid,r in self.rows.items()if r['parent']==row['pid']]
    def openfd(self,pid):self.nextfd+=1;self.fds[self.nextfd]=pid;return self.nextfd
    def send(self,fd,number):
        pid=self.fds[fd];self.sent.append((pid,number))
        if pid==10001 and number==signal.SIGTERM and self.reused:self.rows[pid]=self.row(pid,202,10,10001)
        if self.retire and number==signal.SIGKILL:self.rows.pop(pid,None)
    def sleep(self,value):self.clock+=value
    def invoke(self):
        with patch.object(self.owner,'identity',side_effect=self.identity),patch.object(self.owner,'children',lambda own,row:self.children(own,row)),patch.object(self.owner,'group_absent',side_effect=lambda g:not any(r['group']==g for r in self.rows.values())),patch.object(os,'pidfd_open',side_effect=self.openfd),patch.object(os,'close'),patch.object(signal,'pidfd_send_signal',side_effect=self.send),patch.object(os,'getpgid',return_value=10001),patch.object(time,'monotonic',side_effect=lambda:self.clock),patch.object(time,'sleep',side_effect=self.sleep),patch.object(Path,'read_bytes',return_value=b'/owned-reviewed-repo'),patch.object(Path,'resolve',return_value=self.m['REPO']),patch('builtins.print'):
            self.m['stop']()
    def test_reused_after_term_never_receives_kill_registry_retained(self):
        self.reused=True
        with self.assertRaisesRegex(RuntimeError,'reused'):self.invoke()
        self.assertNotIn((10001,signal.SIGKILL),self.sent)
        self.assertEqual(json.loads(self.state.read_text()),self.document)
    def test_unconfirmed_retirement_retains_registry_original_budget(self):
        with self.assertRaisesRegex(RuntimeError,'unproven'):self.invoke()
        self.assertEqual(json.loads(self.state.read_text()),self.document)
        self.assertLessEqual(self.clock,3.)
    def test_known_descendant_escaped_original_group_retired_by_its_pidfd(self):
        self.retire=True;self.invoke()
        self.assertEqual(self.rows,{})
        self.assertEqual(json.loads(self.state.read_text()),{})
        self.assertIn((10002,signal.SIGKILL),self.sent)
        self.assertLessEqual(self.clock,3.)
    def test_unknown_original_group_survivor_retains_registry(self):
        own=self.owner(self.document['owned'])
        with patch.object(self.owner,'identity',return_value=None),patch.object(self.owner,'group_absent',return_value=False):self.assertFalse(own.closed())
    def test_uid_change_refuses_before_any_signal(self):
        self.rows[10002]['uid']=os.getuid()+1
        with self.assertRaisesRegex(RuntimeError,'ownership'):self.invoke()
        self.assertEqual(self.sent,[])
        self.assertEqual(json.loads(self.state.read_text()),self.document)
    def test_changed_group_during_escalation_refuses_no_numeric_signal(self):
        original=self.send
        def changed(fd,number):
            original(fd,number)
            if self.fds[fd]==10001 and number==signal.SIGTERM:self.rows[10002]['group']=10099
        self.send=changed
        with self.assertRaisesRegex(RuntimeError,'identity'):self.invoke()
        self.assertFalse(any(n==signal.SIGKILL for p,n in self.sent))
    def test_signal_permission_error_keeps_registry_and_closes_descriptors(self):
        self.send=lambda fd,n:(_ for _ in ()).throw(PermissionError('CPU-only'))
        with self.assertRaises(PermissionError):self.invoke()
        self.assertEqual(json.loads(self.state.read_text()),self.document)
    def test_descendant_bound_fails_closed(self):
        own=self.owner(self.document['owned'])
        own.rows={p:self.row(p,101+p,10001,p)for p in range(1,129)}
        with self.assertRaisesRegex(RuntimeError,'bound'):own.admit(self.row(20001,30000,10001,20001))
    def test_reverse_order_selected_retirement_preserves_other_rows(self):
        self.document={'keep':{'pid':9,'startTicks':'9'},'one':{'pid':8,'startTicks':'8'},'two':{'pid':7,'startTicks':'7'}}
        self.state.write_text(json.dumps(self.document));self.m['alive']=lambda pid:False;order=[]
        class Finished:
            def __init__(own,entry):own.entry=entry
            def closed(own):order.append(own.entry['pid']);return True
            def close(own):pass
        self.m['_OwnedStop']=Finished
        self.m['stop'](['one','two'])
        self.assertEqual(order,[7,8]);self.assertEqual(json.loads(self.state.read_text()),{'keep':self.document['keep']})
    def test_dead_managed_supervisor_never_discards_unobserved_split_payload(self):
        self.document['owned']['arguments']=['python3','fixed-owned-native-launch','--managed-record-fd','3']
        self.state.write_text(json.dumps(self.document));self.m['alive']=lambda pid:False
        with self.assertRaisesRegex(RuntimeError,'attribution'):
            self.m['stop']()
        self.assertEqual(json.loads(self.state.read_text()),self.document)
        self.assertEqual(self.sent,[])
    def test_initial_leader_loss_refuses_before_payload_attribution(self):
        own=self.owner(self.document['owned'])
        with patch.object(self.owner,'identity',return_value=None),self.assertRaisesRegex(RuntimeError,'vanished'):
            own.observe()

    def test_missing_state_is_noop(self):
        self.m['load_state']=lambda:{}
        with patch.object(os,'pidfd_open')as opened:self.m['stop']()
        opened.assert_not_called()

class SessionBoundary(unittest.TestCase):
    def source(self):
        import ctypes
        from unittest.mock import Mock
        tree=ast.parse((HERE/'native_launch.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='supervise')
        scope={'os':os,'signal':signal,'ctypes':ctypes,'subprocess':SimpleNamespace(DEVNULL=-3),'host_environment':lambda:{'PATH':'/usr/bin:/bin'}}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-supervise','exec'),scope)
        seen=[];process=Mock();process.wait.return_value=0
        scope['subprocess'].Popen=lambda command,**options:(seen.append((command,options))or process)
        return scope,seen
    def test_only_prefix_new_session_removed_payload_and_other_flags_exact(self):
        m,seen=self.source()
        original=['/usr/bin/bwrap','--unshare-user','--cap-drop','ALL','--die-with-parent','--new-session','--','fixed-owned-payload','--new-session']
        self.assertEqual(m['supervise'](original,(7,8)),0)
        self.assertEqual(seen[0][0],original[:5]+original[6:])
        self.assertEqual(seen[0][1]['pass_fds'],(7,8));self.assertEqual(original[5],'--new-session')
    def test_missing_duplicate_or_no_delimiter_refuses_before_process(self):
        for command in (['/usr/bin/bwrap','--','payload'],['/usr/bin/bwrap','--new-session','--new-session','--','payload'],['/usr/bin/bwrap','--new-session']):
            m,seen=self.source()
            with self.assertRaises(ValueError):m['supervise'](command,())
            self.assertEqual(seen,[])

if __name__=='__main__':unittest.main(verbosity=2)
