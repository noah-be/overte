# Main provider completion receiver

SH-005, cohort685. Main/Phone/Pico variant only. Requires the corresponding
account-auth-context/v001 and account-auth-request/v001 implementation chain,
plus account-auth-completion/v001; use the exact matching existing Main source.
Apple retains a separately declared, guarded login error slot and must NOT
consume this Main-only source/test patch.

The actual Main AccountManager header has no requestAccessTokenError slot.
Steam and Oculus POST callers still attempted two legacy string-based
connections to that nonexistent receiver. Those two lines are removed; both
retain their actual typed requestAccessTokenFinished connection, original
RequestScope ticket, bounded deadline, form/redirect policy and cleanup path.
No new provider/origin is enabled, no failure suppressed, and refresh wiring
is unchanged. Actual finished handling remains the existing terminal producer.

The focused request fixture no longer invents the absent error slot. A negative
regression compares both complete original provider methods to the actual Main
header and fails on old source. Existing actual Qt POST tests retain all five
original request methods, field-injection/redirect/receiver assertions and the
real15s deadline with five aborted/cleaned replies. Completion success/error/
payload/stale/cleanup tests are exercised separately with their original methods.
The fixture's finished callbacks count dispatch; it is not full storage/UI proof.

Pending: same-context latest-request ordering, foreground UI cancellation,
native provider/storage/origin validation and full artifact/node acceptance.
Apple's guarded error method remains distinct; frozen Cold Build has another SHA.
