"""Compile the actual NodeList domain-auth packet block with real Qt streams."""
from pathlib import Path
import os
import resource
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class DomainPacketSnapshot(unittest.TestCase):
    def test_packet_uses_the_credential_checked_for_admission(self):
        relative = 'libraries/networking/src/NodeList.cpp'
        baseline = os.environ.get('OVERTE_DOMAIN_PACKET_BASELINE')
        source = (subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline + ':' + relative], text=True)
                  if baseline else (ROOT / relative).read_text())
        block = '            if (_hasDomainAccountManager) {' + source.split(
            '            if (_hasDomainAccountManager) {', 1)[1].split('\n            }', 1)[0] + '\n            }\n'
        driver = r'''
#include <QtCore/QtCore>
#include <cassert>
struct DomainAccountManager {
    QString username = "user-canary", token = "token-canary", refresh = "refresh-canary", empty;
    int reads = 0;
    const QString& getUsername() { return username; }
    const QString& getAccessToken() { return ++reads == 1 ? token : empty; }
    const QString& getRefreshToken() { return refresh; }
} manager;
struct DependencyManager { template<class T> static T* get() { return &manager; } };
QByteArray packet(bool _hasDomainAccountManager) {
    QByteArray bytes;
    QDataStream packetStream(&bytes, QIODevice::WriteOnly);
'''
        checks = r'''
    return bytes;
}
int main() {
    assert(packet(false).isEmpty() && manager.reads == 0);
    auto bytes = packet(true);
    QDataStream input(bytes); QString username, credential; input >> username >> credential;
    assert(input.status() == QDataStream::Ok && input.atEnd());
    assert(username == "user-canary" && credential == "token-canary:refresh-canary");
    assert(manager.reads == 1);
    manager.reads = 0; manager.token.clear();
    assert(packet(true).isEmpty());
    manager.reads = 0; manager.token = "token-canary"; manager.username.clear();
    assert(packet(true).isEmpty());
}
'''
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-domain-packet-') as temporary:
            scratch = Path(temporary); cpp = scratch / 'test.cpp'; binary = scratch / 'test'
            cpp.write_text(driver + block + checks)
            subprocess.run(['c++', '-std=c++17', '-fPIC', str(cpp), '-o', str(binary), *flags], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
