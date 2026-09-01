# Dependency security baseline

Dependabot deliberately treats the Electron runtime, Electron packaging,
legacy request stack, JSDoc major upgrades, and low-risk maintenance as
separate review units. Do not combine those pull requests or auto-merge them.
Every update must regenerate its committed lockfile and run the relevant smoke
test before merge.

The current baseline removes unused Axios and request dependencies from the
JSDoc tool. JSDoc 3 remains temporarily because the in-tree template imports
the TaffyDB API that JSDoc 4 removed. The server console still needs separate,
code-changing migrations away from Electron 3 and request; a lockfile-only
upgrade is not a substitute for those migrations.

## OSV scanning and SBOM output

Use OSV-Scanner 2 against the checkout after lockfiles have been generated:

```sh
osv-scanner scan source --recursive .
```

For machine-readable review evidence and a CycloneDX 1.5 SBOM, write generated
files to a temporary or CI artifact directory rather than committing snapshots:

```sh
osv-scanner scan source --recursive --format json --output-file /tmp/overte-osv.json .
osv-scanner scan source --recursive --all-packages --format cyclonedx-1-5 \
  --output-file /tmp/overte-sbom.cdx.json .
```

The recursive scan covers committed npm, Gradle, and Conan lockfiles supported
by OSV-Scanner. Nix evaluation and vendored C/C++ commit scanning remain
separate evidence because ecosystem coverage differs. Update `flake.lock` in a
dedicated Nix change and retain the old lock until evaluation and build checks
for every supported flake system have passed.

Do not blanket-ignore findings. Any exception must be placed in an
`osv-scanner.toml` beside the affected lockfile with the exact advisory ID, a
technical reason, an owner, and a review expiry date. License policy should use
an explicit reviewed allowlist; unknown or missing licenses fail review rather
than being silently accepted.

No dependency-security setup may download an opaque third-party archive. Tools
must come from a pinned package-manager input or a checksum/provenance-verified
release, and generated SBOM/scan artifacts must identify the exact source SHA.
