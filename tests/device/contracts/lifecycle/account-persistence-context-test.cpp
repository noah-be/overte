#include <QtCore/QCoreApplication>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QLoggingCategory>
#include <QtCore/QPointer>
#include "libraries/networking/src/RequestCancellation.h"
#include "security/redaction/SafeDiagnostics.h"
#include <cassert>
#include <cstring>

Q_LOGGING_CATEGORY(networking, "overte.test.persistence-context")
struct DataServerAccountInfo {
    QJsonObject tokens;
    void setAccessTokenFromJSON(const QJsonObject& value) { tokens = value; }
};
Q_DECLARE_METATYPE(DataServerAccountInfo)
// Only the protected-storage I/O, data representation, profile and preference
// boundaries are test doubles. All four production method bodies are original.
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
    bool _isWaitingForAccessToken = false;
    QString getMetaverseServerURLPath() { return "/api"; }
    void persistAccountToFile();
    bool setAccessTokens(const QString& response);
    void requestAccessTokenFinished();
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
struct Reply : QNetworkReply {
    QByteArray payload; qint64 offset = 0;
    explicit Reply(const QString& text) : payload(text.toUtf8()) {
        setUrl(QUrl("https://private-test.invalid/api/oauth/token"));
        setAttribute(QNetworkRequest::HttpStatusCodeAttribute, 200);
        open(QIODevice::ReadOnly | QIODevice::Unbuffered);
    }
    void abort() override {}
    void finish() { setFinished(true); emit finished(); }
    qint64 readData(char* out, qint64 maximum) override {
        const auto count = qMin(maximum, qint64(payload.size()) - offset);
        if (!count) return -1;
        std::memcpy(out, payload.constData() + offset, size_t(count)); offset += count;
        return count;
    }
};
#include "persistence.inc"
#include "persistence.moc"

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    Application caller;
    const QString good = "{\"access_token\":\"token-canary\",\"expires_in\":3600,\"token_type\":\"Bearer\"}";
    for (bool network : {false, true}) {
    for (int failure = 0; failure < 3; ++failure) {
        AccountManager manager; selected = &manager;
        readable = failure != 1; writable = failure != 2;
        writes = saved = profiles = kept = 0;
        manager._isWaitingForTokenRefresh = true;
        const auto old = manager._credentialContext.snapshot();
        int required = 0, success = 0;
        QObject::connect(&manager, &AccountManager::loginComplete, [&] {
            ++success;
            assert(readable && writable && writes >= 1); // No success before confirmed I/O.
        });
        QObject::connect(&manager, &AccountManager::authRequired, [&] {
            ++required;
            assert(!old.current()); // Fence before outward/reentrant re-auth signal.
            assert(!manager._isWaitingForTokenRefresh);
            assert(manager._accountInfo.tokens.isEmpty());
        });
        if (network) {
            QPointer<Reply> reply = new Reply(good);
            QObject::connect(reply.data(), &QNetworkReply::finished, &manager, &AccountManager::requestAccessTokenFinished);
            reply->finish();
            QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
            assert(!reply);
        } else {
            caller.forceLoginWithTokens(good);
        }
        assert(writes == int(readable));
        assert(required == int(failure != 0));
        assert(success == int(failure == 0));
        assert(saved == int(!network && failure == 0) && profiles == int(failure == 0) && kept == int(!network && failure == 0));
        // A valid direct import is itself a new credential intent; network
        // completion retains the already established request's context.
        assert(old.current() == (network && failure == 0));
        if (failure) {
            readable = writable = true;
            assert(manager.setAccessTokens(good)); // Recovery is not permanently disabled.
            assert(saved == 1 && profiles == 1);
        }
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
