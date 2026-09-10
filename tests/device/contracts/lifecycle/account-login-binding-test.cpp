// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <cassert>
#include "interface/src/ui/AccountLoginStateBinding.h"
class Manager : public QObject {
    Q_OBJECT
public:
    void succeed() { emit loginComplete(); }
    void fail() { emit loginFailed(); }
signals:
    void loginComplete();
    void loginFailed();
};
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    PhoneLoginState state;
    QPointer<AccountLoginStateBinding<Manager>> binding;
    Manager first, second;
    bindAccountLoginState(state, binding, &first, &app);
    auto original = binding.data();
    assert(state.beginRequest());
    bindAccountLoginState(state, binding, &first, &app);
    assert(binding == original && state.requestPending());
    first.succeed();
    assert(!state.requestPending());
    assert(state.beginRequest());
    first.fail();
    assert(!state.requestPending());
    assert(state.beginRequest());
    bindAccountLoginState(state, binding, &second, &app);
    assert(!state.requestPending());
    assert(state.beginRequest());
    first.succeed(); first.fail();
    assert(state.requestPending()); // Old account cannot finish the new request.
    second.fail();
    assert(!state.requestPending());
    auto transient = new Manager;
    bindAccountLoginState(state, binding, transient, &app);
    assert(state.beginRequest());
    delete transient;
    assert(!state.requestPending());
}
#include "account-login-binding.moc"
