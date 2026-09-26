# VirtualBaton tests

These tests exercise `scripts/developer/libraries/virtualBaton.js` and the Home
content copy at `unpublishedScripts/DomainContent/Home/virtualBaton.js` with
Node.js 22 or later and Node's built-in test runner. No npm dependencies are required;
the historical directory name is retained for existing callers.

From this directory:

```sh
npm test
```

From the repository root:

```sh
node --test tests/mocha/test/testVirtualBaton.js
```

The suite covers single and competing claimants, late arrivals, and release
handoffs with three message-delivery modes and both optimization settings.
Settled claimants must take over after release, including when two waiters
compete, and elections must stop when no claims remain.
An isolated clock and seeded election timing make the main scenarios
reproducible. Every scenario observes the entire ownership/release trace and
checks timer and message-subscription cleanup. A separate smoke test exercises
the real Node.js event loop.

The legacy direct invocation also works:

```sh
node tests/mocha/test/testVirtualBaton.js
```

Assertion failures, duplicate ownership notifications, incomplete handoffs, and
timeouts return a nonzero exit status.
