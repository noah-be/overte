#!/usr/bin/env python3
"""Execute actual saveObject with real Qt files at the open/write boundary."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / 'interface/src/scripting/TestScriptingInterface.cpp').read_text()
start = source.index('void TestScriptingInterface::saveObject(')
end = source.index('\nvoid TestScriptingInterface::showMaximized()', start)
method = source[start:end].replace('QFile file(filepath);', 'ObservedQFile file(filepath);')
method = method.replace('QSaveFile file(filepath);', 'ObservedQSaveFile file(filepath);')
harness = r'''
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSaveFile>
#include <QTemporaryDir>
#include <QVariant>
#include <QLoggingCategory>
#include <cassert>
Q_LOGGING_CATEGORY(trace_test, "trace.test")
static int observations=0, incomplete=0;
static void observe(const QString& path) {
    QFile actual(path);
    assert(actual.open(QIODevice::ReadOnly));
    const auto document=QJsonDocument::fromJson(actual.readAll());
    observations++;
    if (!document.isObject() || !document.object().contains("sequence")) { incomplete++; }
}
// Scheduling seam: a real independent reader is run immediately after open
// and before write. Both classes still use the actual Qt filesystem methods.
class ObservedQFile : public QFile {
public:
    using QFile::QFile;
    bool open(OpenMode mode) override {
        const bool ok=QFile::open(mode);
        if(ok) { observe(fileName()); }
        return ok;
    }
};
class ObservedQSaveFile : public QSaveFile {
public:
    using QSaveFile::QSaveFile;
    bool open(OpenMode mode) override {
        const bool ok=QSaveFile::open(mode);
        if(ok) { observe(fileName()); }
        return ok;
    }
};
class TestScriptingInterface {
public:
    QString _testResultsLocation;
    void saveObject(QVariant variant, const QString& filename);
};
#if TEST_ATOMIC
#define Q_OS_IOS
#else
#undef Q_OS_IOS
#endif
METHOD
int main(int argc, char** argv) {
    QCoreApplication app(argc,argv);
    QTemporaryDir directory;
    assert(directory.isValid());
    const auto path=directory.path()+"/observation.json";
    QFile initial(path);
    assert(initial.open(QIODevice::WriteOnly));
    assert(initial.write("{\"sequence\":0}")>0);
    initial.close();
    TestScriptingInterface actual;
    actual._testResultsLocation=directory.path();
    for(int sequence=1;sequence<=250;sequence++) {
        QVariantMap sample {{"sequence",sequence},{"payload",QString(32768,QChar(0x00e4))}};
        actual.saveObject(sample,"observation.json");
        QFile committed(path);
        assert(committed.open(QIODevice::ReadOnly));
        const auto document=QJsonDocument::fromJson(committed.readAll());
        assert(document.isObject());
        assert(document.object()["sequence"].toInt()==sequence);
    }
    assert(observations==250);
#if TEST_ATOMIC
    assert(incomplete==0);
#else
    assert(incomplete==250);
#endif
}
'''.replace('METHOD', method)
flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
with tempfile.TemporaryDirectory(prefix='ios-observation-publication-') as directory:
    root = Path(directory)
    cpp = root / 'publication.cpp'
    cpp.write_text(harness)
    for atomic in (False, True):
        executable = root / ('atomic' if atomic else 'legacy')
        subprocess.run(['c++', '-std=c++17', '-O2', '-fPIC', f'-DTEST_ATOMIC={int(atomic)}',
                        str(cpp), '-o', str(executable), *flags], check=True, timeout=60)
        subprocess.run([str(executable)], check=True, timeout=15)
print('PASS actual iOS saveObject publishes complete files; legacy truncate/read race reproduced.')
