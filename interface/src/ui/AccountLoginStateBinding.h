#pragma once

#include <QtCore/QObject>
#include <QtCore/QPointer>
#include "PhoneLoginState.h"

// UI-thread binding whose lifetime belongs to the application, not a dialog.
// Account results must never clear a different domain request's ownership.
template<class Manager>
class AccountLoginStateBinding : public QObject {
public:
    AccountLoginStateBinding(Manager* manager, PhoneLoginState& state, QObject* parent) :
        QObject(parent), _manager(manager) {
        connect(manager, &Manager::loginComplete, this, [&state] { state.finishRequest(); });
        connect(manager, &Manager::loginFailed, this, [&state] { state.finishRequest(); });
        connect(manager, &QObject::destroyed, this, [&state] { state.finishRequest(); });
    }
    Manager* manager() const { return _manager.data(); }
private:
    QPointer<Manager> _manager;
};

template<class Manager>
void bindAccountLoginState(PhoneLoginState& state,
                          QPointer<AccountLoginStateBinding<Manager>>& binding,
                          Manager* manager, QObject* application) {
    if (binding && binding->manager() == manager) {
        return;
    }
    // Drop old-context queued deliveries before admitting a new manager's
    // requests. QObject destruction disconnects all old observer callbacks.
    delete binding.data();
    state.finishRequest();
    binding = new AccountLoginStateBinding<Manager>(manager, state, application);
}
