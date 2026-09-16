"""Three complete actual engine string factories on real V8/Qt."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class V8StringFactory(unittest.TestCase):
    def test_original_factory_encoding_lengths_and_null(self):
        prefix = pathlib.Path(os.environ['V8_TEST_ROOT']).resolve(strict=True)
        path = 'libraries/script-engine/src/v8/ScriptEngineV8.cpp'
        baseline = os.environ.get('V8_STRING_FACTORY_BASELINE')
        source = subprocess.check_output(['git','show',baseline+':'+path],cwd=ROOT,text=True) if baseline else (ROOT / path).read_text()
        methods = []
        for kind in ('QString&','QLatin1String&','char*'):
            start = source.index('ScriptValue ScriptEngineV8::newValue(const '+kind+' value) {')
            methods.append(source[start:].split('\n}',1)[0]+'\n}\n')
        flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
        with tempfile.TemporaryDirectory(prefix='sh005-string-factory-') as temporary:
            directory = pathlib.Path(temporary)
            (directory / 'string-factory.inc').write_text('\n'.join(methods))
            binary = directory / 'test'
            library = prefix / 'usr/lib64'
            subprocess.run(['c++','-std=c++17','-fPIC','-pthread','-DQT_NO_DEBUG','-I',str(directory),
                            '-isystem',str(prefix / 'usr/include/node'),
                            str(pathlib.Path(__file__).with_name('v8-string-factory-test.cpp')),
                            '-L',str(library),'-Wl,-rpath,'+str(library),'-lnode','-o',str(binary),*flags],check=True,timeout=40)
            result = subprocess.run(['unshare','--user','--map-root-user','--net',str(binary)],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__': unittest.main()
