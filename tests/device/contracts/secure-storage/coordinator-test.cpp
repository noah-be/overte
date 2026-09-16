// SPDX-License-Identifier: Apache-2.0
#include "../../../../security/storage/ProtectedAccountStore.h"
#include <cassert>
#include <iostream>
using namespace overte::security;

struct FakeStore : ProtectedAccountStore {
    AccountBytes bytes;
    StoreResult readResult { StoreResult::Absent };
    StoreResult writeResult { StoreResult::Ok };
    StoreResult eraseResult { StoreResult::Ok };
    bool mismatch { false };
    int reads { 0 }, writes { 0 }, erases { 0 };
    StoreResult read(AccountBytes& output) override {
        ++reads; output = bytes; return readResult;
    }
    StoreResult write(const AccountBytes& input) override {
        ++writes;
        if (writeResult == StoreResult::Ok) {
            bytes = input; if (mismatch) { bytes.push_back(9); }
            readResult = StoreResult::Ok;
        }
        return writeResult;
    }
    StoreResult erase() override {
        ++erases;
        if (eraseResult == StoreResult::Ok) { bytes.clear(); readResult = StoreResult::Absent; }
        return eraseResult;
    }
};

struct Fixture {
    AccountStoreCoordinator coordinator;
    std::shared_ptr<FakeStore> store { std::make_shared<FakeStore>() };
    AccountBytes old { 1, 2, 3 }, out;
    bool removeWorks { true };
    int legacyReads { 0 }, legacyErases { 0 };
    LegacyAccountInput legacy {
        [this](AccountBytes& output) {
            ++legacyReads; output = old;
            return old.empty() ? StoreResult::Absent : StoreResult::Ok;
        },
        [this]() { ++legacyErases; if (removeWorks) { old.clear(); } return removeWorks; }
    };
    Fixture() { assert(coordinator.install(store)); }
};

int main() {
    { AccountStoreCoordinator c; AccountBytes out{7}; bool touched=false;
      LegacyAccountInput legacy{[&](AccountBytes&){touched=true;return StoreResult::Ok;}, []{return true;}};
      assert(c.read(out,legacy)==StoreResult::Unavailable && out.empty() && !touched);
      assert(c.write({1},legacy)==StoreResult::Unavailable); }
    { Fixture f; assert(!f.coordinator.install(std::make_shared<FakeStore>()));
      assert(f.coordinator.read(f.out,f.legacy)==StoreResult::Ok);
      assert(f.out==AccountBytes({1,2,3}) && f.old.empty() && f.store->writes==1 && f.store->reads==2); }
    { Fixture f; f.store->writeResult=StoreResult::IoError;
      assert(f.coordinator.read(f.out,f.legacy)==StoreResult::ReauthRequired);
      assert(!f.old.empty() && f.legacyErases==0 && f.out.empty());
      assert(f.coordinator.read(f.out,f.legacy)==StoreResult::ReauthRequired); }
    { Fixture f; f.store->mismatch=true;
      assert(f.coordinator.read(f.out,f.legacy)==StoreResult::ReauthRequired);
      assert(!f.old.empty() && f.out.empty() && f.legacyErases==0); }
    { Fixture f; f.removeWorks=false;
      assert(f.coordinator.read(f.out,f.legacy)==StoreResult::ReauthRequired);
      assert(!f.old.empty() && f.out.empty()); }
    for (auto result : {StoreResult::Locked,StoreResult::Unavailable,StoreResult::Corrupt,StoreResult::IoError}) {
      Fixture f; f.store->readResult=result; f.store->bytes={8};
      assert(f.coordinator.read(f.out,f.legacy)==result && f.out.empty() && f.legacyReads==0); }
    { Fixture f; f.store->readResult=StoreResult::Ok; f.store->bytes={8};
      assert(f.coordinator.read(f.out,f.legacy)==StoreResult::Ok);
      assert(f.out==AccountBytes({8}) && f.legacyReads==0 && f.old.empty()); }
    { Fixture f; f.old.clear(); assert(f.coordinator.read(f.out,f.legacy)==StoreResult::Absent); }
    { Fixture f; assert(f.coordinator.write({},f.legacy)==StoreResult::Corrupt);
      assert(f.coordinator.write(AccountBytes(MAX_ACCOUNT_BYTES+1),f.legacy)==StoreResult::Corrupt); }
    { Fixture f; assert(f.coordinator.write({5,6},f.legacy)==StoreResult::Ok);
      assert(f.old.empty() && f.store->bytes==AccountBytes({5,6})); }
    { Fixture f; f.store->readResult=StoreResult::Locked;
      assert(f.coordinator.erase(f.legacy)==StoreResult::Ok);
      assert(f.legacyReads==0 && f.old.empty() && f.store->erases==1); }
    { Fixture f; f.store->eraseResult=StoreResult::IoError;
      assert(f.coordinator.erase(f.legacy)==StoreResult::ReauthRequired);
      assert(f.coordinator.read(f.out,f.legacy)==StoreResult::ReauthRequired);
      assert(f.coordinator.write({4},f.legacy)==StoreResult::ReauthRequired);
      f.store->eraseResult=StoreResult::Ok;
      assert(f.coordinator.erase(f.legacy)==StoreResult::Ok);
      assert(f.coordinator.write({4},f.legacy)==StoreResult::Ok); }
    std::cout << "PX-15 migration, readback, lock, corruption, erase and no-fallback contracts PASS\n";
}
