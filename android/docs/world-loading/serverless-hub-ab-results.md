# Serverless Hub A/B result record

Date: 2026-08-06, Pico 4 over WLAN ADB, brightness 1%, fan 100%.

| fixture | run | playable (ms) | release (ms) | settled (ms) | HTTP requests | HTTP bytes | tracked entities |
|---|---:|---:|---:|---:|---:|---:|---:|
| original | 1 | 48503 | 49474 | 75856 | 18 | 2127372 | 0 |
| original | 2 | 35663 | 36791 | 61040 | 18 | 2127372 | 0 |
| original | 3 | 33113 | 34014 | 57235 | 18 | 2127372 | 0 |
| optimized | 1 | 52470 | 53370 | 81419 | 18 | 2127372 | 0 |
| optimized | 2 | 39041 | 39949 | 65896 | 18 | 2127372 | 0 |
| optimized | 3 | 33786 | 34768 | 60233 | 18 | 2127372 | 0 |

Medians: original 35663 / 36791 / 61040 ms; optimized 39041 / 39949 /
65896 ms (playable / release / settled). The optimized fixture is therefore
not faster in this setup. Since no exported entity was tracked at the default
serverless spawn, this result does not measure the removed seat-script
preloads; it is a harness validation and a reason to repeat at a spawn point
inside the exported Hub content before making a production change.

The raw ignored artifacts were generated as:

```bash
./pico-world-loading-test.sh --runs 3 --serverless \
  --target file:///~/serverless/overte-hub-original.json \
  --output power-results/bundled-original-3run-final.csv
./pico-world-loading-test.sh --runs 3 --serverless \
  --target file:///~/serverless/overte-hub-pico4-optimized.json \
  --output power-results/bundled-optimized-3run-final.csv
```
