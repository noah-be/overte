// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QString>
#include <QUrl>
#include <cstdint>

namespace overte { namespace web {
struct Request {
    std::uint64_t ticket;
    QUrl url;       // Private runtime input, never a diagnostic/export field.
    QString origin;
};
class Adapter {
public:
    virtual ~Adapter() = default;
    // Must first show native origin confirmation with equal Cancel, before
    // loading any page. True means presentation accepted, not navigation PASS.
    virtual bool present(const Request&) noexcept = 0;
    virtual void dismiss(std::uint64_t ticket) noexcept = 0;
};

// GUI-thread-confined policy used by the actual process owner below. Separate
// instances exist only in host tests; native consumers MUST use global APIs.
class Session {
public:
    bool install(Adapter* adapter);
    void visible(bool value);
    std::uint64_t open(const QString& input);
    bool allows(std::uint64_t ticket, const QString& destination) const;
    void close(std::uint64_t ticket);
private:
    void invalidate();
    Adapter* _adapter { nullptr }; // Process-lived native adapter, no replacement.
    std::uint64_t _generation { 0 };
    bool _visible { false }, _active { false }, _dispatching { false };
    QString _origin;
};

// Register once on the actual QGuiApplication thread after its construction.
// All calls from a different thread fail closed without touching session state.
bool installNativeWebAdapter(Adapter* adapter);
std::uint64_t openNativeWeb(const QString& input);
bool nativeWebMayNavigate(std::uint64_t ticket, const QString& destination);
void closeNativeWeb(std::uint64_t ticket);
} }
