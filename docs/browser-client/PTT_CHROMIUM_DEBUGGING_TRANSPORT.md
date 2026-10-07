# Owned PTT Chromium debugging transport

The protected setup-only diagnostic records `launchTimeout=true`; its private exception identifies a 30,000ms wait for the WebSocket endpoint. The fixed observed category is `launch-timeout-waiting-ws`. This evidence does not establish a sandbox, display, library, focus, microphone or audio failure.

Installed Puppeteer 25.12.0 provides the concrete argument cause. `ChromeLauncher.computeLaunchArguments` only inserts `--remote-debugging-port=0` (or a pipe) if no argument starts with `--remote-debugging-`. The fixture already passes `--remote-debugging-address=127.0.0.1`, which satisfies that condition, suppressing the automatic port. The resulting arguments have an address but no debugging transport. `BrowserLauncher.createCdpSocketConnection` then waits for the endpoint on stderr. Fixed source classification: `debugging-transport-missing-address-prefix-control`.

The original working Playwright launch explicitly adds `--remote-debugging-pipe` in its installed `defaultArgs`. The new owned Puppeteer route needs a WebSocket endpoint for its public Playwright `connectOverCDP` controller, so the narrow correction explicitly adds `--remote-debugging-port=0` alongside the retained loopback address. Chromium chooses the port; no fixed port, shared profile or foreign process is used. The helper still validates the actual returned endpoint against strict loopback, credentials/query/hash and browser-path ownership constraints before connecting.

No sandbox flag is added. Playwright's separate sandbox defaults are not copied as an unexplained remedy. Native worker isolation, capabilities and profiles are untouched. The default browser context, `noDefaults:true`, no viewport emulation, no focus/visibility overrides, synthetic-media consent, owned process/profile close, original 30,000ms setup/protocol limits and ten-second cleanup budget stay unchanged. No PTT/audio predicates or native permissions change.

Eighteen CPU contracts pass, including all sixteen existing ownership/source contracts. Two new controls invoke the exact installed Puppeteer argument builder, with only an authored executable string and a temporary-profile directory. They never launch a browser. The address-only negative produces no port or pipe; the actual corrected helper options produce exactly one ephemeral debugging port, retain loopback, use the temporary owned profile and preserve default-context/cleanup guards. Test-created directories are removed in `finally`. No Node 24-only API is introduced.

```sh
node --test browser-client/tests/integration/tablet-ptt-real-focus.test.mjs
```

The existing `tests/tablet-ptt-audit.test.mjs` imports this suite, so no additional CI stage is needed. Source and installed dependency hashes are bound by the packet manifest. Root must run the actual owned Chromium setup and then the unchanged genuine PTT journey. CPU argument proof is not a real startup, focus, PCM or cleanup acceptance claim. Keep private exceptions, endpoints, process/profile identities and media artifacts private; publish only reviewed fixed categories and counts. Preserve the original setup failure rather than overwriting its evidence.
