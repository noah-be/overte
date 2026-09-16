// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QObject>
#include <QMetaType>
#include <functional>
#include <memory>
struct ScriptValueV8Wrapper;
struct ScriptValue {
 std::shared_ptr<ScriptValueV8Wrapper> value;
 ScriptValue()=default;
 explicit ScriptValue(ScriptValueV8Wrapper* p);
};
Q_DECLARE_METATYPE(ScriptValue)
extern int nativeCalls;
extern std::function<void()> duringNative;
class Target : public QObject {
 Q_OBJECT
 public:
 Q_INVOKABLE int number(int x, int y) { ++nativeCalls; if(duringNative)duringNative(); return x+y; }
 Q_INVOKABLE void empty(int) { ++nativeCalls; }
 Q_INVOKABLE ScriptValue wrapped(ScriptValue x) { ++nativeCalls; return x; }
};
