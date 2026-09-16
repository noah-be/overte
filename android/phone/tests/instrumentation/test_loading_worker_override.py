#!/usr/bin/env python3
"""Execute actual startup/update code for the bounded Phone worker experiment."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class WorkerOverrideTest(unittest.TestCase):
    def test_startup_and_later_plugin_updates(self):
        source = (ROOT / 'interface/src/Application.cpp').read_text()
        begin = source.index('static const int UI_RESERVED_THREADS')
        end = source.index('\nvoid Application::gotoTutorial()', begin)
        update = source[begin:end]
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        begin = setup.index('        // Phone worker experiment:')
        end = setup.index('        if (_useSystemCursor)', begin)
        startup = setup[begin:end]
        fixture = r'''
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#define PROP_VALUE_MAX 92
bool diagnostics = false;
const char* property = "0";
int propertyReads = 0;
int ideal = 9;
std::string marker;
bool phoneLoadingDiagnosticsEnabled() { return diagnostics; }
int __system_property_get(const char* key, char* out) {
    assert(std::string(key) == "debug.overte.loading.workers");
    ++propertyReads; strcpy(out, property); return strlen(property);
}
#define PHONE_LOADING(...) do { if (diagnostics) { char out[512]; snprintf(out,sizeof(out),__VA_ARGS__); marker=out; } } while(0)
struct Sink { template<class T> Sink& operator<<(const T&) { return *this; } };
#define qCDebug(category) Sink()
struct QThread { static int idealThreadCount() { return ideal; } };
struct QThreadPool {
    int size = 2;
    void setMaxThreadCount(int value) { size = value; }
    int maxThreadCount() { return size; }
    static QThreadPool* globalInstance() { static QThreadPool pool; return &pool; }
};
struct Plugin { int required = 1; int getRequiredThreadCount() { return required; } };
static const int MIN_PROCESSING_THREAD_POOL_SIZE = 2;
struct Application {
    Plugin plugin;
    Plugin* _displayPlugin = &plugin;
    void updateThreadPoolCount() const;
    void startup() {
''' + startup + r'''
    }
};
''' + update + r'''
void reset() { QThreadPool::globalInstance()->size=2; marker.clear(); propertyReads=0; }
int main() {
    Application app;
    // Diagnostics disabled cannot change startup behavior or read properties.
    property="4"; reset(); app.startup();
    assert(QThreadPool::globalInstance()->size==2 && propertyReads==0);
    app.updateThreadPoolCount();
    assert(QThreadPool::globalInstance()->size==6 && propertyReads==0);
    diagnostics=true;
    for (const char* value : {"", "0", "1", "3", "8", "04", "40", " 4", "4 ", "invalid"}) {
        property=value; reset(); app.startup();
        assert(QThreadPool::globalInstance()->size==2);
#ifdef ANDROID_APP_PHONE_INTERFACE
        assert(marker=="phase=worker_pool ideal=9 reserved=3 requested=0 actual=2");
#else
        assert(marker.empty() && propertyReads==0);
#endif
        app.updateThreadPoolCount(); // ordinary later plugin-switch behavior
        assert(QThreadPool::globalInstance()->size==6);
    }
    for (const char* value : {"2", "4"}) {
        property=value; reset(); app.startup();
#ifdef ANDROID_APP_PHONE_INTERFACE
        assert(QThreadPool::globalInstance()->size==value[0]-'0');
        app.plugin.required=2;
        app.updateThreadPoolCount();
        assert(QThreadPool::globalInstance()->size==value[0]-'0');
        assert(marker==std::string("phase=worker_pool ideal=9 reserved=4 requested=")+value+" actual="+value);
        diagnostics=false;
        app.updateThreadPoolCount();
        assert(QThreadPool::globalInstance()->size==5);
        diagnostics=true;
#else
        assert(QThreadPool::globalInstance()->size==2 && propertyReads==0);
        app.updateThreadPoolCount();
        assert(QThreadPool::globalInstance()->size==6);
#endif
        app.plugin.required=1;
    }
    diagnostics=false; ideal=-1;
    app.updateThreadPoolCount();
    assert(QThreadPool::globalInstance()->size==2);
    diagnostics=true; app._displayPlugin=nullptr; reset();
    app.startup(); // no premature display dereference during diagnostic setup
    assert(QThreadPool::globalInstance()->size==2 && propertyReads==0);
}
'''
        with tempfile.TemporaryDirectory(prefix='phone-worker-override-') as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(fixture)
            for phone in [False, True]:
                command = ['c++', '-std=c++17', '-O2', '-Wall', '-Wextra']
                if phone:
                    command.append('-DANDROID_APP_PHONE_INTERFACE')
                command += [str(path / 'test.cpp'), '-o', str(path / 'test')]
                subprocess.run(command, check=True)
                subprocess.run([str(path / 'test')], check=True)


if __name__ == '__main__':
    unittest.main()
