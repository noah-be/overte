// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "SecureAccountStore.h"

#import <Foundation/Foundation.h>
#import <LocalAuthentication/LocalAuthentication.h>
#import <Security/Security.h>

#include <mutex>

namespace overte::ios {
namespace {
std::mutex storeMutex;

SecureStoreStatus statusFor(OSStatus status) {
    switch (status) {
        case errSecSuccess: return SecureStoreStatus::Ok;
        case errSecItemNotFound: return SecureStoreStatus::NotFound;
        case errSecInteractionNotAllowed: return SecureStoreStatus::Locked;
        case errSecNotAvailable: return SecureStoreStatus::Unavailable;
        case errSecDecode: return SecureStoreStatus::Corrupt;
        case errSecParam: return SecureStoreStatus::Invalid;
        default: return SecureStoreStatus::Failed;
    }
}

NSMutableDictionary* queryFor(std::string_view key) {
    if (!SecureAccountStore::validKey(key)) {
        return nil;
    }
    NSString* bundle = NSBundle.mainBundle.bundleIdentifier;
    if (bundle.length == 0) {
        return nil;
    }
    NSString* account = [[NSString alloc] initWithBytes:key.data() length:key.size()
                                              encoding:NSASCIIStringEncoding];
    LAContext* context = [[LAContext alloc] init];
    context.interactionNotAllowed = YES;
    return [@{
        (__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword,
        (__bridge id)kSecAttrService: [bundle stringByAppendingString:@".protected-accounts.v1"],
        (__bridge id)kSecAttrAccount: account,
        (__bridge id)kSecAttrSynchronizable: @NO,
        (__bridge id)kSecUseAuthenticationContext: context
    } mutableCopy];
}
}

SecureStoreStatus SecureAccountStore::read(std::string_view key, std::vector<std::uint8_t>& value) {
    clear(value);
    std::lock_guard guard(storeMutex);
    @autoreleasepool {
      @try {
        NSMutableDictionary* query = queryFor(key);
        if (query == nil) { return SecureStoreStatus::Invalid; }
        query[(__bridge id)kSecReturnData] = @YES;
        query[(__bridge id)kSecMatchLimit] = (__bridge id)kSecMatchLimitOne;
        CFTypeRef item = nullptr;
        const auto status = SecItemCopyMatching((__bridge CFDictionaryRef)query, &item);
        if (status != errSecSuccess) {
            if (item != nullptr) { CFRelease(item); }
            return statusFor(status);
        }
        if (item == nullptr || CFGetTypeID(item) != CFDataGetTypeID()) {
            if (item != nullptr) { CFRelease(item); }
            return SecureStoreStatus::Corrupt;
        }
        NSData* data = CFBridgingRelease(item);
        if (data.length == 0 || data.length > MAX_VALUE_BYTES) {
            return SecureStoreStatus::Corrupt;
        }
        const auto bytes = static_cast<const std::uint8_t*>(data.bytes);
        value.assign(bytes, bytes + data.length);
        return SecureStoreStatus::Ok;
      } @catch (NSException*) {
        clear(value);
        return SecureStoreStatus::Failed;
      }
    }
}

SecureStoreStatus SecureAccountStore::write(std::string_view key, const std::vector<std::uint8_t>& value) {
    if (value.empty() || value.size() > MAX_VALUE_BYTES) { return SecureStoreStatus::Invalid; }
    std::lock_guard guard(storeMutex);
    @autoreleasepool {
      @try {
        NSMutableDictionary* query = queryFor(key);
        if (query == nil) { return SecureStoreStatus::Invalid; }
        NSData* data = [NSData dataWithBytes:value.data() length:value.size()];
        NSDictionary* attributes = @{
            (__bridge id)kSecValueData: data,
            (__bridge id)kSecAttrAccessible: (__bridge id)kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        };
        OSStatus status = SecItemUpdate((__bridge CFDictionaryRef)query, (__bridge CFDictionaryRef)attributes);
        if (status == errSecItemNotFound) {
            NSMutableDictionary* insertion = [query mutableCopy];
            [insertion addEntriesFromDictionary:attributes];
            status = SecItemAdd((__bridge CFDictionaryRef)insertion, nullptr);
            // Another process can race our insert. One update retry, no loop.
            if (status == errSecDuplicateItem) {
                status = SecItemUpdate((__bridge CFDictionaryRef)query, (__bridge CFDictionaryRef)attributes);
            }
        }
        return statusFor(status);
      } @catch (NSException*) {
        return SecureStoreStatus::Failed;
      }
    }
}

SecureStoreStatus SecureAccountStore::remove(std::string_view key) {
    std::lock_guard guard(storeMutex);
    @autoreleasepool {
      @try {
        NSMutableDictionary* query = queryFor(key);
        if (query == nil) { return SecureStoreStatus::Invalid; }
        const auto status = SecItemDelete((__bridge CFDictionaryRef)query);
        // Removing an absent item is idempotent. Locked/error is never success.
        return status == errSecItemNotFound ? SecureStoreStatus::Ok : statusFor(status);
      } @catch (NSException*) {
        return SecureStoreStatus::Failed;
      }
    }
}
} // namespace overte::ios
