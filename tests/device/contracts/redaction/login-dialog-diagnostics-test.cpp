// SPDX-License-Identifier: Apache-2.0
// Three complete original callers, original PhoneLoginState, real Qt JSON/raw logger.
#include <QtCore/QtCore>
#include <QtNetwork/QtNetwork>
#include <cassert>
#include <vector>
#include "security/redaction/SafeDiagnostics.h"
#include "interface/src/ui/PhoneLoginState.h"
#if TEST_PHONE
#define ANDROID_APP_PHONE_INTERFACE 1
#endif
#if TEST_IOS
#define Q_OS_IOS 1
#endif
static PhoneLoginState phoneLoginState;
struct JSONCallbackParameters { QObject* callbackReceiver {}; QString jsonCallbackMethod, errorCallbackMethod; };
namespace AccountManagerAuth { enum Type { None }; }
static const QString API_SIGNUP_PATH = "/api/v1/users"; // Transport route is an explicit boundary.
struct AccountManager {
    int calls {}, signups {};
    QString user, password; QByteArray signup;
    QObject* receiver {};
    void requestAccessToken(const QString& u, const QString& p) { ++calls; user = u; password = p; }
    void sendRequest(const QString& path, AccountManagerAuth::Type auth, QNetworkAccessManager::Operation op,
                     const JSONCallbackParameters& callbacks, const QByteArray& payload) {
        assert(path == API_SIGNUP_PATH && auth == AccountManagerAuth::None && op == QNetworkAccessManager::PostOperation);
        assert(callbacks.jsonCallbackMethod == "signupCompleted" && callbacks.errorCallbackMethod == "signupFailed");
        ++signups; receiver = callbacks.callbackReceiver; signup = payload;
    }
};
struct DomainAccountManager : AccountManager {};
struct DependencyManager { template<class T> static T* get() { static T instance; return &instance; } };
struct LoginDialog : QObject {
    void login(const QString&, const QString&) const;
    void loginDomain(const QString&, const QString&) const;
    void signup(const QString&, const QString&, const QString&);
};
#include "login-methods.inc"
static std::vector<QString> logs;
static void capture(QtMsgType, const QMessageLogContext&, const QString& text) { logs.push_back(text); }
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    QLoggingCategory::setFilterRules("*.debug=true");
    qInstallMessageHandler(capture);
    qDebug() << "raw-sink-probe";
    assert(logs.size() == 1 && logs[0] == "raw-sink-probe");
    logs.clear();
    LoginDialog dialog;
    auto* account = DependencyManager::get<AccountManager>();
    auto* domain = DependencyManager::get<DomainAccountManager>();
    const QString user = "user-private-canary", password = "password-private-canary", email = "email-private-canary";
    dialog.login(user, password);
    dialog.login("blocked-or-current-user", password);
#if TEST_EXPECT_GUARD
    assert(account->calls == 1 && account->user == user && phoneLoginState.requestPending());
#else
    assert(account->calls == 2 && account->user == "blocked-or-current-user");
#endif
    assert(account->password == password);
    phoneLoginState.finishRequest();
    dialog.loginDomain(user, password);
    dialog.loginDomain("blocked-or-current-domain-user", password);
#if TEST_EXPECT_GUARD
    assert(domain->calls == 1 && domain->user == user && phoneLoginState.requestPending());
#else
    assert(domain->calls == 2 && domain->user == "blocked-or-current-domain-user");
#endif
    assert(domain->password == password);
    dialog.signup(email, user, password);
    assert(account->signups == 1 && account->receiver == &dialog);
    const auto root = QJsonDocument::fromJson(account->signup).object();
    assert(root.size() == 1);
    const auto object = root.value("user").toObject();
    assert(object.size() == 3 && object.value("email") == email && object.value("username") == user && object.value("password") == password);
    assert(logs.size() == 5);
    for (const auto& text : logs) { assert(text == "OVT_REDACTED"); }
    qInstallMessageHandler(nullptr);
}
