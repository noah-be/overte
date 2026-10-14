// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QObject>
#include <QSharedPointer>
#include <QString>
#include <cassert>
#include <iostream>

class AccountManager : public QObject {
    Q_OBJECT
public:
    void requireAuthentication() { emit authRequired(); }
signals:
    void authRequired();
};

class DialogsManager : public QObject {
    Q_OBJECT
public:
    int opened { 0 };
    void showLoginDialog() { ++opened; }
};

class AddressManager {
public:
    QString currentAddress() const { return "overte://fixture.example/"; }
};

class DependencyManager {
public:
    template <typename T> static QSharedPointer<T> get() {
        static auto instance = QSharedPointer<T>::create();
        return instance;
    }
};

// The fixture records the obsolete Activity request; it never calls JNI.
class AndroidHelper {
public:
    static AndroidHelper& instance() { static AndroidHelper instance; return instance; }
    int requested { 0 };
    void showLoginDialog(const QString&) { ++requested; }
};

class Application : public QObject {
public:
    void setup() {
        auto dialogsManager = DependencyManager::get<DialogsManager>();
#include "production-auth-dispatch.inc"
    }
};

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    auto dialogs = DependencyManager::get<DialogsManager>();
    auto accounts = DependencyManager::get<AccountManager>();
    {
        Application application;
        application.setup();
        accounts->requireAuthentication();
        accounts->requireAuthentication();
#if defined(EXPECT_LEGACY_ACTIVITY)
        assert(dialogs->opened == 0);
        assert(AndroidHelper::instance().requested == 2);
#else
        assert(dialogs->opened == 2);
        assert(AndroidHelper::instance().requested == 0);
#endif
    }
    // Connection lifetime matches the production context/receiver. Teardown
    // must not leave a request bound to the destroyed Application.
#if defined(EXPECT_LEGACY_ACTIVITY)
    accounts->requireAuthentication();
    assert(AndroidHelper::instance().requested == 2);
#endif
    std::cout << "PASS real Qt authRequired dispatch\n";
}

#include "account-auth-dispatch-test.moc"
