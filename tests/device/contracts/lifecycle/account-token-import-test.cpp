#include <QtCore/QCoreApplication>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QLoggingCategory>
#include <QtCore/QPointer>
#include "libraries/networking/src/RequestCancellation.h"
#include "security/redaction/SafeDiagnostics.h"
#include <cassert>
#include <functional>

Q_LOGGING_CATEGORY(networking, "overte.test.token-import")
struct DataServerAccountInfo {
    QJsonObject tokens;
    void setAccessTokenFromJSON(const QJsonObject& value) { tokens = value; }
};
// Storage/profile/Setting and dependency lookup are declared boundaries, not
// evidence that a native key store or actual configuration file was written.
static int persisted = 0, saved = 0, profiles = 0, kept = 0;
class AccountManager : public QObject {
    Q_OBJECT
public:
    overte::network::RequestScope _credentialContext;
    DataServerAccountInfo _accountInfo;
    QUrl _authURL { "https://private-test.invalid" };
    std::function<void()> onPersist, onSave, onProfile;
    QString getMetaverseServerURLPath() { return "/api"; }
    void persistAccountToFile() { ++persisted; if (onPersist) { auto action = std::move(onPersist); onPersist = {}; action(); } }
    void saveLoginStatus(bool value) { assert(value); ++saved; if (onSave) { auto action = std::move(onSave); onSave = {}; action(); } }
    void requestProfile() { ++profiles; if (onProfile) { auto action = std::move(onProfile); onProfile = {}; action(); } }
#include "token-return.inc"
    setAccessTokens(const QString& response);
signals:
    void loginComplete(QUrl);
    void loginFailed();
};
static AccountManager* selected = nullptr;
struct DependencyManager { template<class T> static T* get() { return selected; } };
const char* KEEP_ME_LOGGED_IN_SETTING_NAME = "test-keep-login";
namespace Setting { template<class T> struct Handle {
    Handle(const char*, bool) {}
    void set(bool value) { assert(value); ++kept; }
}; }
struct Application { void forceLoginWithTokens(const QString&); };
#include "token-import.inc"
#include "token-import.moc"

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    Application caller;
    const QJsonObject good {{"access_token", "token-canary"}, {"expires_in", 3600}, {"token_type", "Bearer"}};
    auto check = [&](const QString& input, bool accepted) {
        AccountManager manager; selected = &manager;
        manager._accountInfo.tokens.insert("prior", true);
        persisted = saved = profiles = kept = 0;
        int success = 0, failure = 0;
        QObject::connect(&manager, &AccountManager::loginComplete, [&](const QUrl& url) { ++success; assert(url.path() == "/api"); });
        QObject::connect(&manager, &AccountManager::loginFailed, [&] { ++failure; });
        caller.forceLoginWithTokens(input);
        assert(success == int(accepted) && failure == int(!accepted));
        assert(persisted == int(accepted) && saved == int(accepted) && profiles == int(accepted) && kept == int(accepted));
        assert(accepted ? manager._accountInfo.tokens.value("access_token") == "token-canary" : manager._accountInfo.tokens.value("prior").toBool());
    };
    for (const auto& input : {QString("{}"), QString("{"), QString("[]"), QString("null"),
                             QString("{\"error\":\"private-error-canary\"}")}) check(input, false);
    check(QString::fromUtf8(QJsonDocument(good).toJson()), true);
    for (const auto& key : {QString("access_token"), QString("token_type"), QString("refresh_token")}) {
        for (const auto& invalid : {QJsonValue(), QJsonValue(false), QJsonValue(12), QJsonValue(QJsonObject())}) {
            auto object = good; object.insert(key, invalid); check(QString::fromUtf8(QJsonDocument(object).toJson()), false);
        }
    }
    for (const auto& key : {QString("access_token"), QString("token_type")}) {
        auto object = good; object.insert(key, ""); check(QString::fromUtf8(QJsonDocument(object).toJson()), false);
    }
    for (const auto& invalid : {QJsonValue("3600"), QJsonValue(0), QJsonValue(-1), QJsonValue(0.5), QJsonValue(2147483648.0)}) {
        auto object = good; object.insert("expires_in", invalid); check(QString::fromUtf8(QJsonDocument(object).toJson()), false);
    }
    auto valid = good; valid.insert("expires_in", 2147483647); valid.insert("refresh_token", "");
    check(QString::fromUtf8(QJsonDocument(valid).toJson()), true);
    QString exact = QString::fromUtf8(QJsonDocument(good).toJson(QJsonDocument::Compact));
    exact += QString(1024 * 1024 - exact.size(), ' ');
    check(exact, true); check(exact + ' ', false);
    auto unicode = good; unicode.insert("padding", QString(400000, QChar(0x20ac)));
    check(QString::fromUtf8(QJsonDocument(unicode).toJson()), false); // UTF8 exceeds cap despite fewer UTF16 code units.
    for (int stage = 0; stage < 4; ++stage) {
        for (bool destroy : {false, true}) {
            QPointer<AccountManager> manager = new AccountManager; selected = manager;
            persisted = saved = profiles = kept = 0;
            auto invalidate = [&] { if (destroy) delete manager.data(); else manager->_credentialContext.next(); };
            if (stage == 0) manager->onPersist = invalidate;
            else if (stage == 1) QObject::connect(manager.data(), &AccountManager::loginComplete, invalidate);
            else if (stage == 2) manager->onSave = invalidate;
            else manager->onProfile = invalidate;
            caller.forceLoginWithTokens(QString::fromUtf8(QJsonDocument(good).toJson()));
            assert(persisted == 1 && saved == int(stage >= 2) && profiles == int(stage >= 3) && kept == 0);
            if (manager) delete manager.data();
        }
    }
}
