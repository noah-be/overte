# iOS universal device adapter

The adapter uses `xcrun devicectl` and accepts only connected, paired physical
iPhone/iPad targets with Developer Mode and DDI services available. Currently
it advertises bounded launch and terminate operations. Process/foreground
stability remains capability-skipped until a reliable physical-device polling
contract is established.

Current-artifact IOS-P2 product journeys and their coverage boundaries are in
[parity acceptance](PARITY_ACCEPTANCE.md), with an explicitly unfilled
[observation sheet](PARITY_OBSERVATION_TEMPLATE.md). They supplement the existing
native laboratory routes; these two universal entries alone do not qualify the
fourteen parity criteria or establish installed IPA identity.
