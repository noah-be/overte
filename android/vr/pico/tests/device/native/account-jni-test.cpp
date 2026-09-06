// SPDX-License-Identifier: Apache-2.0
#include "../../../apps/picoInterface/security/PicoAccountStore.h"
#include <cassert>
#include <iostream>
#include <string>
#include <thread>
using namespace overte::security;
int main(int argc, char** argv) {
    assert(argc == 2);
    std::string classPath = std::string("-Djava.class.path=") + argv[1];
    JavaVMOption option { const_cast<char*>(classPath.c_str()), nullptr };
    JavaVMInitArgs args { JNI_VERSION_1_6, 1, &option, JNI_FALSE };
    JavaVM* vm = nullptr;
    JNIEnv* env = nullptr;
    assert(JNI_CreateJavaVM(&vm, reinterpret_cast<void**>(&env), &args) == JNI_OK);
    auto store = overte::pico::protectedAccountStore();
    AccountBytes bytes { 99 };
    assert(store->read(bytes) == StoreResult::Unavailable && bytes.empty());
    assert(store->write({1}) == StoreResult::Unavailable);
    assert(store->erase() == StoreResult::Unavailable);
    assert(!overte::pico::prepareProtectedAccountStore(env, nullptr));
    auto type = env->FindClass("org/overte/pico/PicoAccountBridgeTest");
    assert(type);
    auto create = env->GetStaticMethodID(type, "create", "()Lorg/overte/pico/PicoAccountStoreBridge;");
    auto setMode = env->GetStaticMethodID(type, "setMode", "(I)V");
    auto cleared = env->GetStaticMethodID(type, "buffersCleared", "()Z");
    assert(create && setMode && cleared);
    auto peer = env->CallStaticObjectMethod(type, create);
    assert(peer && !env->ExceptionCheck());
    assert(overte::pico::prepareProtectedAccountStore(env, peer));
    assert(overte::pico::prepareProtectedAccountStore(env, peer));
    assert(store->read(bytes) == StoreResult::Absent && bytes.empty());
    assert(store->write({1,2,3}) == StoreResult::Ok);
    assert(store->read(bytes) == StoreResult::Ok && bytes == AccountBytes({1,2,3}));
    assert(env->CallStaticBooleanMethod(type, cleared));
    // Native worker must attach/detach correctly and use retained method IDs,
    // not FindClass with the bootstrap class loader.
    std::thread worker([&] {
        AccountBytes value;
        assert(store->read(value) == StoreResult::Ok && value == AccountBytes({1,2,3}));
        clearAccountBytes(value);
    });
    worker.join();
    for (jint mode : {2,3,4,5,6,7,8}) {
        env->CallStaticVoidMethod(type, setMode, mode);
        bytes = {99};
        auto expected = mode == 2 ? StoreResult::IoError : mode == 3 ? StoreResult::Locked
            : mode == 4 || mode == 7 ? StoreResult::Corrupt : StoreResult::Unavailable;
        assert(store->read(bytes) == expected && bytes.empty());
        assert(!env->ExceptionCheck());
        if (mode != 7) {
            assert(store->write({4}) == expected);
            assert(store->erase() == expected);
            assert(!env->ExceptionCheck());
        }
        assert(env->CallStaticBooleanMethod(type, cleared));
    }
    env->CallStaticVoidMethod(type, setMode, 0);
    assert(store->write({}) == StoreResult::Corrupt);
    assert(store->write(AccountBytes(MAX_ACCOUNT_BYTES+1)) == StoreResult::Corrupt);
    // Actual Shared coordinator + production JNI + production Java transport.
    assert(store->erase() == StoreResult::Ok);
    AccountStoreCoordinator coordinator;
    assert(coordinator.install(store));
    AccountBytes legacy {7,8};
    LegacyAccountInput old {
        [&](AccountBytes& output) { output = legacy; return StoreResult::Ok; },
        [&]() { legacy.clear(); return true; }
    };
    assert(coordinator.read(bytes, old) == StoreResult::Ok);
    assert(bytes == AccountBytes({7,8}) && legacy.empty());
    assert(coordinator.erase(old) == StoreResult::Ok);
    env->DeleteLocalRef(peer);
    env->DeleteLocalRef(type);
    assert(vm->DestroyJavaVM() == JNI_OK);
    std::cout << "Pico production JNI + Java + PX-15 migration/status/exception/worker-thread PASS (test backend)\n";
}
