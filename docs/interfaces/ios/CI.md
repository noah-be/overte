# iOS continuous integration

The current workflows are:

- `iOS bootstrap` (`.github/workflows/ios-bootstrap.yml`): Linux contracts,
  unsigned iPhone/iPad simulator launch, and unsigned device-SDK packaging;
- `Provision Qt iOS source cache` (`.github/workflows/ios-qt-source.yml`): manual,
  license-neutral preparation of matching Qt host and target trees; and
- `iOS experimental integrated client gate`
  (`.github/workflows/ios-integrated.yml`): opt-in dependency, build, package,
  readiness, and sanitized-failure path.

The bootstrap workflow runs on `apple-ios`. Uploaded simulator archives,
unsigned device IPAs, and diagnostics are retained for seven days. An unsigned
IPA is an inspectable developer artifact, not an installable or accepted device
release until an authorized local signing step has completed.
