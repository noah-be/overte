"""Complete CrashHandler class/methods with Qt and a capture-only backend."""
from pathlib import Path
import os,re,shlex,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class CrashAnnotations(unittest.TestCase):
    def test_actual_handler(self):
        base=ROOT/'libraries/networking/src/crash-handler'
        source=(base/'CrashHandler.cpp').read_text().replace('../../../../security/redaction/CrashAnnotations.h','CrashAnnotations.h')
        if os.environ.get('OVERTE_CRASH_ALLOW_PRIVATE_ANNOTATIONS'):
            source=source.replace('if (!overte::security::allowedCrashAnnotation(key, value)) { return; }','')
        with tempfile.TemporaryDirectory(prefix='crash-annotations-') as directory:
            d=Path(directory)
            (d/'CrashHandler.h').write_text((base/'CrashHandler.h').read_text().replace('#include <SettingHandle.h>',''))
            (d/'CrashHandlerBackend.h').write_bytes((base/'CrashHandlerBackend.h').read_bytes())
            (d/'CrashAnnotations.h').write_bytes((ROOT/'security/redaction/CrashAnnotations.h').read_bytes())
            (d/'production.cpp').write_text(source)
            (d/'test.cpp').write_text(Path(__file__).with_name('crash-annotations-test.cpp').read_text())
            subprocess.run(['/usr/lib64/qt6/libexec/moc',str(d/'CrashHandler.h'),'-o',str(d/'moc.cpp')],check=True,timeout=10)
            flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
            subprocess.run(['c++','-std=c++17','-fPIC','-pthread',str(d/'production.cpp'),str(d/'test.cpp'),str(d/'moc.cpp'),'-o',str(d/'test'),*flags],check=True,timeout=30)
            subprocess.run(['unshare','--user','--map-root-user','--net',str(d/'test')],check=True,timeout=5)
    def test_backend_metadata_and_diagnostics(self):
        base=ROOT/'libraries/networking/src/crash-handler'
        sources={}
        for name in ['Crashpad','Breakpad']:
            relative='libraries/networking/src/crash-handler/CrashHandlerBackend_'+name+'.cpp'
            baseline=os.environ.get('OVERTE_CRASH_BACKEND_BASELINE')
            sources[name]=subprocess.check_output(['git','-C',str(ROOT),'show',baseline+':'+relative],text=True) if baseline else (ROOT/relative).read_text()
        crashpad='annotations["sentry[release]"]'+sources['Crashpad'].split('annotations["sentry[release]"]',1)[1].split('    arguments.push_back(',1)[0]
        breakpad='annotations["version"]'+sources['Breakpad'].split('annotations["version"]',1)[1].split('    flushAnnotations();',1)[0]
        logs='\n'.join(re.findall(r'qC(?:Debug|Info|Warning|Critical)\(crash_handler\)\s*<<[^;]+;',sources['Crashpad']))
        fixture=Path(__file__).with_name('crash-backend-metadata-test.cpp').read_text().replace('// CRASHPAD_METADATA',crashpad).replace('// BREAKPAD_METADATA',breakpad).replace('// BACKEND_LOGS',logs)
        with tempfile.TemporaryDirectory(prefix='crash-backend-metadata-') as directory:
            d=Path(directory);cpp=d/'test.cpp';cpp.write_text(fixture)
            flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
            subprocess.run(['c++','-std=c++17','-fPIC',str(cpp),'-o',str(d/'test'),*flags],check=True,timeout=20)
            subprocess.run(['unshare','--user','--map-root-user','--net',str(d/'test')],check=True,timeout=5)
if __name__=='__main__':unittest.main()
