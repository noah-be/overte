# PX-15 protected account storage v001

Implementation contract, not PX-15 acceptance. Header-only C++14 coordinator:
`security/storage/ProtectedAccountStore.h`. Production consumer:
`libraries/networking/src/AccountManager.{h,cpp}`. Import the published commit
patch in a local integration branch only; owners do not independently edit those
Shared paths. Include the exported header for adapter compilation meanwhile.

## Native binding

Derive from `overte::security::ProtectedAccountStore` and implement:

```cpp
StoreResult read(AccountBytes& output);
StoreResult write(const AccountBytes& input);
StoreResult erase();
// Before first AccountManager account load, from the platform's startup caller:
AccountManager::installProtectedAccountStore(std::make_shared<NativeStore>());
```

Registration returns false for null or a second registration; retain the first
adapter. Missing registration denies all persistence and loading, including the
legacy file. Calls are synchronous, serialized by the coordinator; adapters must
catch OS/JNI exceptions and return a status, never reenter AccountManager, and
must not retain input/output references. The adapter instance is process-lived.
`AccountBytes` is an owned vector of uint8_t; one nonempty opaque record is at
most 1 MiB. Native record key is the literal `account-map-v1` for keyed stores.
Phone/Pico's single-record Java stores require no additional key parameter.
No Shared-generated encryption key, platform key export, backup or cloud sync.

`Ok` means a completed operation, `Absent` exclusively means no stored record,
`Locked` means temporarily inaccessible, `Unavailable` means native facility or
binding missing, `Corrupt` includes malformed ciphertext/wrong or missing key
for an existing record, `IoError` means another native operation failure.
`ReauthRequired` is the coordinator's ambiguous-state quarantine. On every read
failure output is discarded. Native adapters should clear it themselves too.
Native writes must be atomic and protected; successful writes are verified by
an independent read and byte comparison before Shared exposes migrated data.

Phone failure mapping: KEY_UNAVAILABLE -> Unavailable (Locked only with explicit
native evidence), MISSING_KEY/CORRUPT/INPUT -> Corrupt, READ/WRITE/DELETE ->
IoError. Java null read -> Absent. Pico applies these same semantic outcomes to
its native status vocabulary. iOS: NotFound -> Absent, Invalid -> Corrupt,
Failed -> IoError; Ok/Locked/Unavailable/Corrupt retain their meanings.
Never map inaccessible, wrong-key, reinstall-orphaned or corrupt data to Absent.

## Migration and logout

Protected read precedes any legacy read. Only protected Absent permits a bounded,
well-formed legacy `AccountInfo.bin` map to migrate. Write, readback equality,
then legacy deletion must all succeed before credentials become available.
An interrupted migration with valid protected bytes uses those bytes only and
removes the obsolete legacy copy. Failed write/readback/deletion quarantines the
coordinator for this process, retains legacy for explicit recovery, returns no
credentials and requires logout/re-authentication; no plaintext fallback exists.
Lock/unavailable/corrupt reads never try legacy. The adapter must preserve these
distinctions across restart. Persistent ambiguous OS outcomes remain platform
verification work; a process quarantine is not a durable native tombstone.

Logout clears AccountManager's live credentials and pending private key first,
then attempts legacy deletion and native erase without loading old data. It
erases the entire account map, including other cached auth endpoints, rather
than retaining uncertain credentials. A failed deletion keeps the process
quarantined. A later explicitly successful erase clears quarantine. Locked-store
logout must attempt native invalidation; it must not report success on failure.
Old flash blocks/backups are not claimed securely erased by QFile::remove.

## Field inventory and privacy

The whole existing QVariantMap encoding is protected, without native parsing.
Its auth-URL map keys, usernames and IDs are private, not public metadata.
DataServerAccountInfo serializes access token (token, expiry, token type, refresh
token), username, XMPP password, Discourse API key, legacy UUID placeholder,
private key, domain ID, temporary domain ID and temporary-domain API key.
None may be persisted directly or logged. AccountSettings home-location remains
under its existing in-memory behavior; DomainAccountManager's in-memory token
is not newly persisted. This contract introduces no new data collection.

## Conformance and remaining evidence

Run `c++ -std=c++14 -Wall -Wextra -Werror -pthread
tests/device/contracts/secure-storage/coordinator-test.cpp -o <scratch>/storage`
then execute that test. It exercises the actual coordinator with test-only
native substitutes: migration ordering, write/readback failure, legacy-removal
failure, no adapter/fallback, locked/corrupt stores, bounds and logout recovery.
Platform owners must test their real adapter with these outcomes and register
through the production entry point. Native locked/key/reinstall faults and
plaintext absence on real devices are pending; the host fake is not OS evidence.
Full Qt AccountManager compilation/integration, desktop protected adapters,
SH-003/SH-005 acceptance, platform builds and downstream login/upgrade/locked-
store checkpoints remain pending. Do not merge an unbound product or label a
node PASS on the basis of this contract. PX-16 is a separate pinned release.

## Shared serialized-map validation

LegacyAccountInput additionally accepts an optional Shared-owned `validate`
callback. Existing two-callback consumers remain source-compatible and keep the
opaque nonempty/1-MiB bound. AccountManager supplies its real QDataStream map
validator for protected reads, migration and writes. Protected bytes must decode
as a complete QVariantMap with no trailing data before the coordinator deletes
legacy data or exposes the record. Invalid protected serialization quarantines
the process and preserves legacy; it never falls back to those credentials.
Explicit logout/erase remains the recovery operation. Native adapter interfaces
and protected record key/format are unchanged. The validator executes under the
coordinator lock and, like the other Shared callbacks, must not reenter it.

The actual AccountManager file/map functions, actual QDataStream and coordinator
run together in `test_account_map.py` with temporary files and an opaque memory
store. Tests cover valid migration/write/read, truncated/trailing protected data,
legacy retention and quarantine, corrupt legacy, mismatched readback and explicit
erase recovery. This joins serialization to migration; QVariantMap values are
fixtures, not the complete DataServerAccountInfo metatype field corpus. Native
OS durability, parser resource limits beyond input size, every field/version,
real AccountManager startup and restart recovery remain unqualified.
