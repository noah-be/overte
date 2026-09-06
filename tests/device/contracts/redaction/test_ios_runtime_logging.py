"""Actual entire Apple Shared header, real Qt and an explicit OS capture seam."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class IOSRuntimeLogging(unittest.TestCase):
    def test_complete_original_header_and_both_raw_sinks(self):
        flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
        with tempfile.TemporaryDirectory(prefix='px16-apple-log-') as temporary:
            directory = pathlib.Path(temporary)
            source = (ROOT / 'libraries/networking/src/NodeList.cpp').read_text()
            start = source.index('    if (!_domainHandler.isConnected()) {')
            end = source.index('\n    }', start) + len('\n    }')
            (directory / 'nodelist-connected.inc').write_text(source[start:end])
            (directory / 'os').mkdir()
            (directory / 'os/log.h').write_text('''#pragma once
#include <vector>
#include <QtCore/QString>
#include <cassert>
#include <cstring>
static std::vector<QString> osMessages;
#define OS_LOG_DEFAULT 0
inline void os_log_info(int, const char* format, const char* text) {
    assert(std::strcmp(format, "%{public}s") == 0);
    osMessages.push_back(QString::fromUtf8(text));
}
''')
            for os_sink in (0,1):
                with self.subTest(os_sink=os_sink):
                    binary = directory / ('test-' + str(os_sink))
                    subprocess.run(['c++','-std=c++17','-fPIC','-I',str(ROOT),'-I',str(directory),
                                    '-DTEST_OS_SINK='+str(os_sink),str(pathlib.Path(__file__).with_name('ios-runtime-logging-test.cpp')),
                                    '-o',str(binary),*flags],check=True,timeout=30)
                    subprocess.run(['unshare','--user','--map-root-user','--net',str(binary)],
                                   env={**os.environ,'QT_LOGGING_RULES':'*.info=true'},check=True,timeout=5)


if __name__ == '__main__':
    unittest.main()
