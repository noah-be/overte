# Shared Appium implementation

This directory owns the platform-neutral Appium transport, its Android/iOS
manifests and example configuration. Its executable protocol and security
contracts are `tests/device/self_tests/test_shared_appium_adapter.py` and
`tests/device/self_tests/test_appium_security.py`.

The older `adapters/appium/` entrypoint forwards here on `main`. Apple iOS owns
that older path as an extension point for its native process identity, signing,
RemoteXPC and device-lab integration. Shared tests address this directory
explicitly so parent propagation never replaces or tests the wrong consumer.
Both implementations continue to use the common device contracts.

See the [Appium setup guide](../appium/README.md) for transport prerequisites.
A shared transport contract is not evidence of iOS device acceptance.
