# Embedded webserver document-root boundary

`HTTPManager` resolves the configured document directory to its canonical path.
Each static request, selected `index.html`/`index.shtml`, and SSI `file`/`virtual`
include must have both a lexical path inside that directory and an existing
canonical target inside it before opening. Containment compares directory
components (root equality or root plus a separator), so similarly named sibling
directories do not qualify. URL paths are checked after Qt's URL decoding; the
existing embedded-NUL request rejection runs before the application handler.
SSI names are filesystem names, without additional URL decoding, and reject NULs.

Symlinks within the document tree are supported when their final target stays
inside the canonical root. A configured root may itself be a directory symlink;
its resolved directory defines the boundary. File and directory symlinks to
outside targets are rejected, including symlinked index files and SSI targets.
Nonexistent or dangling targets are unavailable: static requests return 404,
and SSI replaces missing or rejected includes with an empty string. Existing
outside request/index targets return 400; outside directory requests do not
redirect. An unavailable/non-directory root returns 404 for static requests.

Valid directory redirects retain their query string. Index selection still
prefers `index.html`, then `index.shtml`. SSI file includes are relative to the
resolved served file's directory; virtual includes are relative to the document
root. A leading slash in either kind remains relative to that base, preserving
the previous include semantics. Expansion remains a single pass: included
text is not recursively evaluated. Adjacent directives are processed even when
a preceding include is empty or shorter than its directive. The served filename
continues to determine HTML/SSI behavior, including symlink aliases.

This portable Qt5 check assumes a trusted, stable document tree. It does not
provide an atomic, directory-handle-anchored open against concurrent filesystem
or symlink replacement by a local writer. Document directories and their parent
components must not be writable by untrusted users. Hard links inside the tree
are ordinary files; canonical paths cannot establish their content provenance.
Authentication policy and the other findings in #926 remain separate work.

## Request parser resource policy (C1)

Parsing precedes application authentication. `HTTPManager::setRequestLimits`
configures the owning listener before requests are live; it rejects invalid
policies and changes while admitted connections exist. HTTP and HTTPS use the
same policy. Configuration and request accounting run in the manager's Qt thread.

The defaults in `HTTPRequestLimits` are:

| Resource | Default |
| --- | --- |
| Request line plus all headers, including CRLFs | 64 KiB |
| Body | 2,147,483,646 bytes (Qt5 array ceiling minus terminator space) |
| Concurrent admitted connections | 32 |
| Aggregate reserved request bytes per listener | 4 GiB |
| In-memory body threshold | Below 10,000,000 bytes; larger bodies use temporary files |
| Header deadline from accept | 30 seconds |
| Absolute request deadline from accept | 5 minutes |
| Idle input deadline | 30 seconds |

The body default preserves the previous positive `toInt` range except its
unsafe final byte; the old 10 MB value was a spooling threshold, not an upload
limit. The shipped content-restoration UI sends 1 MiB chunks with a 30-second
client timeout (`domain-server/resources/web/content/js/content.js`). Settings
restore and assignment-script uploads send whole files without a declared size
maximum (`settings/js/settings.js`, `assignment/js/assignment.js`). Those callers
do not justify imposing a new small universal upload maximum. Deployments can
choose smaller body/aggregate limits and longer finite deadlines through the API;
the appropriate maximum for unusually large whole-file uploads remains an
operator decision, not verified usage. No UI/config-file setting is added here.

Admission reserves one header allowance and one 64 KiB socket-buffer allowance.
The complete declared body is reserved before allocating memory or resizing a
temporary file. Reservations remain charged while a completed request is held
by an asynchronous handler, and are returned once on failure/disconnect/destruction.
Failed requests return their body storage immediately; their admission allowance
lasts until closure. An exhausted budget returns 503 before allocating body
storage. Accounting uses overflow-safe subtraction. These are logical wire/body
reservations, not a measurement of process RSS: Qt object/container overhead,
TLS buffers, kernel buffers, transient 64 KiB reads, and application-created
copies are separate. The connection cap, header cap, and fixed-size reads bound
parser-side overhead. Each listener owns its budget; this is not a process-wide
budget shared between unrelated managers or application upload-session storage.

