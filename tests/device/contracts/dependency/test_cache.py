"""Production DependencyManager concurrency/lifetime test; host Qt, not native acceptance.

OVERTE_DEPENDENCY_TSAN=1 enables the host compiler's ThreadSanitizer.
OVERTE_DEPENDENCY_BASELINE=<commit> uses exact older production source.
The only replacement is process singleton storage (no QApplication/DLL host).
"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
baseline = os.environ.get('OVERTE_DEPENDENCY_BASELINE')
tsan = os.environ.get('OVERTE_DEPENDENCY_TSAN') == '1'
flags = shlex.split(subprocess.check_output(
    ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
with tempfile.TemporaryDirectory(prefix='overte-dependency-cache-') as scratch:
    path = Path(scratch)
    for name in ('DependencyManager.cpp', 'DependencyManager.h'):
        source = 'libraries/shared/src/' + name
        text = subprocess.check_output(['git', 'show', baseline + ':' + source],
                                       cwd=ROOT, text=True) if baseline else (ROOT / source).read_text()
        (path / name).write_text(text)
    (path / 'SharedUtil.h').write_text(
        'template<class T> T* globalInstance(const char*) { static T instance; return &instance; }\n')
    (path / 'Finally.h').write_text('')
    sanitizer = ['-fsanitize=thread'] if tsan else []
    subprocess.run(['c++', '-std=c++17', '-O1', '-g', '-fPIC', '-pthread', *sanitizer,
                    '-I' + str(path), str(path / 'DependencyManager.cpp'),
                    str(Path(__file__).with_name('cache.cpp')), '-o', str(path / 'test'), *flags],
                   check=True, timeout=40)
    env = dict(os.environ, TSAN_OPTIONS='halt_on_error=1')
    result = subprocess.run([str(path / 'test')], env=env, capture_output=True,
                            text=True, timeout=30)
    if baseline and tsan:
        assert result.returncode != 0 and 'WARNING: ThreadSanitizer: data race' in result.stderr, result.stderr
        print(result.stderr)
        print('EXPECTED BASELINE FAILURE: concurrent access to shared weak cache')
    else:
        assert result.returncode == 0, result.stderr
        print('PASS: concurrent first use, 40 cache expirations/replacements, weak ownership, inheritance, recursive registry reads')
