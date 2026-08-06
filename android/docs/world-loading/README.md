# Pico 4 world loading

This directory contains the measured guidance for optimizing Overte worlds for
the Pico 4, including work that continues after the loading screen disappears.

- [Pico 4 world optimization guide](pico4-optimization-guide.md)
- [Serverless Hub A/B result record](serverless-hub-ab-results.md)

Run the measurement from `android/`:

```bash
./pico-world-loading-test.sh --runs 5
./pico-world-loading-report.sh power-results/<run>.csv
```

For the bundled Hub A/B fixtures use the serverless mode:

```bash
./pico-world-loading-test.sh --runs 3 --serverless \
  --target file:///~/serverless/overte-hub-original.json
./pico-world-loading-test.sh --runs 3 --serverless \
  --target file:///~/serverless/overte-hub-pico4-optimized.json
```

Each run produces milestone CSV, one-second telemetry samples, active-resource
snapshots, and filtered diagnostics. The runner uses wireless ADB, enforces
brightness 1% and fan 100% during the test, and restores the previous controls
afterwards.

Validate the checked-in serverless fixtures without a headset:

```bash
./tests/serverless-hub-fixture-test.sh
```
