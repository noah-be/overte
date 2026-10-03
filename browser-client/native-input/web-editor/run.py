#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Run current production text methods in genuine Qt WebEngine editors, privately."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import selectors
import re
import signal
import time
import shutil
import struct
import subprocess
import tempfile
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(args, **options):
    return subprocess.run([str(arg) for arg in args], check=True, timeout=60, capture_output=True, text=True, **options)

def capture_bounded(process, timeout):
    chunks={};truncated=False;deadline=time.monotonic()+timeout
    with selectors.DefaultSelector() as selector:
        for stream in (process.stdout,process.stderr):
            os.set_blocking(stream.fileno(),False)
            selector.register(stream,selectors.EVENT_READ)
            chunks[stream]=bytearray()
        while selector.get_map():
            remaining=deadline-time.monotonic()
            if remaining<=0:raise subprocess.TimeoutExpired('owned-editor',timeout)
            for key,_ in selector.select(min(remaining,.1)):
                data=os.read(key.fileobj.fileno(),8192)
                if not data:selector.unregister(key.fileobj);continue
                available=65536-len(chunks[key.fileobj])
                if len(data)>available:truncated=True
                chunks[key.fileobj].extend(data[:available])
        process.wait(timeout=max(.001,deadline-time.monotonic()))
    return chunks[process.stdout].decode('utf8','replace'),chunks[process.stderr].decode('utf8','replace'),truncated

