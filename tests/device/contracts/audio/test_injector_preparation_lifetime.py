"""Execute the production submission block against a held real Qt thread pool."""
from pathlib import Path
import os
import resource
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
relative = 'libraries/audio-client/src/AudioClient.cpp'
baseline = os.environ.get('OVERTE_AUDIO_PREP_BASELINE')
source = (subprocess.check_output(['git', 'show', baseline + ':' + relative], cwd=ROOT, text=True)
          if baseline else (ROOT / relative).read_text())
read = source.split('qint64 AudioClient::AudioOutputIODevice::readData(', 1)[1]
start = read.index('    // Keep one tracked preparation job.' if not baseline else '    // prepare injectors for the next callback')
submission = read[start:read.index('    int samplesPopped =', start)]
fixture = r'''
#include <QFuture>
#include <QThreadPool>
#include <QtConcurrent/QtConcurrentRun>
#include <QSemaphore>
#include <atomic>
#include <cassert>
struct AudioClient {
    QFuture<void> _localPrepInjectorFuture;
    std::atomic<int> calls { 0 };
    void prepareLocalAudioInjectors() { ++calls; }
};
struct AudioOutputIODevice {
    AudioClient* _audio;
    void submit() { /* SUBMISSION */ }
};
int main() {
    auto pool = QThreadPool::globalInstance();
    pool->setMaxThreadCount(1);
    QSemaphore entered, release;
    auto blocker = QtConcurrent::run(pool, [&] { entered.release(); release.acquire(); });
    assert(entered.tryAcquire(1, 2000));
    AudioClient audio;
    AudioOutputIODevice device { &audio };
    for (int i = 0; i < 1000; ++i) device.submit();
    assert(audio.calls == 0);
    release.release();
    audio._localPrepInjectorFuture.waitForFinished();
    assert(pool->waitForDone(2000));
    assert(audio.calls == 1); // no abandoned jobs remain behind the tracked future
    device.submit();
    audio._localPrepInjectorFuture.waitForFinished();
    assert(audio.calls == 2); // later callbacks can replenish again
}
'''
flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Concurrent'], text=True))
with tempfile.TemporaryDirectory(prefix='overte-audio-prep-') as scratch:
    path = Path(scratch)
    (path / 'test.cpp').write_text(fixture.replace('/* SUBMISSION */', submission))
    subprocess.run(['c++', '-std=c++17', '-fPIC', '-pthread', str(path / 'test.cpp'),
                    '-o', str(path / 'test'), *flags], check=True, timeout=40)
    result = subprocess.run([str(path / 'test')], capture_output=True, text=True, timeout=5)
    if baseline:
        assert result.returncode != 0 and 'audio.calls == 1' in result.stderr, result
        print('EXPECTED BASELINE FAILURE: callback burst leaves multiple preparation jobs')
    else:
        assert result.returncode == 0, result.stderr
        print('PASS production submission: bounded pending job, complete drain, later replenishment')
