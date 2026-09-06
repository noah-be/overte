# SH-005 actual direct/ICE DNS visibility binding v001

The existing Application effective Qt/native visibility publisher reaches
NodeList and now the actual DomainHandler C++-only
`setClientDiscoveryVisibility`. A shared atomic generation snapshot invalidates
previous direct/ICE DNS callbacks immediately when foreground changes. Qt
resolver cancellation runs in the DomainHandler thread through AutoConnection;
a stale queued visibility action is rejected by its exact snapshot, including
rapid pause/resume. Domain hardReset also invalidates queued visibility actions
before cancellation and socket/domain mutation.

Direct and ICE lookup launch helpers refuse background work. While hidden, a
new target may replace domain metadata but starts no DNS. On foreground return,
an unconnected unresolved current target is resolved anew; only its current
generation may set a socket. An existing numeric ICE target may issue its normal
completion then, but not while hidden. Duplicate foreground input does not
restart work. Unmanaged assignment/server objects retain the existing active
default. This uses the existing effective-visibility authority, not a competing
platform lifecycle machine or native hook.

RequestScope adds read-only `snapshot()` and RequestTicket `matchesSnapshot()`.
The latter also matches a suspended generation for queued cleanup; it is NOT
permission to perform network work. Such work still requires `current()`.
No identity or endpoint is exposed by these tickets. Visibility publication is
serialized by the existing GUI-thread publisher; only its atomic invalidation
crosses into the DomainHandler thread.

Import dependencies (all exact immutable source versions):

- sh005-nodelist-visibility/v001 be92baefc95271158c3e2e517166af5219e503d1,
  manifest1f862b8a2af84465384b3c5f8ba8c001072ee1c6ae0762a957f33e3250892d82,
  including its Qt/native input and HTTP prerequisites.
- sh005-ice-hostname/v001 5177f6c24d47f1cbcddc7fd0265c4eb687f06315,
  manifest5c10a279c23e42ae96904eb27126f086c95d324eee8ea28b63c957418961a814.
- px16-domain-diagnostics/v001 6fac7b9768c59198da6db101e8c3ca501d7c60a1,
  manifest36b556dbaf94d21279877330750fc0064fa2628e3f89226ed7e7abc8c70fea45.

Focused tests compile the complete production visibility method, both DNS
launch helpers, ICE setter/completion and actual reset prefix with original
ScopedHostnameLookup/RequestScope and real Qt. Cross-thread pause before event
delivery, quick pause/resume, latest hidden target, stale/duplicate reply,
numeric ICE and same-state publication are covered. OS resolver, socket value
storage, timing/signal receivers and unchanged reset tail remain boundaries.
Existing direct DNS, NodeList entry/publication and HTTP tests remain required.

Limits: this is not an in-flight callback barrier or a hard OS resolver deadline.
Already-entered work, other SockAddr/STUN/ICE replies/UDP transport queues,
settings timers/auth requests, complete connect/reconnect/recovery UI, sticky
script consent/revoke, whole Qt5/platform compilation and device acceptance
remain pending. NodeList transport guards remain entry-only. No SH-005 PASS.