class OwnedRendererGroup:
    """Reap only birth-checked descendants of this runner's new session."""
    def __init__(self):
        self.libc=ctypes.CDLL(None,use_errno=True)
        previous=ctypes.c_int()
        if self.libc.prctl(37,ctypes.byref(previous),0,0,0)!=0:
            raise OSError(ctypes.get_errno(),'editor-subreaper-query-refused')
        self.previous=previous.value
        if self.libc.prctl(36,1,0,0,0)!=0:
            raise OSError(ctypes.get_errno(),'editor-subreaper-enable-refused')
        self.owner=os.getpid();self.leader=None;self.birth=None;self.seen={}

    @staticmethod
    def identity(pid):
        try:
            directory=Path('/proc')/str(pid)
            with (directory/'stat').open('rb') as stream:data=stream.read(4097)
            if len(data)>4096:raise RuntimeError('editor-proc-stat-bound')
            fields=data.rsplit(b') ',1)[1].split()
            if len(fields)<20:raise RuntimeError('editor-proc-stat-refused')
            return {'pid':pid,'state':fields[0].decode('ascii'),'parent':int(fields[1]),
                    'group':int(fields[2]),'session':int(fields[3]),'birth':int(fields[19]),
                    'uid':directory.stat().st_uid}
        except (FileNotFoundError,ProcessLookupError):return None

    def bind(self,process):
        self.leader=process.pid
        row=self.identity(process.pid)
        if not row or row['parent']!=self.owner or row['group']!=process.pid or row['session']!=process.pid or row['uid']!=os.getuid():
            raise RuntimeError('editor-owned-session-refused')
        self.birth=row['birth'];self.seen[process.pid]=row['birth']

    def validate(self,rows):
        if self.birth is None:raise RuntimeError('editor-unbound-group-refused')
        if len(rows)>128:raise RuntimeError('editor-owned-group-bound')
        if len(set(self.seen)|{row['pid'] for row in rows})>256:
            raise RuntimeError('editor-owned-birth-bound')
        pending={row['pid']:row for row in rows}
        admitted=set()
        while pending:
            progress=False
            for pid,row in list(pending.items()):
                if row['group']!=self.leader or row['session']!=self.leader or row['uid']!=os.getuid() or row['birth']<self.birth or pid in self.seen and self.seen[pid]!=row['birth']:
                    raise RuntimeError('editor-owned-group-identity-refused')
                if pid==self.leader:
                    if row['birth']!=self.birth or row['parent']!=self.owner:
                        raise RuntimeError('editor-owned-leader-refused')
                elif row['parent']!=self.owner and row['parent'] not in admitted:
                    continue
                admitted.add(pid);del pending[pid];progress=True
            if not progress:raise RuntimeError('editor-unknown-group-member')
        for row in rows:self.seen[row['pid']]=row['birth']
        return rows

    def members(self):
        def children(pid):
            try:
                with (Path('/proc')/str(pid)/'task'/str(pid)/'children').open('rb') as stream:
                    data=stream.read(8193)
            except (FileNotFoundError,ProcessLookupError):return []
            parts=data.split()
            if len(data)>8192 or len(parts)>128 or any(not p.isdigit() for p in parts):
                raise RuntimeError('editor-owned-children-bound')
            return [int(p) for p in parts]
        rows=[];seen=set();stack=[(pid,self.owner,0) for pid in children(self.owner)]
        while stack:
            pid,parent,depth=stack.pop()
            if depth>16 or len(seen)>=256 or pid in seen:
                raise RuntimeError('editor-owned-descendant-bound')
            seen.add(pid);row=self.identity(pid)
            if row is None:continue
            # Other direct children (e.g. our Xvfb) have unrelated sessions;
            # neither their descendants nor any foreign /proc entry is read.
            if depth==0 and row['session']!=self.leader:continue
            if row['parent'] not in (parent,self.owner) or row['session']!=self.leader or row['group']!=self.leader:
                raise RuntimeError('editor-owned-descendant-refused')
            rows.append(row)
            if row['uid']!=os.getuid() or row['birth']<self.birth or pid in self.seen and self.seen[pid]!=row['birth']:
                raise RuntimeError('editor-owned-descendant-identity-refused')
            stack.extend((child,pid,depth+1) for child in children(pid))
        return self.validate(rows)

    def signal(self,rows,number):
        for row in rows:
            try:descriptor=os.pidfd_open(row['pid'])
            except (FileNotFoundError,ProcessLookupError):continue
            try:
                current=self.identity(row['pid'])
                if current is None:continue
                if any(current[key]!=row[key] for key in ('pid','birth','uid','group','session')):
                    raise RuntimeError('editor-member-changed-before-signal')
                # An exited pidfd cannot be used to signal a reused numeric PID.
                signal.pidfd_send_signal(descriptor,number)
            except ProcessLookupError:pass
            finally:os.close(descriptor)

    def reap(self,rows):
        for row in rows:
            if row['pid']==self.leader or row['parent']!=self.owner:continue
            current=self.identity(row['pid'])
            if current is None:continue
            if any(current[key]!=row[key] for key in ('pid','birth','uid','group','session','parent')):
                raise RuntimeError('editor-member-changed-before-reap')
            try:os.waitpid(row['pid'],os.WNOHANG)
            except ChildProcessError:raise RuntimeError('editor-reap-ownership-refused')

    def restore(self):
        if self.libc.prctl(36,self.previous,0,0,0)!=0:
            raise OSError(ctypes.get_errno(),'editor-subreaper-restore-refused')

    def stop(self,process):
        try:return self.stop_owned(process)
        finally:self.restore()

    def stop_owned(self,process):
        if self.birth is None:raise RuntimeError('editor-unbound-group-refused')
        self.signal(self.members(),signal.SIGTERM)
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.signal(self.members(),signal.SIGKILL);process.wait(timeout=5)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            rows=self.members();self.reap(rows)
            rows=self.members()
            if not rows:
                try:os.killpg(self.leader,0)
                except ProcessLookupError:
                    return True
                raise RuntimeError('editor-unobserved-group-refused')
            self.signal(rows,signal.SIGKILL)
            time.sleep(.05)
        return False

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input-build', type=Path, required=True)
parser.add_argument('--qt-libraries', type=Path, required=True)
parser.add_argument('--qt-test-libraries', type=Path)
parser.add_argument('--xvfb', type=Path, required=True)
parser.add_argument('--report', type=Path, required=True)
options = parser.parse_args()
root = HERE.parents[1]
private = options.input_build.resolve(strict=True)
qt = options.qt_libraries.resolve(strict=True)
xvfb = options.xvfb.resolve(strict=True)
report_path = options.report.absolute()
report_path.parent.mkdir(parents=True, exist_ok=True)
assert not report_path.exists(), 'Do not overwrite an earlier proof'
source = HERE.parent / 'native-input.cpp'
CPP_SHA = sha(source)
artifacts = json.loads((private / 'artifacts.json').read_text())
assert artifacts['sourceSha256'] == CPP_SHA and artifacts['qtSDKVersion']=='5.15.3' and artifacts['qtRuntimeVersion']=='5.15.3', 'Current source and pinned Qt build are required'
plugin = private / 'qml/BrowserNativeInput/libbrowsernativeinput.so'
assert plugin.is_file() and not plugin.is_symlink(), 'Reviewed native input plugin is not built'
candidate_qml = root / 'gateway/tablet-capture.qml'
sdk = private / 'sdk'
assert xvfb.is_file() and os.access(xvfb,os.X_OK) and sdk.is_dir() and qt.is_dir(), 'Reviewed SDK/runtime/display resources missing'
runtime=json.loads((HERE/'runtime-input-artifacts.json').read_text())
assert set(runtime['files'])=={'libexec/QtWebEngineProcess','resources/qtwebengine_resources.pak','resources/qtwebengine_resources_100p.pak','resources/qtwebengine_resources_200p.pak','resources/qtwebengine_devtools_resources.pak','translations/qtwebengine_locales/en-US.pak','qml/QtWebEngine/qmldir','qml/QtWebEngine/libqtwebengineplugin.so','bin/qt.conf'}, 'Mandatory runtime path whitelist changed'
for name,expected in runtime['files'].items():
    resource=qt.parent/name
    assert resource.is_file() and not resource.is_symlink() and resource.stat().st_size==expected['bytes'] and resource.stat().st_size<=32*1024*1024 and sha(resource)==expected['sha256'], 'Mandatory reviewed runtime input changed'
