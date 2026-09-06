// SPDX-License-Identifier: Apache-2.0
// Complete original DomainAccountManager header/methods; real Qt network replies.
#include <QtCore/QtCore>
#include <QtNetwork/QtNetwork>
#include <cassert>
#include <cstring>
#include <memory>
#include <vector>
#include "libraries/networking/src/DomainAccountManager.h"
#include "security/redaction/SafeDiagnostics.h"
Q_LOGGING_CATEGORY(networking, "overte.test.domain-auth")
namespace NetworkingConstants { const char* OVERTE_USER_AGENT = "contract-test"; }
struct Handler { QString getHostname() { return "domain-host-private-canary"; } };
struct NodeList { Handler handler; Handler& getDomainHandler() { return handler; } };
struct FakeReply : QNetworkReply {
    QByteArray response; qint64 offset {}; int aborts {};
    FakeReply(const QNetworkRequest& request, QObject* parent) : QNetworkReply(parent) {
        setRequest(request); setUrl(request.url()); open(QIODevice::ReadOnly | QIODevice::Unbuffered);
    }
    void finish(int status, QByteArray data) {
        response = data; offset = 0;
        setAttribute(QNetworkRequest::HttpStatusCodeAttribute, status);
        setFinished(true); emit finished();
    }
    void abort() override {
        ++aborts;
        // Deliberately race an apparently successful response with cancellation.
        finish(200, "{\"access_token\":\"aborted-token-private-canary\"}");
    }
    qint64 bytesAvailable() const override { return response.size() - offset + QNetworkReply::bytesAvailable(); }
    qint64 readData(char* output, qint64 maximum) override {
        const auto count = qMin(maximum, qint64(response.size()) - offset);
        if (!count) { return -1; }
        std::memcpy(output, response.constData() + offset, size_t(count)); offset += count; return count;
    }
};
struct NetworkAccessManager : QNetworkAccessManager {
    FakeReply* latest {}; QByteArray body; int posts {};
    static NetworkAccessManager& getInstance() { static NetworkAccessManager instance; return instance; }
    QNetworkReply* createRequest(Operation operation, const QNetworkRequest& request, QIODevice* data) override {
        assert(operation == PostOperation); ++posts; body = data->readAll();
        latest = new FakeReply(request, this); return latest;
    }
};
#include "domain-methods.inc"
static std::vector<QString> logs;
static void capture(QtMsgType, const QMessageLogContext&, const QString& value) { logs.push_back(value); }
static void waitTimers() { QEventLoop loop; QTimer::singleShot(550, &loop, &QEventLoop::quit); loop.exec(); }
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    qInstallMessageHandler(capture);
    auto& network = NetworkAccessManager::getInstance();
    DomainAccountManager manager;
    if (argc > 1 && QByteArray(argv[1]) == "timeout") {
        int failures = 0, successes = 0;
        QObject::connect(&manager, &DomainAccountManager::loginFailed, [&] { ++failures; });
        QObject::connect(&manager, &DomainAccountManager::loginComplete, [&] { ++successes; });
        manager.setAuthURL(QUrl("https://timeout.invalid/token"));
        manager.requestAccessToken("u", "p");
        QPointer<FakeReply> pending = network.latest;
        QElapsedTimer elapsed; elapsed.start();
        QEventLoop loop;
        QObject::connect(&manager, &DomainAccountManager::loginFailed, &loop, &QEventLoop::quit);
        QTimer::singleShot(17000, &loop, &QEventLoop::quit);
        loop.exec();
        assert(failures == 1 && successes == 0 && manager.getAccessToken().isEmpty());
        // Actual production 15s timer, not a rewritten interval or synthetic timeout.
        // Coarse Qt timers may fire slightly early; OS scheduling is not a hard bound.
        assert(elapsed.elapsed() >= 14000 && elapsed.elapsed() < 17000);
        if (pending) { assert(pending->aborts == 1); }
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        assert(!pending);
        qInstallMessageHandler(nullptr);
        return 0;
    }
    int success = 0, failure = 0, tokens = 0, prompts = 0;
    QObject::connect(&manager, &DomainAccountManager::loginComplete, [&] { ++success; });
    QObject::connect(&manager, &DomainAccountManager::loginFailed, [&] { ++failure; });
    QObject::connect(&manager, &DomainAccountManager::newTokens, [&] { ++tokens; });
    QObject::connect(&manager, &DomainAccountManager::authRequired, [&](const QString& domain) {
        assert(domain == "auth-b.invalid"); ++prompts;
    });
    manager.setDomainURL(QUrl("hifi://private-a.invalid"));
    manager.setAuthURL(QUrl("https://auth-a.invalid/token"));
    manager.setClientID("client-a");
    manager.requestAccessToken("user-private-canary", "password-private-canary");
    auto* old = network.latest;
    manager.setDomainURL(QUrl("hifi://private-b.invalid"));
    assert(old->aborts == 1 && manager.getAccessToken().isEmpty() && success == 0 && tokens == 0);
    old->finish(200, "{\"access_token\":\"late-domain-private-canary\"}");
    assert(manager.getAccessToken().isEmpty() && success == 0);
    manager.setAuthURL(QUrl("https://auth-b.invalid/token"));
    manager.requestAccessToken("u", "p"); old = network.latest;
    manager.setAuthURL(QUrl("https://auth-b.invalid/new-token"));
    assert(old->aborts == 1 && success == 0 && manager.getAccessToken().isEmpty());
    manager.requestAccessToken("u", "p"); old = network.latest;
    manager.setClientID("client-b");
    assert(old->aborts == 1 && success == 0);
    manager.requestAccessToken("u", "p"); old = network.latest;
    manager.requestAccessToken("current-user", "current-password");
    assert(old->aborts == 1 && success == 0);
    assert(network.body.contains("username=current-user&password=current-password&client_id=client-b"));
    network.latest->finish(200, "{\"access_token\":\"current-token\",\"refresh_token\":\"current-refresh\"}");
    assert(manager.getAccessToken() == "current-token" && manager.getRefreshToken() == "current-refresh");
    assert(manager.getUsername() == "current-user" && success == 1 && tokens == 1);
    network.latest->finish(200, "{\"access_token\":\"duplicate-private-canary\"}");
    manager.requestAccessTokenFinished(); // Direct/no-sender call must be harmless.
    assert(manager.getAccessToken() == "current-token" && success == 1);
    manager.requestAccessToken("u", "p");
    network.latest->finish(401, "{\"error\":\"error-private-canary\",\"error_description\":\"private-target-canary\"}");
    assert(failure == 1 && manager.getAccessToken().isEmpty());
    manager.requestAccessToken("u", "p");
    network.latest->finish(200, "{}");
    assert(failure == 2 && manager.getAccessToken().isEmpty());
    manager.checkAndSignalForAccessToken();
    manager.setClientID("client-c"); // Cancel the old delayed dialog.
    waitTimers(); assert(prompts == 0);
    manager.checkAndSignalForAccessToken();
    waitTimers(); assert(prompts == 1);
    auto dying = std::make_unique<DomainAccountManager>();
    dying->setAuthURL(QUrl("https://auth-b.invalid/token"));
    dying->requestAccessToken("u", "p");
    QPointer<FakeReply> pending = network.latest;
    dying.reset();
    assert(pending && pending->aborts == 1);
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    assert(!pending);
    for (const auto& message : logs) {
        assert(message == "OVT_REDACTED" || message == "OVT_AUTH_FAILED");
    }
    qInstallMessageHandler(nullptr);
}
