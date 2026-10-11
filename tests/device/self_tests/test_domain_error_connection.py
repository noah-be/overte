"""Compile and execute the production serverless connection transition."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[3] / 'libraries/networking/src/DomainHandler.cpp'


@unittest.skipUnless(shutil.which('g++'), 'A native C++ compiler is required')
class DomainErrorConnectionTest(unittest.TestCase):
    def test_error_world_keeps_network_retries_but_local_worlds_stop_them(self):
        source = (SOURCE.parents[3] / 'interface/src/Application.cpp').read_text()
        start = source.index('void Application::setIsServerlessMode(')
        finish = source.index('\nbool Application::prepareServerlessDomainContents(', start)
        transition = source[start:finish]
        program = r'''
#include <cassert>
struct Handler { bool local; bool isServerless()const{return local;} };
struct NodeList {
    Handler handler;
    bool retries=false;
    void setSendDomainServerCheckInEnabled(bool value){retries=value;}
    Handler& getDomainHandler(){return handler;}
};
NodeList node;
struct DependencyManager { template<class T> static T* get(){return &node;} };
struct Tree { bool local=false; void setIsServerlessMode(bool value){local=value;} };
struct Entities { Tree tree; Tree* getTree(){return &tree;} };
struct Application {
    Entities entities;
    bool _waitForServerlessToBeSet=true;
    Entities* getEntities(){return &entities;}
    void setIsServerlessMode(bool);
};
''' + transition + r'''
int main(){
    Application app;
    node.handler.local=false; app.setIsServerlessMode(true);
    assert(node.retries && app.entities.tree.local && !app._waitForServerlessToBeSet);
    node.handler.local=true; app.setIsServerlessMode(true);
    assert(!node.retries && app.entities.tree.local);
    app.setIsServerlessMode(false);
    assert(node.retries && !app.entities.tree.local);
}
'''
        self.compile_and_run(program)

    @staticmethod
    def compile_and_run(program):
        with tempfile.TemporaryDirectory(prefix='domain-error-transition-') as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(program)
            subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', str(path / 'test.cpp'),
                            '-o', str(path / 'test')], check=True, capture_output=True)
            subprocess.run([str(path / 'test')], check=True, capture_output=True)

    def test_error_scene_does_not_confirm_an_online_domain(self):
        source = SOURCE.read_text()
        start = source.index('void DomainHandler::connectedToServerless(')
        finish = source.index('\nvoid DomainHandler::loadedErrorDomain(', start)
        transition = source[start:finish]
        program = r'''
#include <cassert>
#include <map>
#include <string>
using QString = std::string;
struct DomainHandler {
    std::string scheme;
    bool connected = false;
    unsigned confirmed = 0;
    std::map<QString, QString> _namedPaths;
    bool isServerless() const { return scheme != "hifi"; }
    void setIsConnected(bool value) { connected=value; if(value){++confirmed;} }
    void connectedToServerless(std::map<QString, QString>);
};
''' + transition + r'''
int main() {
    const std::map<QString,QString> paths {{"/", "0,0,0"}};
    DomainHandler online {"hifi"};
    online.connectedToServerless(paths);
    assert(!online.connected && online.confirmed == 0);
    assert(online._namedPaths == paths);
    // A late local scene must not replace or revoke a real online handshake.
    online.connected = true;
    online.connectedToServerless(paths);
    assert(online.connected && online.confirmed == 0);
    for (const auto& scheme : {"file", "qrc", "atp", "https"}) {
        DomainHandler local {scheme};
        local.connectedToServerless(paths);
        assert(local.connected && local.confirmed == 1);
        assert(local._namedPaths == paths);
    }
}
'''
        self.compile_and_run(program)


if __name__ == '__main__':
    unittest.main()
