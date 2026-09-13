#!/usr/bin/env python3
"""Exercise the production fatal-snapshot body with small host adapters.

This validates registry/control-flow/bounds behavior, not Qt's private ABI,
Android logging, actual Qt signal delivery, arbitrary corrupted-pointer safety,
or the application's final abort. Those require the real Qt/device checks.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
HEADER = ROOT / 'libraries/qml/src/qml/impl/PhoneQmlFatalDiagnostics.h'
ADAPTERS = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <functional>
#include <string>
#include <thread>
#include <vector>
#include <algorithm>
struct QChar { char16_t value; unsigned unicode() const { return value; } };
struct QString {
    std::vector<QChar> chars;
    QString(const char* s = "qrc:/qml/test.qml") { for (; *s; ++s) chars.push_back({char16_t(*s)}); }
    auto begin() const { return chars.begin(); }
    auto end() const { return chars.end(); }
};
struct QThread { static QThread* currentThread() { static thread_local QThread id; return &id; } };
namespace QV4 {
struct ExecutionEngine;
struct Compiled { uint32_t nameIndex=7, codeSize=100, nRegisters=4; };
struct Function { Compiled* compiledFunction; const char* codeData; };
struct CppStackFrame {
    ExecutionEngine* engine; Function* v4Function; int instructionPointer;
    CppStackFrame* parent=nullptr;
    QString source() const { return QString(); }
};
struct ExecutionEngine { char* jsStackBase; char* jsStackTop; CppStackFrame* currentStackFrame=nullptr; };
}
struct QObject {
    std::vector<std::function<void(QObject*)>> cleanup;
    virtual ~QObject() { for (auto& fn : cleanup) fn(this); }
    void destroyed(QObject*) {}
    template<class Sender, class Signal, class Fn> static void connect(Sender* s, Signal, Fn fn) {
        s->cleanup.push_back(fn);
    }
};
struct QQmlEngine : QObject {
    QV4::ExecutionEngine* handle;
    QThread* owner = QThread::currentThread();
    explicit QQmlEngine(QV4::ExecutionEngine* e=nullptr) : handle(e) {}
    QThread* thread() const { return owner; }
};
struct QQmlEnginePrivate {
    static QQmlEnginePrivate* get(QQmlEngine* e) { static thread_local QQmlEnginePrivate p; p.engine=e; return &p; }
    QV4::ExecutionEngine* v4engine() { return engine->handle; }
    QQmlEngine* engine;
};
constexpr int ANDROID_LOG_FATAL = 7;
thread_local std::vector<std::string> messages;
thread_local bool recurseInLog = false;
extern "C" void overtePhoneQmlFatalSnapshot() noexcept;
int __android_log_print(int, const char*, const char* format, ...) {
    char text[512]; va_list args; va_start(args, format); vsnprintf(text, sizeof(text), format, args); va_end(args);
    messages.emplace_back(text);
    if (recurseInLog) overtePhoneQmlFatalSnapshot();
    return 0;
}
'''
TESTS = r'''
void reset() {
    for (auto& slot : phoneQmlSlots) slot={};
    phoneQmlNextId=phoneQmlRegistryOverflow=0; phoneQmlInFatal=false;
    messages.clear(); recurseInLog=false;
}
unsigned countSlots() { unsigned n=0; for (const auto& s : phoneQmlSlots) n += s.object != nullptr; return n; }
unsigned countMessages(const std::string& prefix) {
    return std::count_if(messages.begin(),messages.end(),[&](const auto& s){return s.rfind(prefix,0)==0;});
}
struct Fixture {
    char code[100] {}; char stack[256] {};
    QV4::Compiled compiled;
    QV4::Function function {&compiled,code};
    QV4::ExecutionEngine engine {stack,stack+80,nullptr};
    QV4::CppStackFrame frame {&engine,&function,50,nullptr};
    QQmlEngine object {&engine};
    Fixture() { for (int i=0;i<100;++i) code[i]=char(i); engine.currentStackFrame=&frame; phoneRegisterQmlEngine(&object); }
};
void registry() {
    reset();
    QQmlEngine first;
    phoneRegisterQmlEngine(&first); phoneRegisterQmlEngine(&first);
    assert(countSlots()==1 && phoneQmlNextId==1 && first.cleanup.size()==1);
    const auto firstId=phoneQmlSlots[0].id;
    phoneUnregisterQmlEngine(&first); phoneUnregisterQmlEngine(&first);
    assert(countSlots()==0);
    phoneRegisterQmlEngine(&first); assert(phoneQmlSlots[0].id>firstId);
    phoneUnregisterQmlEngine(&first);
    auto* transient=new QQmlEngine;
    phoneRegisterQmlEngine(transient); assert(countSlots()==1);
    delete transient; assert(countSlots()==0);
    QQmlEngine many[33];
    for(auto& object:many) phoneRegisterQmlEngine(&object);
    assert(countSlots()==32 && phoneQmlRegistryOverflow==1);
    phoneUnregisterQmlEngine(&many[8]);
    phoneRegisterQmlEngine(&many[32]); assert(countSlots()==32 && phoneQmlRegistryOverflow==1);
    overtePhoneQmlFatalSnapshot();
    assert(messages.size()==1 && messages[0]=="qml_fatal_registry overflow=1");
    reset(); phoneRegisterQmlEngine(&first);
    std::thread worker([&] {
        assert(countSlots()==0);
        phoneRegisterQmlEngine(&first); assert(countSlots()==0);
        QQmlEngine own; phoneRegisterQmlEngine(&own); assert(countSlots()==1);
        phoneUnregisterQmlEngine(&first); assert(countSlots()==1);
    }); worker.join();
    assert(countSlots()==1 && phoneQmlSlots[0].object==&first);
}
void basicSnapshot() {
    reset(); Fixture f;
    recurseInLog=true;
    overtePhoneQmlFatalSnapshot();
    assert(countMessages("qml_fatal_registry ")==1);
    assert(countMessages("qml_frame ")==1 && countMessages("qml_byte ")==48);
    assert(messages[1].find("stack_nonnegative=1 stack_bytes=80")!=std::string::npos);
    assert(messages[3].find("offset=26 value=26")!=std::string::npos);
    assert(messages.back().find("offset=73 value=73")!=std::string::npos);
    const auto size=messages.size(); overtePhoneQmlFatalSnapshot(); assert(messages.size()==size);
    assert(f.engine.currentStackFrame==&f.frame && f.engine.jsStackTop==f.stack+80);
    assert(f.frame.instructionPointer==50 && f.frame.parent==nullptr);
}
void frameLimits() {
    reset(); Fixture f;
    QV4::CppStackFrame frames[10];
    for(int i=0;i<10;++i) frames[i]={&f.engine,&f.function,50,i==9?nullptr:&frames[i+1]};
    f.engine.currentStackFrame=&frames[0];
    overtePhoneQmlFatalSnapshot(); assert(countMessages("qml_frame ")==8 && countMessages("qml_byte ")==384);
    phoneQmlInFatal=false; messages.clear(); frames[0].parent=&frames[0];
    overtePhoneQmlFatalSnapshot(); assert(countMessages("qml_frame ")==1);
    phoneQmlInFatal=false; messages.clear(); frames[0].parent=&frames[1]; frames[1].parent=&frames[0];
    overtePhoneQmlFatalSnapshot(); assert(countMessages("qml_frame ")==8);
    phoneQmlInFatal=false; messages.clear(); frames[0].engine=nullptr;
    overtePhoneQmlFatalSnapshot(); assert(countMessages("qml_frame ")==0);
}
void byteBounds() {
    struct Case { int ip; uint32_t size; unsigned bytes; };
    for (const auto test : std::vector<Case>{{0,100,24},{100,100,24},{3,5,5},{0,0,0},
             {-1,100,0},{101,100,0},{50,1048576,48},{50,1048577,0},{50,UINT32_MAX,0}}) {
        reset(); Fixture f; f.frame.instructionPointer=test.ip; f.compiled.codeSize=test.size;
        overtePhoneQmlFatalSnapshot(); assert(countMessages("qml_byte ")==test.bytes);
    }
    reset(); Fixture f; f.function.codeData=nullptr;
    overtePhoneQmlFatalSnapshot(); assert(countMessages("qml_byte ")==0);
    phoneQmlInFatal=false; messages.clear(); f.frame.v4Function=nullptr;
    overtePhoneQmlFatalSnapshot(); assert(countMessages("qml_frame ")==0);
    phoneQmlInFatal=false; messages.clear(); f.frame.v4Function=&f.function; f.function.compiledFunction=nullptr;
    overtePhoneQmlFatalSnapshot(); assert(countMessages("qml_frame ")==0);
    phoneQmlInFatal=false; messages.clear(); f.engine.currentStackFrame=nullptr;
    overtePhoneQmlFatalSnapshot(); assert(messages.size()==1);
    phoneQmlInFatal=false; messages.clear(); f.engine.currentStackFrame=&f.frame;
    f.engine.jsStackBase=f.stack+80; f.engine.jsStackTop=f.stack;
    overtePhoneQmlFatalSnapshot(); assert(messages[1].find("stack_nonnegative=0 stack_bytes=0")!=std::string::npos);
}
int main() {
    registry(); basicSnapshot(); frameLimits(); byteBounds();
    puts("PASS production QML fatal body: registry, destruction, thread isolation, recursion, frame cycles, bytecode bounds");
}
'''


def main():
    source = HEADER.read_text()
    body = source[source.index('namespace {'):source.rindex('#endif')]
    with tempfile.TemporaryDirectory(prefix='overte-qml-fatal-test-') as folder:
        cpp = Path(folder) / 'test.cpp'
        exe = Path(folder) / 'test'
        cpp.write_text(ADAPTERS + body + TESTS)
        sanitizers = os.environ.get('QML_TEST_SANITIZERS', '')
        flags = ['-fsanitize=' + sanitizers, '-fno-omit-frame-pointer'] if sanitizers else []
        subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-O1', '-g', '-pthread',
                        *flags, str(cpp), '-o', str(exe)], check=True)
        print('Sanitizers: ' + (sanitizers or 'disabled (set QML_TEST_SANITIZERS=address,undefined when available)'), flush=True)
        subprocess.run([str(exe)], check=True)
    print('LIMIT: adapters do not validate Qt ABI/signal runtime, Android log delivery, corrupted pointers, or final abort.')


if __name__ == '__main__':
    main()
