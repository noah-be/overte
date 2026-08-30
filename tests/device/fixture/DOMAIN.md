# Controlled E2E domain fixture

`domain.py` owns a private, ephemeral domain-server, one assignment-client
monitor, and the repository-owned persistent assignment
`domain_content_agent.js`. The assignment creates four uniquely named domain
entities. The common `domain-smoke` module requires a real domain connection,
the exact domain UUID returned by `/id`, all four markers for consecutive probe
samples, stable process identity, and foreground state.

Run it only with locally built, trusted executables and keep its output outside
the checkout:

```bash
python3 tests/device/fixture/domain.py \
  --domain-server /absolute/build/domain-server \
  --assignment-client /absolute/build/assignment-client \
  --public-host 192.0.2.10 \
  --output-dir /tmp/overte-domain-fixture \
  --ready-file /tmp/overte-domain-ready.json
```

The ready file supplies `domainUrl`, `domainHost`, `domainId`, and
`requiredMarkers`. Export those values as `OVERTE_E2E_DOMAIN_URL`,
`OVERTE_E2E_DOMAIN_HOST`, `OVERTE_E2E_DOMAIN_ID`, and
`OVERTE_E2E_DOMAIN_MARKERS_JSON` before running `domain-smoke`.

`domain-recovery` uses the same values plus `OVERTE_E2E_SCENE_URL`. It enters
the domain, returns to the controlled serverless scene, proves that the domain
is disconnected, and re-enters the exact domain without changing the
Interface process identity.

The controller's ready metadata means only that the infrastructure is
reachable and its assignment processes survived warmup. Only the client probe
can prove that the domain handshake completed and the entity server delivered
the assignment-owned markers. Each product adapter advertises
`navigation.enter-domain` only after its own physical acceptance gate.