assert os.access(qt.parent/'libexec/QtWebEngineProcess',os.X_OK), 'Reviewed WebEngine helper is not executable'
report = {'startedAt': datetime.now(timezone.utc).isoformat(), 'sourceSHA256': CPP_SHA,
          'candidateQmlSHA256': sha(candidate_qml), 'pluginLibrarySHA256': sha(plugin),
          'pluginArtifactsSHA256': sha(private / 'artifacts.json'),
          'fixtureSHA256': sha(HERE / 'editor-fixture.cpp'), 'templateSHA256': sha(HERE / 'editor-fixture.template.qml'), 'htmlSHA256': sha(HERE / 'editor-fixture.html'), 'qtSDKVersion': '5.15.3',
          'qtRuntimeVersion': artifacts['qtRuntimeVersion'], 'runtimeInputArtifactsSHA256':sha(HERE/'runtime-input-artifacts.json'), 'mandatoryRuntimeHashes':{name:expected['sha256'] for name,expected in runtime['files'].items()}, 'completed': False,
          'scope': 'Source-root genuine Qt WebEngine editor fixture; fourteen authored oracles with their original five-second deadlines. This does not establish complete Tablet or same-page DOM identity safety.',
          'passwordCancellationVerified':False,'passwordScope':'Ordinary editors use the unchanged guarded native IME commit. Password text uses one dedicated guarded native IME commit before any key event; undo/redo and maxlength remain original acceptance requirements. Cancellation suppresses future dispatch only and cannot retract delivered input; same Quick delegate is not a distinct password DOM identity.'}
