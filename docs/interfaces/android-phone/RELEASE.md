# Android Phone developer artifacts

The current milestone is an installable developer APK. Selection of Play,
F-Droid, direct download, or another publication channel is deferred.

For local development, build and deploy the debug APK with an explicit device
serial. Verify the exact APK contents and 16-KiB compatibility before sharing it.

The protected release-candidate workflow produces an unsigned APK, provenance,
SBOM, and checksums from an immutable `android-phone-vM.m.p-alpha.N` tag. That
artifact is for inspection and reproducibility work; it must not be presented to
users as an installable release.

A future signed artifact must repeat signer, package, permission, contents, ABI,
and page-size gates and requires a separately approved signing process.
