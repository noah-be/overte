"""Execute the real periodic callback while an offline world is displayed."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('g++'), 'A C++ compiler is required')
class DomainCheckInTimerTest(unittest.TestCase):
    def test_selected_network_domain_retries_during_local_error_presentation(self):
        source = (Path(__file__).resolve().parents[3] / 'interface/src/Application_Setup.cpp').read_text()
        marker = 'connect(domainCheckInTimer, &QTimer::timeout, [this, nodeList] {'
        body = source.split(marker, 1)[1].split('\n        });', 1)[0]
        program = r'''
#include <cassert>
struct Handler { bool local; bool isServerless() const { return local; } };
struct NodeList {
    Handler domain;
    unsigned checkIns = 0;
    Handler& getDomainHandler() { return domain; }
    void sendDomainServerCheckIn() { ++checkIns; }
};
struct Application {
    bool localPresentation = false;
    bool isServerlessMode() const { return localPresentation; }
    void periodic(NodeList* nodeList) {
''' + body + r'''
    }
};
int main() {
    Application app;
    NodeList node {{false}};
    app.periodic(&node);
    assert(node.checkIns == 1);
    app.localPresentation = true;
    app.periodic(&node);
    assert(node.checkIns == 2); // Continue actual handshake in the error world.
    node.domain.local = true;
    app.periodic(&node);
    assert(node.checkIns == 2); // An intentionally selected local world is offline.
    app.localPresentation = false;
    app.periodic(&node);
    assert(node.checkIns == 2);
}
'''
        with tempfile.TemporaryDirectory(prefix='domain-checkin-timer-') as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(program)
            subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', str(path / 'test.cpp'),
                            '-o', str(path / 'test')], capture_output=True, check=True)
            subprocess.run([str(path / 'test')], capture_output=True, check=True)


if __name__ == '__main__':
    unittest.main()
