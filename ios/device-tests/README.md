# iOS universal device adapter

The adapter uses `xcrun devicectl` and accepts only connected, paired physical
iPhone/iPad targets with Developer Mode and DDI services available. Currently
it advertises bounded launch and terminate operations. Process/foreground
stability remains capability-skipped until a reliable physical-device polling
contract is established.
