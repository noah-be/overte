#!/usr/bin/env python3
"""Execute the real log handler with a full stdout pipe and a live Qt UI timer."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ConsoleBackpressure(unittest.TestCase):
    def test_ios_native_sink_keeps_writer_and_main_timer_live_without_raw_payload(self):
        source = (ROOT / 'libraries/shared/src/LogHandler.cpp').read_text()
        native_stub = r'''
#pragma once
#include <cstring>
#include <cassert>
#include <string>
#include <vector>
using os_log_type_t = int;
constexpr auto OS_LOG_DEFAULT = nullptr;
enum { OS_LOG_TYPE_DEFAULT, OS_LOG_TYPE_INFO, OS_LOG_TYPE_DEBUG,
       OS_LOG_TYPE_ERROR, OS_LOG_TYPE_FAULT };
inline std::vector<std::string> nativeMessages;
inline std::vector<int> nativeTypes;
inline void os_log_with_type(void*, int type, const char* format, const char* message) {
    assert(std::strcmp(format, "%{public}s") == 0);
    assert(std::strcmp(message, "OVT_REDACTED") == 0 ||
           std::strcmp(message, "OVT_CONNECTION_READY") == 0);
    nativeMessages.emplace_back(message);nativeTypes.push_back(type);
}
'''
        fixture = r'''
#include <QtCore/QtCore>
#define Q_OS_IOS 1
#include "os/log.h"
#include "actual-handler.cpp"
#include <atomic>
#include <thread>
#include <cassert>
#include <sys/resource.h>
int main(int argc,char** argv) {
    const rlimit noCore{0,0};assert(setrlimit(RLIMIT_CORE,&noCore)==0);
    QCoreApplication app(argc,argv);
    auto& logger=LogHandler::getInstance();
    logger.setupRepeatedMessageFlusher();
    const int id=logger.newRepeatedMessageID();
    std::atomic<bool> completed{false};
    std::thread writer([&] {
        const QString canary=QString(8192,QChar('x'))+"private-console-canary";
        for(int i=0;i<10;++i) {
            logger.printRepeatedMessage(id,LogDebug,QMessageLogContext(),canary);
        }
        completed.store(true);
    });
    QTimer::singleShot(6500,&app,[&] { assert(completed.load());app.quit(); });
    app.exec();writer.join();
    const QString returned=logger.printMessage(LogInfo,QMessageLogContext(),"OVT_CONNECTION_READY");
    assert(returned.contains("OVT_CONNECTION_READY"));
    assert(nativeMessages.size()==3);
    assert(nativeMessages[0]=="OVT_REDACTED" && nativeMessages[1]=="OVT_REDACTED");
    assert(nativeMessages[2]=="OVT_CONNECTION_READY" && nativeTypes[2]==OS_LOG_TYPE_INFO);
    QFile result(QString::fromLocal8Bit(argv[1]));assert(result.open(QIODevice::WriteOnly));
    result.write("{\"writerProgress\":true,\"mainTimerProgress\":true,\"sanitized\":true}");
}
'''
        with tempfile.TemporaryDirectory(prefix='ios-log-backpressure-') as directory:
            root = Path(directory); (root / 'os').mkdir()
            (root / 'os/log.h').write_text(native_stub)
            (root / 'main.cpp').write_text(fixture)
            flags = shlex.split(subprocess.check_output(
                ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
            libexec = subprocess.check_output(
                ['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip()
            subprocess.run([str(Path(libexec) / 'moc'), str(ROOT / 'libraries/shared/src/LogHandler.h'),
                            '-o', str(root / 'moc.cpp')], check=True, timeout=30)
            for mutation in (False, True):
                (root / 'actual-handler.cpp').write_text(
                    source.replace('#if defined(Q_OS_IOS)', '#if 0') if mutation else source)
                binary = root / ('old-console' if mutation else 'native-console')
                subprocess.run(['c++', '-std=c++17', '-pthread', '-fPIC', '-I', str(root),
                    '-I', str(ROOT / 'libraries/shared/src'), str(root / 'main.cpp'),
                    str(root / 'moc.cpp'), '-o', str(binary), *flags], check=True, timeout=45)
                read_fd, write_fd = os.pipe()
                try:
                    os.set_blocking(write_fd, False)
                    try:
                        while True: os.write(write_fd, b'x' * 4096)
                    except BlockingIOError: pass
                    os.set_blocking(write_fd, True)
                    receipt = root / ('old.json' if mutation else 'native.json')
                    process = subprocess.Popen([str(binary), str(receipt)], stdout=write_fd,
                        env={**os.environ, 'OVERTE_LOG_OPTIONS': 'nocolor,nojournald'})
                    try:
                        if mutation:
                            with self.assertRaises(subprocess.TimeoutExpired): process.wait(timeout=8)
                            self.assertFalse(receipt.exists())
                        else:
                            self.assertEqual(process.wait(timeout=15), 0)
                            self.assertEqual(json.loads(receipt.read_text()), {
                                'writerProgress': True, 'mainTimerProgress': True, 'sanitized': True})
                    finally:
                        if process.poll() is None: process.kill(); process.wait(timeout=5)
                finally:
                    os.close(read_fd); os.close(write_fd)


if __name__ == '__main__': unittest.main()
