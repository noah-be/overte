# SH-005 V8 iterator failure prerequisite v001

The actual V8ScriptValueIterator constructor and accessors now check fallible V8
operations instead of using ToLocalChecked/assertions on proxy/getter results.
No native hook or other v09 contract prerequisite. This is the real Shared
iterator used beneath ScriptManager, not a complete revoke mechanism.

Length/index start at0/-1. Null/nonobject input, failed own-key enumeration and
out-of-range key count leave an empty iterator without publishing partial object
or key handles. name/value before next or on failed/empty construction return
empty name/undefined. Getter errors and termination return undefined while the
outer V8 exception remains caught by the caller. No dynamic key diagnostic or
unchecked key coercion is performed. Ordinary own-key order/value delivery and
next/hasNext behavior remain intact; last-current-item semantics are unchanged.

Focused check:

    V8_TEST_ROOT=/explicit/host/node-prefix python3 tests/device/contracts/lifecycle/test_v8_iterator.py

Complete original iterator class and six methods compile with real V8 and Qt;
only engine/value storage scaffolding is substituted. Seven network-isolated
cases PASS1.808s: ordinary, empty, null, throwing/terminated ownKeys proxy and
throwing/terminated getter. Pre-next name/value and actual persistent-handle
destruction during captured termination are covered. Each subprocess is bounded
by an external five-second timeout. Host V8 is never a candidate binary input.

Pending: whole engine/platform build, general wrapper/isolate lifetime and
native callback handling, other property/constructor/registration paths,
sticky lifetime-safe cancellation/fresh regrant, informed default-deny entity
consent and finite in-flight revoke, original artifact/device acceptance.
This does not establish a hard production deadline or make hostile JS safe.
