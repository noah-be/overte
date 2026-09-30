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

This portable Qt check assumes a trusted, stable document tree. It does not
provide an atomic, directory-handle-anchored open against concurrent filesystem
or symlink replacement by a local writer. Document directories and their parent
components must not be writable by untrusted users. Hard links inside the tree
are ordinary files; canonical paths cannot establish their content provenance.
Other HTTP-parser/authentication findings in #926 are outside this change.

## Focused native verification

The test registers through the normal `setup_hifi_testcase(Network)` macro,
CTest, `.github/native-tests.json`, and `tests/project-coverage.json`. It uses
temporary fixtures and fresh loopback-only servers on ephemeral ports. Each
request has a three-second deadline; CTest limits the executable to 120 seconds.
It never connects to existing servers. Unix symlink cases are included on Linux;
Windows native symlink qualification remains a separate platform check.

A focused host build needs CMake 3.24+, Ninja, a C++17 compiler, and Qt6 Core,
Network, and Test development packages. It compiles all actual embedded-webserver
product sources, including HTTP/HTTPS connections and managers, without replacing
them with mock implementations or requiring the full client dependency graph:

```bash
cmake -S tests/embedded-webserver/standalone -B build/http-boundary -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug -DOVERTE_QT_MAJOR=6
cmake --build build/http-boundary --target embedded-webserver-tests --parallel 2
ctest --test-dir build/http-boundary -R '^embedded-webserver-HTTPManagerTests-test$' \
  --output-on-failure --no-tests=error
```

On Apple branches the focused helper defaults to Qt6 and uses the same Qt selection
helpers as the production build. The regression executable links all actual
HTTP/HTTPS sources, including the Qt6 `QRegularExpression` SSI implementation.

For Qt installed outside the system prefix, add `-DCMAKE_PREFIX_PATH=<qt-prefix>`
and supply its runtime library search path if needed. For the full Overte build,
include `embedded-webserver` in `OVERTE_TEST_GROUPS` (or leave groups unrestricted)
and build/run the same target and CTest name in that build directory. The native
CI manifest runs every method and data row through its existing Qt result verifier.