Lengths must contain only decimal digits after optional surrounding SP/HTAB.
Negative/signed/fractional/overflowing values, repeated Content-Length fields
(including equal values), comma lists, folded headers, invalid field names, and
all Transfer-Encoding fields are rejected with 400. Chunked decoding is not
implemented. Values exceeding the policy or Qt5 array range return 413, and
oversized request lines/headers return 431. Lines use CRLF, exact supported
method names, and HTTP/1.0 or HTTP/1.1. Even a configured larger header allowance
cannot permit an individual line to fill the 64 KiB socket buffer without a
newline. Rejected requests never reach application authentication/dispatch.

Both absolute deadlines are non-renewable. Incremental bytes renew only the
idle timer, so a peer cannot retain an incomplete request forever by trickling
bytes. Deadline comparisons also run before parsing/dispatch, covering delayed
timer delivery. All timers are QObject children of the connection and follow
its thread/lifetime. Parsing deadlines stop on completed dispatch, preserving
asynchronous handlers. Timeouts return 408; rejected responses have a bounded
forced-close fallback. Existing behavior is one request per connection with
`Connection: close`, including when the client asks for keepalive or pipelines
another request; this change does not add persistent connections.

Temporary-file open, resize, checked writes, flush, and mapping are validated.
File bodies are written through QFile before mapping completed content, avoiding
unchecked writes into sparse mapped pages when disk space runs out. Allocation
exceptions or failed storage operations return 500 without dispatch. Files own
their mappings and auto-removal; connection cleanup releases storage before
returning its reservation. `requestContent()` remains a borrowed view whose
file-backed bytes are valid until failure/disconnect or connection destruction.
After cleanup, its accessor returns an empty array even if deferred QObject
deletion has not run yet. A caller that retains content must make an owning copy.
Globally fatal OS/allocator conditions
are not made recoverable by this API; finite policy prevents unbounded parser
reservations, and recoverable allocation failures are handled explicitly.

The existing required `embedded-webserver-HTTPManagerTests` executable runs all
C1 methods/data rows as well as the preserved document-root regressions. Tests
use production HTTPConnection/HTTPManager on ephemeral loopback ports with small
policies. Storage-operation overrides invoke real failing Qt open/resize/map/write
operations, and inject allocation throws/short buffers through the same production
allocation call. Coverage includes split messages, limits/overflow, framing,
trickle/idle deadlines, aggregate exhaustion, asynchronous retention, disconnect
and manager destruction, threshold crossing, multipart content, and authentication
header dispatch controls. The fixture handler is not the DomainServer's complete
authentication implementation. No live user service or physical device is tested.

## Focused native verification

The test registers through the normal `setup_hifi_testcase(Network)` macro,
CTest, `.github/native-tests.json`, and `tests/project-coverage.json`. It uses
temporary fixtures and fresh loopback-only servers on ephemeral ports. Each
request has a three-second deadline; CTest limits the executable to 120 seconds.
It never connects to existing servers. Unix symlink cases are included on Linux;
Windows native symlink qualification remains a separate platform check.

A focused host build needs CMake 3.24+, Ninja, a C++17 compiler, and Qt5 5.15 Core,
Network, and Test development packages. It compiles all actual embedded-webserver
product sources, including HTTP/HTTPS connections and managers, without replacing
them with mock implementations or requiring the full client dependency graph:

```bash
cmake -S tests/embedded-webserver/standalone -B build/http-boundary -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug
cmake --build build/http-boundary --target embedded-webserver-tests --parallel 2
ctest --test-dir build/http-boundary -R '^embedded-webserver-HTTPManagerTests-test$' \
  --output-on-failure --no-tests=error
```

For Qt installed outside the system prefix, add `-DCMAKE_PREFIX_PATH=<qt-prefix>`
and supply its runtime library search path if needed. For the full Overte build,
include `embedded-webserver` in `OVERTE_TEST_GROUPS` (or leave groups unrestricted)
and build/run the same target and CTest name in that build directory. The native
CI manifest runs every method and data row through its existing Qt result verifier.
