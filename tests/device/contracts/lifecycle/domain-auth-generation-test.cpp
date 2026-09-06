// SPDX-License-Identifier: Apache-2.0
// Complete original DomainAccountManager header/methods; real Qt network replies.
#include <QtCore/QtCore>
#include <QtNetwork/QtNetwork>
#include <cassert>
#include <cstring>
#include <memory>
#include <vector>
#include <thread>
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
    void networkFailure() { setError(QNetworkReply::RemoteHostClosedError, "private-error-canary"); }
    void stream(QByteArray data) { response = data; offset = 0; emit readyRead(); }
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
    struct OutcomeRecord { overte::network::RequestTicket ticket, context; int outcome; };
    std::vector<OutcomeRecord> outcomes;
    QObject::connect(&manager, &DomainAccountManager::loginRequestFinished,
        [&](overte::network::RequestTicket ticket, overte::network::RequestTicket context, int outcome) {
            outcomes.push_back({ ticket, context, outcome });
        });
    if (argc > 1 && QByteArray(argv[1]) == "timeout") {
        int failures = 0, successes = 0;
        QObject::connect(&manager, &DomainAccountManager::loginFailed, [&] { ++failures; });
        QObject::connect(&manager, &DomainAccountManager::loginComplete, [&] { ++successes; });
        manager.setAuthURL(QUrl("https://timeout.invalid/token"));
        const auto timeoutTicket = manager.requestAccessToken("u", "p");
        QPointer<FakeReply> pending = network.latest;
        QElapsedTimer elapsed; elapsed.start();
        QEventLoop loop;
        QObject::connect(&manager, &DomainAccountManager::loginFailed, &loop, &QEventLoop::quit);
        QTimer::singleShot(17000, &loop, &QEventLoop::quit);
        loop.exec();
        assert(failures == 1 && successes == 0 && manager.getAccessToken().isEmpty());
        assert(outcomes.size() == 1 && outcomes.back().ticket.sameRequest(timeoutTicket));
        assert(outcomes.back().outcome == static_cast<int>(DomainAccountManager::LoginOutcome::TimedOut));
        assert(!timeoutTicket.current() && outcomes.back().context.current());
        // Actual production 15s timer, not a rewritten interval or synthetic timeout.
        // Coarse Qt timers may fire slightly early; OS scheduling is not a hard bound.
        assert(elapsed.elapsed() >= 14000 && elapsed.elapsed() < 17000);
        if (pending) { assert(pending->aborts == 1); }
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        assert(!pending);
        qInstallMessageHandler(nullptr);
        return 0;
    }
    {
        DomainAccountManager visible;
        visible.setAuthURL(QUrl("https://visibility.invalid/token"));
        int completions = 0;
        overte::network::RequestTicket cancelledTicket;
        QObject::connect(&visible, &DomainAccountManager::loginRequestFinished,
            [&](overte::network::RequestTicket ticket, overte::network::RequestTicket, int outcome) {
                ++completions;
                if (outcome == static_cast<int>(DomainAccountManager::LoginOutcome::Cancelled)) cancelledTicket = ticket;
            });
        const auto ticket = visible.requestAccessToken("u", "p");
        auto* pending = network.latest;
        visible.setClientAuthVisibility(false);
        assert(!ticket.current() && !visible.isAccessTokenRequestPending());
        assert(cancelledTicket.sameRequest(ticket) && completions == 1 && pending->aborts == 1);
        assert(visible.getAccessToken().isEmpty());
        pending->finish(200, "{\"access_token\":\"late-hidden-token\"}");
        assert(visible.getAccessToken().isEmpty() && completions == 1);
        const int posts = network.posts;
        visible.requestAccessToken("hidden-u", "hidden-p");
        assert(network.posts == posts && !visible.isAccessTokenRequestPending());
        visible.setClientAuthVisibility(false); // Duplicate loss is harmless.
        visible.setClientAuthVisibility(true);
        assert(network.posts == posts); // No automatic resume/replay.
        const auto resumed = visible.requestAccessToken("new-u", "new-p");
        assert(resumed.current() && !ticket.current() && network.posts == posts + 1);
        std::thread pause([&] { visible.setClientAuthVisibility(false); });
        pause.join();
        assert(resumed.current()); // Cross-thread handoff is explicitly queued.
        QCoreApplication::processEvents();
        assert(!resumed.current() && !visible.isAccessTokenRequestPending());
        assert(cancelledTicket.sameRequest(resumed));
    }
    // Actual session-cache entry must not revive after an auth context change
    // or failed replacement sign-in. Unchanged context still reuses its token.
    for (int change = 0; change < 3; ++change) {
        DomainAccountManager cached;
        const QUrl domain("hifi://cached-private.invalid");
        const QUrl auth("https://cached-auth.invalid/token");
        cached.setDomainURL(domain); cached.setAuthURL(auth); cached.setClientID("old-client");
        cached.requestAccessToken("cached-user", "cached-password");
        network.latest->finish(200, "{\"access_token\":\"cached-token\",\"refresh_token\":\"cached-refresh\"}");
        assert(cached.isLoggedIn());
        cached.setClientID("old-client"); cached.setAuthURL(auth);
        assert(cached.getAccessToken() == "cached-token");
        cached.setDomainURL(QUrl("hifi://other-private.invalid")); cached.setDomainURL(domain);
        assert(cached.getAccessToken() == "cached-token" && cached.getRefreshToken() == "cached-refresh");
        if (change == 0) cached.setClientID("new-client");
        else if (change == 1) cached.setAuthURL(QUrl("https://new-auth.invalid/token"));
        else {
            cached.requestAccessToken("new-user", "new-password");
            network.latest->finish(401, "{}");
        }
        assert(!cached.isLoggedIn() && cached.getAccessToken().isEmpty());
        assert(cached.getRefreshToken().isEmpty() && cached.getAuthedDomainName().isEmpty());
        cached.setDomainURL(QUrl("hifi://other-private.invalid")); cached.setDomainURL(domain);
        assert(cached.getAccessToken().isEmpty() && cached.getRefreshToken().isEmpty());
        assert(!cached.isLoggedIn());
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
    const auto firstTicket = manager.requestAccessToken("user-private-canary", "password-private-canary");
    assert(firstTicket.sameRequest(manager.accessTokenRequestTicket()));
    assert(manager.isAccessTokenRequestPending());
    auto* old = network.latest;
    manager.setDomainURL(QUrl("hifi://private-b.invalid"));
    assert(!manager.isAccessTokenRequestPending());
    assert(outcomes.size() == 1 && outcomes.back().ticket.sameRequest(firstTicket));
    assert(outcomes.back().outcome == static_cast<int>(DomainAccountManager::LoginOutcome::Cancelled));
    assert(!firstTicket.current() && outcomes.back().context.current());
    assert(old->aborts == 1 && manager.getAccessToken().isEmpty() && success == 0 && tokens == 0);
    old->finish(200, "{\"access_token\":\"late-domain-private-canary\"}");
    assert(outcomes.size() == 1);
    assert(!manager.isAccessTokenRequestPending());
    assert(manager.getAccessToken().isEmpty() && success == 0);
    manager.setAuthURL(QUrl("https://auth-b.invalid/token"));
    manager.requestAccessToken("u", "p"); old = network.latest;
    manager.setAuthURL(QUrl("https://auth-b.invalid/new-token"));
    assert(!manager.isAccessTokenRequestPending());
    assert(old->aborts == 1 && success == 0 && manager.getAccessToken().isEmpty());
    manager.requestAccessToken("u", "p"); old = network.latest;
    manager.setClientID("client-b");
    assert(!manager.isAccessTokenRequestPending());
    assert(old->aborts == 1 && success == 0);
    manager.requestAccessToken("u", "p"); old = network.latest;
    const auto currentTicket = manager.requestAccessToken("current-user", "current-password");
    assert(manager.isAccessTokenRequestPending());
    assert(old->aborts == 1 && success == 0);
    assert(network.body.contains("username=current-user&password=current-password&client_id=client-b"));
    network.latest->finish(200, "{\"access_token\":\"current-token\",\"refresh_token\":\"current-refresh\"}");
    assert(!manager.isAccessTokenRequestPending());
    assert(outcomes.back().ticket.sameRequest(currentTicket) && outcomes.back().context.current());
    assert(outcomes.back().outcome == static_cast<int>(DomainAccountManager::LoginOutcome::Succeeded));
    const auto beforeDuplicate = outcomes.size();
    assert(manager.getAccessToken() == "current-token" && manager.getRefreshToken() == "current-refresh");
    assert(manager.getUsername() == "current-user" && success == 1 && tokens == 1);
    network.latest->finish(200, "{\"access_token\":\"duplicate-private-canary\"}");
    manager.requestAccessTokenFinished(); // Direct/no-sender call must be harmless.
    assert(outcomes.size() == beforeDuplicate);
    assert(manager.getAccessToken() == "current-token" && success == 1);
    manager.requestAccessToken("u", "p");
    network.latest->finish(401, "{\"error\":\"error-private-canary\",\"error_description\":\"private-target-canary\"}");
    assert(failure == 1 && manager.getAccessToken().isEmpty());
    manager.requestAccessToken("u", "p");
    network.latest->finish(200, "{}");
    assert(failure == 2 && manager.getAccessToken().isEmpty());
    // Actual form encoding and redirect policy, not a reconstructed request.
    manager.setClientID("client&scope=private +\xC3\xA4");
    manager.requestAccessToken("u+&", "p=&");
    assert(network.body == "grant_type=password&username=u%2B%26&password=p%3D%26&client_id=client%26scope%3Dprivate%20%2B%C3%A4");
    assert(network.latest->request().attribute(QNetworkRequest::RedirectPolicyAttribute).toInt() ==
           QNetworkRequest::ManualRedirectPolicy);
    assert(network.latest->readBufferSize() == 1024 * 1024 + 1);
    network.latest->finish(302, "{\"access_token\":\"redirect-private-canary\"}");
    assert(failure == 3 && success == 1 && tokens == 1 && manager.getAccessToken().isEmpty());
    const std::vector<QByteArray> invalidPayloads {
        "{", "[]", "null", "{\"access_token\":null}", "{\"access_token\":true}",
        "{\"access_token\":123}", "{\"access_token\":{}}", "{\"access_token\":[]}",
        "{\"access_token\":\"\"}", "{\"access_token\":\"  \\t\"}",
        "{\"access_token\":\"t\",\"refresh_token\":null}",
        "{\"access_token\":\"t\",\"refresh_token\":1}",
        QByteArray("{\"access_token\":\"t\",\"padding\":\"") + QByteArray(1024 * 1024, 'x') + "\"}"
    };
    for (const auto& payload : invalidPayloads) {
        const int before = failure;
        manager.requestAccessToken("u", "p");
        network.latest->finish(200, payload);
        assert(failure == before + 1 && success == 1 && tokens == 1);
        assert(manager.getAccessToken().isEmpty() && manager.getRefreshToken().isEmpty());
        network.latest->finish(200, "{\"access_token\":\"duplicate-private-canary\"}");
        assert(failure == before + 1 && success == 1);
    }
    int before = failure;
    manager.requestAccessToken("u", "p");
    network.latest->networkFailure();
    network.latest->finish(200, "{\"access_token\":\"network-error-private-canary\"}");
    assert(failure == before + 1 && success == 1 && manager.getAccessToken().isEmpty());
    before = failure;
    manager.requestAccessToken("u", "p");
    auto streaming = network.latest;
    streaming->stream(QByteArray(1024 * 1024 + 1, 'x'));
    assert(streaming->aborts == 1 && failure == before + 1 && success == 1);
    assert(outcomes.back().outcome == static_cast<int>(DomainAccountManager::LoginOutcome::ResponseRejected));
    assert(!outcomes.back().ticket.current() && outcomes.back().context.current());
    streaming->stream(QByteArray(1024 * 1024 + 1, 'x'));
    assert(streaming->aborts == 1 && failure == before + 1);
    // Inclusive boundary succeeds; optional absent/empty refresh token remains supported.
    manager.requestAccessToken("u", "p");
    QByteArray exact("{\"access_token\":\"boundary-token\",\"refresh_token\":\"\",\"padding\":\"");
    exact += QByteArray(1024 * 1024 - exact.size() - 2, 'x'); exact += "\"}";
    assert(exact.size() == 1024 * 1024);
    network.latest->finish(200, exact);
    assert(success == 2 && tokens == 2 && manager.getAccessToken() == "boundary-token");
    assert(manager.getRefreshToken().isEmpty());
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
