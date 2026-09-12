# iOS Qt mutex pool correction

The Qt 6.11.1 fallback QMutex implementation uses QFreeList for QMutexPrivate
storage. Its seven-bit head serial wraps after 128 releases. If an allocator is
preempted after reading the next link, another thread can remove that next slot,
retain it, and recycle the head until the stale CAS succeeds. A live mutex pool
slot can then be allocated twice. The host regression reproduces this with the
unmodified upstream algorithm and a scheduling hook immediately before its CAS.

The patch serializes allocation and release with a separate native-backed
`std::mutex`. Using QMutex here would recursively require the same pool. The lock
covers pool operations, not callers' entire critical sections. Public Qt ABI and
QMutexPrivate layout are unchanged. The change is guarded by Q_OS_IOS; cached
macOS host tools retain their previous semantics and provenance. Other platforms
are outside this patch's scope.

The frozen iPad capture showed a PresentThread waiting on a QMutexPrivate
semaphore while the associated environment mutex pointer was already null. This
is consistent with pool corruption, but the historical interleaving was not
captured. The host reproduction does not establish that every observed native
freeze had this cause.

`ios/tools/qt-mutex-patch.py` accepts only the pinned original or corrected source
hash. The source builder applies it before configuration and records a new iOS
plan containing the patch hash. The producer uses a separate target cache key;
host Qt and V8 remain reusable. Before checkpoint publication and app compilation,
the workflow verifies the plan and hashes of the actual installed static QtCore
archives. The receipt supplements existing repository/branch trust checks and
ships with the IPA; it is not a Conan closure or native acceptance receipt.

Run `python3 ios/tools/tests/test-qt-mutex-patch.py` with host Qt6Core available.
It verifies the original failing interleaving, the corrected interleaving,
80,000 concurrent allocations without duplicate ownership, the unchanged host
branch, exact/idempotent patching, and refusal of missing/stale/modified SDK
receipts. The assertions checking duplicate ownership remain enabled while Qt's
own debug assertions are disabled to match the Release target.

Native acceptance still requires the resulting full client on iPad: sustained
movement/rendering and domain activity, foreground/background transitions,
script teardown/reload, and audio output/recovery. Track both responsiveness and
process lifetime; a live process alone does not establish stability.
