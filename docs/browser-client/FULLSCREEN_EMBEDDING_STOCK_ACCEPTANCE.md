# Additional stock fullscreen embedding acceptance

This executable packet is prepared, not browser-qualified. Six CPU contracts pass; syntax checks pass. It adds two explicitly separate actual embedding cases. It does not replace/rerun the original four Playwright bodies, promote the failed Firefox HTTP-header case, or change production fullscreen/viewport policy.

## Cause and scope

Exact official FIREFOX_156_0_RELEASE Document.cpp4289–4321 initializes the container feature policy before its default-off HTTP header branch and only reads legacy Feature-Policy there. StaticPrefList.yaml4931 sets that branch false; FeaturePolicyUtils declares fullscreen's default allowlist self. Document.cpp16961–16969 checks actual feature policy/container permission. These primary files and their SHA256 values are frozen in /tmp/overte-fullscreen-gecko-policy-analysis/manifest.json (db0640216ae9689b36e1f3a5a678464a0807f8df6fbe24e0b30c2ef99fdb4eff). The existing handled Permissions-Policy response/fullscreenEnabled=true failure is retained.

This followup independently tests a real foreign iframe without delegation, then a fresh iframe with explicit allowfullscreen. BrowserTablet and its original registered fixture installation/proof callback are extracted only after the unchanged original spec SHA53ae639c6ec16a6f57aba3ee60bf997e87589a20ec6ce50735fd3bccfb393c37 matches. No fake fullscreen API, document getter override or custom permission preference is used. The original authored480×706 fixture picture qualifies browser control/canvas/input behavior, not native worker pixels or full native Tablet parity.

## Root-owned stock execution

Root alone runs browsers/Vite and verifies owned process/executable/library identities. Reuse the parent-owned Vite listener on5187; no new service is started by this driver. Its127.0.0.1 parent and localhost child use the same exact owned port with different real origins. Ensure localhost resolves to that same owned listener and normal Vite source modules are accessible through both hosts. Only two exact authored HTML requests are fulfilled by browser interception; other requests continue normally. A fresh cross-origin iframe is created by the parent's actual document response, with no sandbox/allow/delegation for the negative and explicit allowfullscreen for the positive. Each case has a new browser context.

Supply a fresh nonexisting private output directory. The driver creates0700 output and0600 private report; it closes its own browser/context/profile and changes no native workers/entities/audio/services. Do not commit private reports, screenshots or error messages. Output stdout contains fixed case enums and booleans only.

```sh
umask 077
OVERTE_FULLSCREEN_SOURCE=/home/user/Documents/github/overte-browser-client/browser-client \
OVERTE_FULLSCREEN_OUTPUT=<fresh-nonexisting-private-directory> \
OVERTE_FULLSCREEN_URL=http://127.0.0.1:5187 \
OVERTE_FULLSCREEN_BROWSER=system-chromium \
OVERTE_FULLSCREEN_CHROMIUM=<owned-stock-154-executable> \
OVERTE_FULLSCREEN_CHROMIUM_LIBRARY_PATH=<matching-browser-only-library-directory> \
DISPLAY=:0 \
node /tmp/overte-fullscreen-embedding-stock/browser-client/tests/integration/fullscreen-embedding-stock.mjs
```

For a separate stockFirefox156 run, use a fresh output, OVERTE_FULLSCREEN_BROWSER=system-firefox and OVERTE_FULLSCREEN_FIREFOX=<owned-installed156-executable>. Remove inherited Chromium library variables/LD_LIBRARY_PATH. Firefox uses the reviewed exact186bb0 system window helper within its unchanged ten-second public exact-viewport/native-DPR bound. Chromium uses its public Puppeteer-owned default-density launch; this supplemental iframe driver neither sets a viewport nor creates a Playwright context/focus override. The public launch preserves sandboxing and ordinary defaults; no SwiftShader/security/media flags or permissions are added.

## Mandatory actual oracles

Negative: actual distinct-origin child Frame, visible/current connected host, no delegation attributes and actual fullscreenEnabled=false; disabled production Fullscreen control and its unchanged embedding-unavailable message; original exact[40,80,100,255] canvas pixel/aspect; real driver canvas click must produce both trusted physical pointer events and exact production press/release revision1/frame1/button0/one-pixel center coordinates. Both documents remain outside fullscreen. A separate authored visible probe button synchronously calls the real requestFullscreen on the connected host from its trusted click, once, before awaiting. Its actual TypeError rejection is accepted only with visible/current/connected/denied target and no fullscreen owner. This probe does not forge the disabled BrowserFullscreen control or synthesize an event.

Positive: fresh explicit-delegation iframe must instead have actual enabled capability and ordinary enabled BrowserTablet control. The same actual canvas/wire/pixels remain usable. A trusted production Fullscreen click must enter that child's owned host and the parent's exact iframe; pixels/aspect remain unchanged and aria-pressed becomestrue. The unchanged Exit fullscreen button must actually exit both documents with no status errors. Real cleanup disposes the child Tablet and leaves neither document in fullscreen.

Original ten-second API/readiness/input waits and forty-five-second case bound stay intact. Same-origin substitutes, accidental allow attributes, a wrong current Frame, synthetic/untrusted events, unknown rejection, missing pixel/input record or source change refuse. This case does not revisit the separate floating DOMRect/rounded innerWidth equality failure and does not make full-window geometry claims. The registered four original bodies remain byte-identical and their stock failures remain distinct.

```sh
cd /tmp/overte-fullscreen-embedding-stock/browser-client
node --test tests/fullscreen-embedding-stock.test.mjs
node --check tests/integration/fullscreen-embedding-stock.mjs
```

The new wrapper follows existing Node test discovery and adds no CI stage. Actual browser evidence remains pending parent execution.
