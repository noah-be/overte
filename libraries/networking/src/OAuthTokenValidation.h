// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <QtCore/QJsonObject>
#include <QtCore/QString>

namespace overte { namespace network {

// The client emits Bearer headers. Reject unsupported token types and bytes
// that cannot occur in a Bearer credential, instead of silently relabelling them.
inline bool validBearerCredential(const QString& value) {
    if (value.isEmpty()) { return false; }
    bool padding = false;
    bool content = false;
    for (const auto character : value) {
        const auto c = character.unicode();
        if (c == '=') { padding = true; continue; }
        if (padding || !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                         (c >= '0' && c <= '9') || c == '-' || c == '.' ||
                         c == '_' || c == '~' || c == '+' || c == '/')) {
            return false;
        }
        content = true;
    }
    return content;
}

inline bool validOAuthTokenResponse(const QJsonObject& object) {
    const auto access = object.value("access_token");
    const auto type = object.value("token_type");
    const auto expiry = object.value("expires_in");
    const auto refresh = object.value("refresh_token");
    if (object.contains("error") || !access.isString() || !validBearerCredential(access.toString()) ||
            !type.isString() || type.toString().compare(QStringLiteral("Bearer"), Qt::CaseInsensitive) != 0 ||
            !expiry.isDouble() || expiry.toInt(-1) <= 0 ||
            (!refresh.isUndefined() && !refresh.isString())) {
        return false;
    }
    // Refresh tokens are form-encoded, not Bearer headers. Permit visible ASCII
    // including spaces; do not apply the access-token grammar to opaque refresh.
    for (const auto character : refresh.toString()) {
        if (character.unicode() < 0x20 || character.unicode() > 0x7e) { return false; }
    }
    return true;
}

}} // namespace overte::network
