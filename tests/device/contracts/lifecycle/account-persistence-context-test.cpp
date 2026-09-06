#include <QtCore/QCoreApplication>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QLoggingCategory>
#include <QtCore/QPointer>
#include "libraries/networking/src/RequestCancellation.h"
#include "security/redaction/SafeDiagnostics.h"
#include <cassert>

Q_LOGGING_CATEGORY(networking, "overte.test.persistence-context")
struct DataServerAccountInfo {
    QJsonObject tokens;
    void setAccessTokenFromJSON(const QJsonObject& value) { tokens = value; }
};
Q_DECLARE_METATYPE(DataServerAccountInfo)
// Only the protected-storage I/O, data representation, profile and preference
// boundaries are test doubles. All three production method bodies are original.
static bool readable = true, writable = true;
static int writes = 0, saved = 0, profiles = 0, kept = 0;
QVariantMap accountMapFromFile(bool& loaded) { loaded = readable; return {}; }
bool writeAccountMapToFile(const QVariantMap& map) {
    ++writes;
    assert(map.size() == 1);
    assert(map.begin().value().value<DataServerAccountInfo>().tokens.contains("access_token"));
    return writable;
}
class AccountManager : public QObject {
    Q_OBJECT
public:
    overte::network::RequestScope _credentialContext;
    DataServerAccountInfo _accountInfo;
    QUrl _authURL { "https://private-test.invalid" };
    bool _isWaitingForTokenRefresh = false;
    QString getMetaverseServerURLPath() { return "/api"; }
    void persistAccountToFile();
    bool setAccessTokens(const QString& response);
    void saveLoginStatus(bool value) { assert(value); ++saved; }
    void requestProfile() { ++profiles; }
signals:
    void loginComplete(QUrl);
    void loginFailed();
    void authRequired();
};
static AccountManager* selected = nullptr;
struct DependencyManager { template<class T> static T* get() { return selected; } };
const char* KEEP_ME_LOGGED_IN_SETTING_NAME = "test-keep-login";
namespace Setting { template<class T> struct Handle {
    Handle(const char*, bool) {}
    void set(bool value) { assert(value); ++kept; }
}; }
struct Application { void forceLoginWithTokens(const QString&); };
#include "persistence.inc"
#include "persistence.moc"

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    Application caller;
    const QString good = "{\"access_token\":\"token-canary\",\"expires_in\":3600,\"token_type\":\"Bearer\"}";
    for (int failure = 0; failure < 3; ++failure) {
        AccountManager manager; selected = &manager;
        readable = failure != 1; writable = failure != 2;
        writes = saved = profiles = kept = 0;
        manager._isWaitingForTokenRefresh = true;
        const auto old = manager._credentialContext.snapshot();
        int required = 0;
        QObject::connect(&manager, &AccountManager::authRequired, [&] {
            ++required;
            assert(!old.current()); // Fence before outward/reentrant re-auth signal.
            assert(!manager._isWaitingForTokenRefresh);
            assert(manager._accountInfo.tokens.isEmpty());
        });
        caller.forceLoginWithTokens(good);
        assert(writes == int(readable));
        assert(required == int(failure != 0));
        assert(saved == int(failure == 0) && profiles == int(failure == 0) && kept == int(failure == 0));
        assert(old.current() == (failure == 0));
        if (failure) {
            readable = writable = true;
            assert(manager.setAccessTokens(good)); // Recovery is not permanently disabled.
            assert(saved == 1 && profiles == 1);
        }
    }
    for (bool destroy : {false, true}) {
        QPointer<AccountManager> manager = new AccountManager; selected = manager;
        readable = true; writable = false;
        writes = saved = profiles = kept = 0;
        QObject::connect(manager.data(), &AccountManager::authRequired, [&] {
            if (destroy) {
                delete manager.data();
            } else {
                writable = true;
                caller.forceLoginWithTokens(good); // Reentrant replacement succeeds once.
            }
        });
        caller.forceLoginWithTokens(good);
        assert(saved == int(!destroy) && profiles == int(!destroy) && kept == int(!destroy));
        if (manager) delete manager.data();
    }
}
