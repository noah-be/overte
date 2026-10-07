# Optional model parse tasks

The production baseline remains the original parser scheduling. The experimental
`?modelParseTurn=1` option places each complete synchronous FBX parse in a separate
owned MessageChannel task. It cannot preempt a large individual parse and has no
proven general loading or Firefox rendering advantage.

One connected World owns the queue. At most 32 pending jobs and 256 MiB of charged
pending/active input are admitted. Cancellation removes pending readers and closes
idle ports. Reconnecting invalidates the old parse epoch immediately. Source
authority is checked at admission, before parsing, after parsing and after texture
completion. Revoked parsed resources are disposed through their original owner.
Only the typed optional queue-capacity error may fall back to the baseline parser,
after a fresh authority check; parse errors and cancellation never fall back.

The original 30-second model-texture deadline includes queued parsing and image
completion. A LoadingManager sentinel prevents early completion while parsing is
queued. Failure is recorded before aborting and ending that sentinel, and rejection
always has a consumer. Model mesh collision remains available at the original
stage, before delayed textures make the model visible.

The [actual browser proof](evidence/model-parse-turn-actual-browser-20261002.json)
retains six successful predicates across two runs and four preceding fixture
failures. Both bundled engines preserve six genuine authored FBX geometry,
material, decoded-image and BVH records; cancellation/revocation performs no
queued parse. Twelve distinct authored image dependencies produce twelve actual
HTTP requests and completion events. The actual constructed BrowserWorld retains
grounded keyboard movement on its initially invisible delayed-texture floor and
produces the expected final rendered pixel. These are authored component tests.

The [four short stock Hub cohorts](evidence/hub-model-parse-turn-stock-20261002.json)
load 295–296 actual models and preserve native pose/rejoin. Both Chromium modes
pass all four original fluidness gates; both Firefox modes fail them. Sampled
model-jobs-idle upper bounds are 21.135/20.536 seconds in Chromium and
21.148/17.786 seconds in Firefox. There is one ordered pair per engine, with a
changing live world and overlapping asynchronous work. These observations do
not establish a general speed gain, so the option remains disabled by default.

Run the component checks from `browser-client`:

```sh
node_modules/.bin/tsx --test tests/model-parse-turn.test.ts tests/world-model-parse-turn.test.ts
npx playwright test tests/model-parse-turn.browser.spec.ts tests/world-model-parse-turn.browser.spec.ts --workers=1
```

For the explicit actual Hub experiment, use the owned configured gateway and the
existing integration harness with `OVERTE_LAB_MODEL_PARSE_TURN=1`. Preserve its
original native freshness, movement, reconnect and fluidness assertions. The
earlier Chromium native-stream interruption and eight independent HTTP image
failures remain documented; subsequent short healthy cohorts do not explain them.