process = None
native = None
renderer_group = None
stderr = ''
temporary = None
try:
    temporary = tempfile.TemporaryDirectory(prefix='own-ime-guard-')
    directory = Path(temporary.name)
    environment = {'PATH': os.defpath, 'HOME': os.environ['HOME'], 'XDG_CONFIG_HOME': str(directory / 'config'),
                   'XDG_DATA_HOME': str(directory / 'data'), 'XDG_CACHE_HOME': str(directory / 'cache'),
                   'XDG_RUNTIME_DIR': str(directory), 'LD_LIBRARY_PATH': str(qt),
                   'QT_PLUGIN_PATH': str(qt.parent / 'plugins'), 'QML2_IMPORT_PATH': str(qt.parent / 'qml'),
                   'QT_QPA_PLATFORM': 'xcb', 'LANG':'en_US.UTF-8', 'QTWEBENGINEPROCESS_PATH': str(qt.parent / 'libexec/QtWebEngineProcess')}
    qt_test=(options.qt_test_libraries or qt.parents[3]/'qt-tablet/usr/lib/x86_64-linux-gnu').resolve(strict=True)
    environment['LD_LIBRARY_PATH']=str(qt)+':'+str(qt_test)
    environment['QML2_IMPORT_PATH']=str(qt.parent/'qml')+':'+str(qt_test/'qt5/qml')
    fixture=directory/'editor-fixture.qml'
    run(['node', HERE/'prepare.mjs',fixture])
    report['qmlSHA256']=sha(fixture)
    include = sdk / 'usr/include/x86_64-linux-gnu/qt5'
    flags = ['-std=c++17', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror', '-I', include]
    for module in ['QtCore', 'QtGui', 'QtQml', 'QtQuick']:
        flags += ['-I', include / module]
    executable = directory / 'guard-test'
    # The pinned Qt5 build uses QLibraryInfo, not the later resources/locales
    # environment overrides. Give this owned executable an exact relocation file.
    qtconf='[Paths]\nPrefix = '+str(qt.parent)+'\nData = .\nTranslations = translations\nLibraryExecutables = libexec\nLibraries = lib\nPlugins = plugins\nImports = qml\nQml2Imports = qml\n'
    (directory/'qt.conf').write_text(qtconf)
    report['ownedQtConfigurationSHA256']=sha(directory/'qt.conf')
    run(['g++', *flags, '-I', directory, '-I', HERE, HERE / 'editor-fixture.cpp', '-o', executable,
         *[qt / f'libQt5{module}.so.5' for module in ['WebEngine', 'Quick', 'Qml', 'Gui', 'Core']]], env=environment)
    report['compileWerror'] = True
    field = lambda value: struct.pack('>H', len(value)) + value
    authority = directory / 'Xauthority'
    authority.write_bytes(struct.pack('>H', 65535) + field(b'') + field(b'') + field(b'MIT-MAGIC-COOKIE-1') + field(os.urandom(16)))
    authority.chmod(0o600)
    process = subprocess.Popen([str(xvfb), '-displayfd', '1', '-auth', str(authority), '-nolisten', 'tcp',
                                '-screen', '0', '640x480x24'], env={'PATH': os.defpath}, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True)
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(10):
            raise RuntimeError('owned-display-deadline')
    number = process.stdout.readline().strip()
    if not number.isdecimal():
        raise RuntimeError('owned-display-refused')
    environment.update(DISPLAY=':' + number, XAUTHORITY=str(authority))
    renderer_group = OwnedRendererGroup()
    native = subprocess.Popen([str(executable), str(private/'qml'), str(fixture), str(HERE/'editor-fixture.html'),str(qt.parent)], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    renderer_group.bind(native)
    stdout,stderr,output_truncated=capture_bounded(native,65)
    report['nativeOutputTruncated']=output_truncated
    assert not output_truncated, 'Bounded editor output exceeded'
    report['nativeExitCode'] = native.returncode
    lines=[line for line in stdout.splitlines() if line.startswith('{')]
    outcome=json.loads(lines[-1]) if lines else {}
    allowed=['unicode-text','native-number','textarea','literal-contenteditable','password-unicode','password-native-undo','password-native-redo','password-native-maxlength','readonly','disabled','immediate-cancel','navigation-cancel','password-immediate-cancel','password-navigation-cancel']
    cases=outcome.get('cases',[])
    stages={'case-start','geometry-read','geometry-ready','disabled-background-press','disabled-background-release','pointer-press','pointer-release','undo-redo','select-all','start-web-text','await-text-completion','await-input-state','verify-value','value-deadline','commit-deadline'}
    errors={'none','focused-field-refused','commit-start-refused','commit-deadline','unknown-fixed-error'}
    lengths={'beforeLength','beforeSelectionLength','afterLength','afterSelectionLength'}
    target_reasons={'pending-missing','pending-cancelled','web-missing','focus-missing','input-missing','surface-changed','revision-changed','navigation-changed','url-changed','focused-item-changed','ancestry-mismatch','current'}
    dom_reasons={'unobserved','result-missing','document-url','active-element-missing','readonly','disabled','noneditable','invalid-route','accepted'}
    native_stages={'password-initial','password-query','password-commit','password-returned','input-enabled-query', 'input-query', 'delivery', 'not-called', 'post-query-target', 'delivery-returned', 'initial-target', 'object-destroyed'}
    native_reasons={'password-commit-refused','password-invalid-text','password-hints-invalid','password-hints-missing','password-flag-expected','password-delegate-class','password-root-class','root-window', 'root-ancestry', 'owner-window', 'window-thread', 'input-enabled-invalid', 'object-destroyed', 'event-not-accepted', 'input-enabled-false', 'entered', 'text-control-character', 'root-thread', 'item-focus', 'delivery-guard', 'item-disabled', 'native-accepted', 'item-window', 'owner-thread', 'window-missing', 'helper-thread', 'owner-missing', 'send-event-false', 'root-hidden', 'input-method-flag', 'root-missing', 'owner-changed', 'item-hidden', 'not-called', 'item-thread', 'item-missing', 'root-disabled', 'current', 'window-focus'}
    keys={'kind','passed','stage','errorCategory','nativeCommitObserved','nativeCommitAccepted','targetChecks','domRefusal','nativeGuardStage','nativeGuardReason'}|lengths
    assert len(cases)<=len(allowed) and all(isinstance(row,dict) and set(row)==keys and row['kind'] in allowed and type(row['passed']) is bool and row['stage'] in stages and row['errorCategory'] in errors and row['domRefusal'] in dom_reasons and row['nativeGuardStage'] in native_stages and row['nativeGuardReason'] in native_reasons and isinstance(row['targetChecks'],list) and len(row['targetChecks'])<=16 and all(reason in target_reasons for reason in row['targetChecks']) and type(row['nativeCommitObserved']) is bool and type(row['nativeCommitAccepted']) is bool and all(type(row[key]) is int and -1<=row[key]<=65536 for key in lengths) for row in cases), 'Native output must remain fixed editor scalar metadata'
    report['qtLibraryPathsMatched']=outcome.get('qtLibraryPathsMatched') is True
    report['cases']=[dict(row) for row in cases]
    report['completed'] = report['qtLibraryPathsMatched'] and native.returncode==0 and outcome.get('completed') is True and outcome.get('passed') is True and [row['kind'] for row in cases]==allowed and all(row['passed'] for row in cases)
    report['passwordCancellationVerified']=report['completed'] and all(any(row['kind']==name and row['passed'] for row in cases) for name in ('password-immediate-cancel','password-navigation-cancel'))
    if not report['completed']:
        report['failureCategory'] = 'actual-qt-guard-or-runtime-refused'
except (OSError, AssertionError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
    if isinstance(error,subprocess.CalledProcessError):
        stderr=error.stderr or ''
    elif isinstance(error,subprocess.TimeoutExpired):
        stderr=error.stderr or ''
    report['failureCategory'] = 'resource-or-build-refused' if isinstance(error, (OSError, AssertionError, subprocess.CalledProcessError)) else 'owned-proof-deadline-or-refusal'
finally:
    if native:
        # This process group belongs to the newly owned session, including its
        # renderer descendants. Never leave them after a timeout or profile exit.
        try:
            group_stopped=renderer_group.stop(native)
        except (OSError,RuntimeError):
            group_stopped=False
        report['ownedRendererGroupStopped']=group_stopped
        if not group_stopped:
            report['completed']=False
            report['failureCategory']='owned-renderer-cleanup-incomplete'
    elif renderer_group:
        try:renderer_group.restore()
        except OSError:
            report['completed']=False
            report['failureCategory']='owned-renderer-cleanup-incomplete'
    if process:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        report['ownedDisplayStopped'] = process.poll() is not None
    if temporary:
        temporary.cleanup()
    if not report['completed'] and stderr:
        text=stderr.decode('utf8','replace') if isinstance(stderr,bytes) else stderr
        for value,marker in [(str(root),'<root-client>'),(str(private),'<private-runtime>'),(os.environ.get('HOME',''),'<user-home>'),(str(HERE),'<proposal>')]:
            if value:text=text.replace(value,marker)
        if temporary:text=text.replace(temporary.name,'<owned-profile>')
        text=re.sub(r'(?:https?|file)://[^\s\"<>]+','<url>',text)
        data=text.encode('utf8')[:65536]
        diagnostic=report_path.parent/('failure-'+str(time.time_ns())+'-stderr.private.txt')
        descriptor=os.open(diagnostic,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(descriptor,'wb') as stream:stream.write(data)
        report['failureDiagnostics']={'file':diagnostic.name,'bytes':len(data),'sha256':sha(diagnostic),'truncated':len(text.encode('utf8'))>len(data)}
    try:
        coherent=(sha(plugin)==report['pluginLibrarySHA256'] and sha(candidate_qml)==report['candidateQmlSHA256'] and sha(source)==CPP_SHA)
    except OSError:
        coherent=False
    report['sourceCoherent']=coherent
    if not coherent:
        report['completed']=False
        report['failureCategory']='source-or-library-changed'
    report['finishedAt'] = datetime.now(timezone.utc).isoformat()
    descriptor=os.open(report_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'w') as stream:stream.write(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
raise SystemExit(0 if report['completed'] else 1)
