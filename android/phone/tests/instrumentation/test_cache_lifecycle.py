"""Exercise actual cache lifecycle code using temporary host files and Qt."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]

DRIVER = r'''
#include <cassert>
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QTemporaryDir>
#include <QStringList>
#include "KTXCache.h"
bool fakeDiagnostics = true;
namespace Setting { int version = 2; }
QStringList records;
void capture(QtMsgType, const QMessageLogContext&, const QString& message) {
    if (message.startsWith("OVT_PHONE_LOADING")) { records.append(message); }
}
bool has(const QString& text) {
    for (const auto& line : records) { if (line.contains(text)) { return true; } }
    return false;
}
void fixture(const QString& dir, const QString& name) {
    assert(QDir().mkpath(dir));
    QFile file(dir + "/" + name + ".ktx");
    assert(file.open(QIODevice::WriteOnly));
    assert(file.write(QByteArray(32, 'x')) == 32);
}
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    fakeDiagnostics = argc == 1;
    qInstallMessageHandler(capture);
    QTemporaryDir scratch;
    assert(scratch.isValid());
    const auto first = scratch.path() + "/ktx_cache_gles";
    fixture(first, "private_fixture_a");
    fixture(first, "private_fixture_b");
    {
        auto cache = std::make_shared<cache::FileCache>(first.toStdString(), "ktx");
        cache->setMinFreeSize(0);
        cache->setMaxSize(48);
        cache->initialize();
        assert(cache->getNumTotalFiles() == 1);
        assert(cache->getSizeTotalFiles() == 32);
        if (fakeDiagnostics) {
            assert(has("phase=file_cache_scan cache=2 exists=1 listed=2"));
            assert(has("scanned_files=2 scanned_bytes=64 indexed_files=1 indexed_bytes=32"));
            assert(has("size_excess_bytes=16 target_bytes=16"));
            assert(has("ejected_files=1 ejected_bytes=32 remaining_target_bytes=0"));
        }
    }
    // Normal destruction persists the surviving entry instead of wiping it.
    assert(QDir(first).entryList({"*.ktx"}, QDir::Files).size() == 1);
    {
        auto cache = std::make_shared<cache::FileCache>(first.toStdString(), "ktx");
        cache->setMinFreeSize(0);
        cache->initialize();
        assert(cache->getNumTotalFiles() == 1);
        cache->setMinFreeSize(size_t(1) << 62);
        assert(cache->getNumTotalFiles() == 0);
        if (fakeDiagnostics) {
            assert(has("size_excess_bytes=0 target_bytes="));
            assert(has("phase=file_cache_persist"));
        }
    }
    const auto second = scratch.path() + "/ktx_cache_gles_loading_2";
    fixture(second, "private_fixture_c");
    Setting::version = 0;
    {
        auto cache = std::make_shared<KTXCache>(second.toStdString(), "ktx");
        cache->setMinFreeSize(0);
        cache->initialize();
        assert(Setting::version == 2);
        assert(cache->getNumTotalFiles() == 0);
        if (fakeDiagnostics) {
            assert(has("phase=ktx_cache_version edge=0 stored=0 expected=2 reset=1 indexed_files=1 indexed_bytes=32"));
            assert(has("phase=ktx_cache_version edge=1 stored=2 expected=2 reset=1 indexed_files=0 indexed_bytes=0"));
            assert(has("phase=file_cache_wipe cache=2 edge=0"));
            assert(has("phase=file_cache_wipe cache=2 edge=1 indexed_files=0"));
        }
    }
    fixture(second, "private_fixture_d");
    {
        auto cache = std::make_shared<KTXCache>(second.toStdString(), "ktx");
        cache->setMinFreeSize(0);
        cache->initialize();
        assert(cache->getNumTotalFiles() == 1); // matching version preserves it
        if (fakeDiagnostics) { assert(has("stored=2 expected=2 reset=0")); }
    }
    const auto third = scratch.path() + "/ktx_cache";
    {
        auto cache = std::make_shared<cache::FileCache>(third.toStdString(), "ktx");
        cache->initialize();
        if (fakeDiagnostics) { assert(has("phase=file_cache_scan cache=1 exists=0 listed=0 created=1")); }
    }
    if (!fakeDiagnostics) { assert(records.isEmpty()); }
    for (const auto& line : records) {
        assert(!line.contains(scratch.path()));
        assert(!line.contains("private_fixture"));
    }
}
'''


class CacheLifecycleTest(unittest.TestCase):
    def test_production_cache_scan_eviction_version_wipe_and_opt_in(self):
        shared = ROOT / 'libraries/shared/src'
        material = ROOT / 'libraries/material-networking/src/material-networking'
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        moc = subprocess.check_output(['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip() + '/moc'
        with tempfile.TemporaryDirectory(prefix='phone-cache-lifecycle-') as scratch:
            path = Path(scratch)
            (path / 'sys').mkdir()
            (path / 'sys/system_properties.h').write_text('''#pragma once
#define PROP_VALUE_MAX 92
extern bool fakeDiagnostics;
inline int __system_property_get(const char*, char* value) {
    value[0] = fakeDiagnostics ? '1' : '0'; value[1] = 0; return 1;
}
''')
            (path / 'SettingHandle.h').write_text('''#pragma once
namespace Setting {
extern int version;
template<class T> class Handle {
public: Handle(const char*, T) {} T get() const { return T(version); }
void set(T value) { version = value; }
};
}
''')
            cache_source = (shared / 'shared/FileCache.cpp').read_text()
            cache_source = cache_source.replace('#include "../PathUtils.h"',
                'class PathUtils { public: static QString getAppLocalDataFilePath(const QString& path) { return path; } };')
            for name in ['NumericalConstants.h', 'PhoneLoadingDiagnostics.h']:
                cache_source = cache_source.replace('#include "../' + name + '"', '#include "' + str(shared / name) + '"')
            (path / 'FileCache.cpp').write_text(cache_source)
            ktx_source = (material / 'KTXCache.cpp').read_text().replace('#include <ktx/KTX.h>', '')
            (path / 'KTXCache.cpp').write_text(ktx_source)
            (path / 'driver.cpp').write_text(DRIVER)
            headers = [shared / 'shared/FileCache.h', material / 'KTXCache.h']
            for index, header in enumerate(headers):
                subprocess.run([moc, '-I' + str(shared), str(header), '-o', str(path / f'moc{index}.cpp')], check=True, timeout=20)
            sources = ['driver.cpp', 'FileCache.cpp', 'KTXCache.cpp', 'moc0.cpp', 'moc1.cpp']
            for phone in [True, False]:
                options = ['-DANDROID_APP_PHONE_INTERFACE'] if phone else []
                subprocess.run(['c++', '-std=c++17', '-fPIC', '-pthread', *options,
                                '-I', str(path), '-I', str(shared), '-I', str(shared / 'shared'), '-I', str(material),
                                *(str(path / name) for name in sources), '-o', str(path / 'test'), *flags],
                               check=True, timeout=45)
                if phone:
                    subprocess.run([str(path / 'test')], check=True, timeout=10)
                subprocess.run([str(path / 'test'), 'disabled'], check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
