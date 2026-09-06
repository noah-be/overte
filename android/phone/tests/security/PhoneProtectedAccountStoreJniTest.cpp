// SPDX-License-Identifier: Apache-2.0
#include "../../apps/phoneInterface/src/PhoneProtectedAccountStore.h"
#include <thread>
#include <stdexcept>

using namespace overte::security;
std::shared_ptr<ProtectedAccountStore>& registeredPhoneStore() {
    static std::shared_ptr<ProtectedAccountStore> store;
    return store;
}

extern "C" JNIEXPORT jint JNICALL
Java_org_overte_phone_SecureAccountStoreJniFixture_run(JNIEnv* env, jclass fixture) {
    int checks = 0;
    auto require = [&checks](bool condition) {
        ++checks;
        if (!condition) { throw std::runtime_error("protected storage JNI assertion"); }
    };
    try {
        auto store = registeredPhoneStore();
        require(bool(store)); // Exact production JNI_OnLoad registration ran.
        auto mode = env->GetStaticMethodID(fixture, "fault", "(I)V");
        require(mode && !env->ExceptionCheck());
        auto fault = [&](int kind) {
            env->CallStaticVoidMethod(fixture, mode, kind);
            require(!env->ExceptionCheck());
        };
        AccountBytes value { 1, 9, 3, 7 }, output { 99 };
        require(store->read(output) == StoreResult::Absent && output.empty());
        require(store->write({}) == StoreResult::Corrupt);
        require(store->write(AccountBytes(MAX_ACCOUNT_BYTES + 1)) == StoreResult::Corrupt);
        require(store->write(value) == StoreResult::Ok);
        require(store->read(output) == StoreResult::Ok && output == value);
        StoreResult workerResult = StoreResult::Unavailable;
        AccountBytes workerOutput;
        std::thread worker([&] { workerResult = store->read(workerOutput); });
        worker.join();
        require(workerResult == StoreResult::Ok && workerOutput == value);
        fault(1);
        require(store->read(output) == StoreResult::Unavailable && output.empty());
        require(store->write(value) == StoreResult::Unavailable);
        fault(2);
        require(store->read(output) == StoreResult::Corrupt && output.empty());
        require(store->write(value) == StoreResult::Corrupt);
        require(store->erase() == StoreResult::Ok);
        require(store->write(value) == StoreResult::Ok);
        fault(4);
        require(store->read(output) == StoreResult::Corrupt && output.empty());
        fault(5);
        require(store->read(output) == StoreResult::IoError && output.empty());
        require(store->write(value) == StoreResult::IoError);
        fault(6);
        require(store->write(value) == StoreResult::Ok);
        fault(3);
        require(store->erase() == StoreResult::IoError);
        require(store->read(output) == StoreResult::Absent && output.empty());
        fault(0);
        require(store->erase() == StoreResult::Ok);

        AccountStoreCoordinator coordinator;
        require(coordinator.install(store));
        bool legacyExists = true;
        int legacyReads = 0, legacyErases = 0;
        bool eraseAllowed = true;
        LegacyAccountInput legacy {
            [&](AccountBytes& bytes) { ++legacyReads; bytes = value; return StoreResult::Ok; },
            [&] { ++legacyErases; if (!eraseAllowed) { return false; } legacyExists = false; return true; }
        };
        require(coordinator.read(output, legacy) == StoreResult::Ok && output == value);
        require(!legacyExists && legacyReads == 1 && legacyErases == 1);
        require(coordinator.read(output, legacy) == StoreResult::Ok && legacyReads == 1);
        require(coordinator.erase(legacy) == StoreResult::Ok);
        require(store->read(output) == StoreResult::Absent);
        eraseAllowed = false;
        require(coordinator.read(output, legacy) == StoreResult::ReauthRequired && output.empty());
        require(coordinator.read(output, legacy) == StoreResult::ReauthRequired && output.empty());
        eraseAllowed = true;
        require(coordinator.erase(legacy) == StoreResult::Ok);
        require(coordinator.write(value, legacy) == StoreResult::Ok);
        fault(3);
        require(coordinator.erase(legacy) == StoreResult::ReauthRequired);
        require(coordinator.read(output, legacy) == StoreResult::ReauthRequired && output.empty());
        fault(0);
        require(coordinator.erase(legacy) == StoreResult::Ok);
        require(!env->ExceptionCheck());
        registeredPhoneStore().reset(); // Release global refs while JVM is live.
        return checks;
    } catch (...) {
        if (env->ExceptionCheck()) { env->ExceptionClear(); }
        registeredPhoneStore().reset();
        jclass failure = env->FindClass("java/lang/AssertionError");
        env->ThrowNew(failure, "protected storage JNI test failed");
        return 0;
    }
}
