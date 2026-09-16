// Test-only boundary: the real Qt AccountManager requires the deferred full build.
#pragma once
#include "../../../../../security/storage/ProtectedAccountStore.h"
std::shared_ptr<overte::security::ProtectedAccountStore>& registeredPhoneStore();
class AccountManager {
public:
    static bool installProtectedAccountStore(std::shared_ptr<overte::security::ProtectedAccountStore> store) {
        auto& registered = registeredPhoneStore();
        if (!store || registered) { return false; }
        registered = std::move(store);
        return true;
    }
};
