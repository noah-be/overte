"""All actual direct OS expressions, raw captured transport; no renderer claim."""
import pathlib
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class AppleVulkanDiagnostics(unittest.TestCase):
    def test_all_actual_os_payloads_preserve_severity_and_close_data(self):
        calls = []
        for name, expected in (('VKBackend.cpp',41),('VKPipelineCache.cpp',3)):
            source = (ROOT / 'libraries/gpu-vk/src/gpu/vk' / name).read_text()
            found = re.findall(r'\bos_log_(?:info|fault)\([^;]+;', source)
            self.assertEqual(len(found),expected)
            self.assertEqual(len(re.findall(r'\bos_log\w*\s*\(',source)),expected)
            for call in found:
                self.assertRegex(call,r'^os_log_(?:info|fault)\(OS_LOG_DEFAULT, "%\{public\}s",\s*'
                                 r'overte::security::diagnosticEvent\(overte::security::DiagnosticEvent::Redacted\)\);$')
            calls.extend(found)
        flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
        with tempfile.TemporaryDirectory(prefix='px16-vulkan-os-') as temporary:
            directory = pathlib.Path(temporary)
            kinds = ','.join('true' if call.startswith('os_log_fault') else 'false' for call in calls)
            driver = '''#include <cassert>
#include <cstring>
#include <vector>
#include <QtCore/QCoreApplication>
#include <QtCore/QString>
#include "security/redaction/SafeDiagnostics.h"
static std::vector<QString> messages;
static std::vector<bool> faults;
#define OS_LOG_DEFAULT 0
static void receive(const char* format,const char* text,bool fault) {
 assert(std::strcmp(format,"%{public}s")==0);
 messages.push_back(QString::fromUtf8(text)); faults.push_back(fault);
}
static void os_log_info(int,const char* f,const char* s) { receive(f,s,false); }
static void os_log_fault(int,const char* f,const char* s) { receive(f,s,true); }
int main(int argc,char** argv) {
 QCoreApplication app(argc,argv);
 os_log_info(OS_LOG_DEFAULT,"%{public}s","sink-private-canary");
 assert(messages.back()=="sink-private-canary"); // Positively prove raw transport.
 messages.clear(); faults.clear();
 CALLS
 const std::vector<bool> expected {KINDS};
 assert(faults==expected && messages.size()==44);
 for(const auto& message:messages) assert(message=="OVT_REDACTED");
}
'''.replace('CALLS','\n'.join(calls)).replace('KINDS',kinds)
            cpp = directory / 'test.cpp'
            cpp.write_text(driver)
            binary = directory / 'test'
            subprocess.run(['c++','-std=c++17','-fPIC','-I',str(ROOT),str(cpp),'-o',str(binary),*flags],check=True,timeout=30)
            subprocess.run(['unshare','--user','--map-root-user','--net',str(binary)],check=True,timeout=5)


if __name__ == '__main__': unittest.main()
