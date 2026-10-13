// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../web/IOSWebDocumentEpoch.h"
#include <cassert>

int main() {
    using namespace overte;
    web::EmbeddedWebSession policy;
    ios::IOSWebDocumentEpoch document;
    const QUrl source("https://example.invalid/app");
    auto generation = policy.open(source, web::Surface::Tablet, QStringLiteral("tablet-test"));
    auto allowed = [&](const QString& nonce, const QUrl& frame, bool main = true) {
        return document.accepts(generation, nonce, frame, main) &&
            policy.allowsBridge(generation, frame, main, 128);
    };
    assert(document.begin(generation, source, QStringLiteral("document-one")));
    assert(allowed(QStringLiteral("document-one"), source));
    const auto epoch = document.epoch();
    assert(ios::IOSWebDocumentEpoch::isFragmentNavigation(source, QUrl("https://example.invalid/app#section")));
    assert(!ios::IOSWebDocumentEpoch::isFragmentNavigation(source, source)); // Reload is a new document.
    assert(!ios::IOSWebDocumentEpoch::isFragmentNavigation(source, QUrl("https://example.invalid/app?q=new#section")));
    assert(!ios::IOSWebDocumentEpoch::isFragmentNavigation(QUrl(), source));
    assert(allowed(QStringLiteral("document-one"), QUrl("https://example.invalid/app#section")));
    assert(document.epoch() == epoch); // Same-document links retain transport authority.

    // Same-origin reload begins a different native document under unchanged
    // source authority. An old queued init cannot initialize the new channel.
    assert(document.begin(generation, source, QStringLiteral("document-two")));
    assert(document.epoch() > epoch);
    assert(!allowed(QStringLiteral("document-one"), source));
    assert(allowed(QStringLiteral("document-two"), source));
    const QUrl redirect("https://example.invalid/redirected");
    document.redirected(redirect);
    assert(allowed(QStringLiteral("document-two"), redirect));
    assert(!allowed(QStringLiteral("document-one"), redirect));
    assert(!allowed(QStringLiteral("document-two"), redirect, false));

    // Foreign HTML may browse normally but does not receive source EventBridge.
    const QUrl foreign("https://other.invalid/page");
    assert(policy.allowsNavigation(generation, foreign, true, QStringLiteral("GET")));
    assert(document.begin(generation, foreign, QStringLiteral("foreign-document")));
    assert(!allowed(QStringLiteral("foreign-document"), foreign));
    // A cached Back document still has its obsolete transport nonce. Permit
    // one real reload of the current history item, never an unbounded loop or
    // an old asynchronous verification completing against the replacement.
    using Verification = ios::IOSWebDocumentEpoch::Verification;
    const auto cachedEpoch = document.epoch();
    assert(document.verify(generation, cachedEpoch, false) == Verification::Reload);
    assert(document.begin(generation, source, QStringLiteral("fresh-back-document")));
    assert(document.verify(generation, cachedEpoch, true) == Verification::Stale);
    assert(document.verify(generation, document.epoch(), false) == Verification::Failed);
    document.resetRecovery();
    assert(document.verify(generation, document.epoch(), false) == Verification::Reload);
    assert(document.verify(generation, document.epoch(), true) == Verification::Ready);
    assert(!allowed(QStringLiteral("document-two"), redirect));
    // Back restores the original origin with a fresh native document identity.
    assert(document.begin(generation, source, QStringLiteral("back-document")));
    assert(allowed(QStringLiteral("back-document"), source));
    assert(!allowed(QStringLiteral("foreign-document"), foreign));

    policy.setForeground(false);
    document.invalidate();
    assert(!allowed(QStringLiteral("fresh-back-document"), source));
    policy.setForeground(true);
    generation = policy.open(source, web::Surface::WorldEntity, QStringLiteral("entity-test"));
    assert(!allowed(QStringLiteral("back-document"), source));
    assert(document.begin(generation, source, QStringLiteral("replacement-document")));
    assert(allowed(QStringLiteral("replacement-document"), source));
    policy.close(); document.invalidate();
    assert(!allowed(QStringLiteral("replacement-document"), source));
    assert(!document.begin(0, source, QStringLiteral("invalid")));
    assert(!document.begin(generation, source, QString()));
}
