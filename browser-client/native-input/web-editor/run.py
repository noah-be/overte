#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Run current production text methods in genuine Qt WebEngine editors, privately."""
import argparse
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
    native = subprocess.Popen([str(executable), str(private/'qml'), str(fixture), str(HERE/'editor-fixture.html'),str(qt.parent)], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
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
            os.killpg(native.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            native.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(native.pid, signal.SIGKILL)
            native.wait(timeout=5)
        deadline=time.monotonic()+5
        group_stopped=False
        while time.monotonic()<deadline:
            try:
                os.killpg(native.pid,0)
            except ProcessLookupError:
                group_stopped=True
                break
            time.sleep(.05)
        if not group_stopped:
            try:
                os.killpg(native.pid,signal.SIGKILL)
            except ProcessLookupError:
                group_stopped=True
        report['ownedRendererGroupStopped']=group_stopped
        if not group_stopped:
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
