#!/usr/bin/env python3
"""Compile the actual native firing hook and prove real SIGABRT and its receipt."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NativeCrash(unittest.TestCase):
    def test_actual_hook_requires_explicit_test_launch_and_fires_sigabrt(self):
        original = (ROOT / "interface/src/scripting/TestScriptingInterface.cpp").read_text()
        hook = "bool TestScriptingInterface::iosCrashTest(" + original.split(
            "bool TestScriptingInterface::iosCrashTest(", 1)[1].split(
            "bool TestScriptingInterface::iosEntityScriptConsentTest(", 1)[0]
        writer = "void TestScriptingInterface::saveObject(" + original.split(
            "void TestScriptingInterface::saveObject(", 1)[1].split(
            "void TestScriptingInterface::showMaximized(", 1)[0]
        fixture = r'''
#include <QCoreApplication>
#include <QDateTime>
#include <QDir>
#include <QJsonDocument>
#include <QLoggingCategory>
#include <QRegularExpression>
#include <QSaveFile>
#include <QTimer>
#include <QVariantMap>
#include <cstdlib>
#include <cassert>
#include <sys/resource.h>
#define Q_OS_IOS 1
Q_LOGGING_CATEGORY(trace_test, "trace.test")
class TestScriptingInterface : public QObject {
public:
    QString _testResultsLocation;
    bool iosCrashTest(const QVariantMap&);
    void saveObject(QVariant,const QString&);
};
// ACTUAL_CODE
int main(int argc,char** argv) {
    const rlimit noCore{0,0};assert(setrlimit(RLIMIT_CORE,&noCore)==0);
    QCoreApplication app(argc,argv);
    TestScriptingInterface test;test._testResultsLocation=QString::fromLocal8Bit(argv[1]);
    QVariantMap command{{"schemaVersion",1},{"commandId","ios-cccccccccccccccccccccccccccccccc"},
        {"action","native-crash"}};
    if(!QCoreApplication::arguments().contains("--testScript")) {
        assert(!test.iosCrashTest(command));return 0;
    }
    auto foreign=command;foreign["processId"]=1;
    assert(!test.iosCrashTest(foreign));
    assert(test.iosCrashTest(command));
    QTimer::singleShot(2000,&app,[]{QCoreApplication::exit(99);});
    return app.exec();
}
'''.replace("// ACTUAL_CODE", hook + writer)
        with tempfile.TemporaryDirectory(prefix="native-crash-contract-") as directory:
            root = Path(directory); cpp = root / "test.cpp"; cpp.write_text(fixture)
            flags = shlex.split(subprocess.check_output(
                ["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
            binary = root / "test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", str(cpp), "-o", str(binary), *flags],
                           check=True, timeout=30)
            subprocess.run([str(binary), directory], check=True, timeout=5)
            receipt = root / "ios-crash-result.json"
            self.assertFalse(receipt.exists())
            process = subprocess.Popen([str(binary), directory, "--testScript", "controlled.js"])
            self.assertEqual(process.wait(timeout=5), -int(signal.SIGABRT))
            document = json.loads(receipt.read_text())
            self.assertEqual(set(document), {"schemaVersion", "commandId", "cause", "phase",
                                            "processId", "sampleEpochMs"})
            self.assertEqual(document["processId"], process.pid)
            self.assertEqual(document["commandId"], "ios-" + "c" * 32)
            self.assertEqual(document["cause"], "SIGABRT")
            self.assertEqual(document["phase"], "firing")
            self.assertLess(abs(time.time() * 1000 - document["sampleEpochMs"]), 5000)


if __name__ == "__main__": unittest.main()
