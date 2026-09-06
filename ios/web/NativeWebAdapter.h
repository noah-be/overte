// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../../interface/src/NativeWebPolicy.h"
#include <optional>

namespace overte::ios {
// HTML input/autofill cannot be made safe merely by CSS. Until a reviewed
// native enforcement hook is available, only noninteractive text is admitted.
bool acceptsNativeWebMime(const QString& mime);
// UIKit boundary only; URL/origin semantics remain in the original Shared owner.
class NativeWebOperations {
public:
    virtual ~NativeWebOperations() = default;
    virtual bool confirmation(const web::Request&) noexcept = 0;
    virtual bool dismiss(std::uint64_t) noexcept = 0;
};

class NativeWebAdapter final : public web::Adapter {
public:
    explicit NativeWebAdapter(NativeWebOperations& operations) : _operations(operations) {}
    bool present(const web::Request&) noexcept override;
    void dismiss(std::uint64_t ticket) noexcept override;
    bool confirm(std::uint64_t ticket);
    bool mayNavigate(std::uint64_t ticket, const QString& destination) const;
    void close(std::uint64_t ticket);
private:
    NativeWebOperations& _operations;
    std::optional<web::Request> _request;
    bool _confirmed { false };
    bool _nativeCleanupFailed { false };
};
} // namespace overte::ios
