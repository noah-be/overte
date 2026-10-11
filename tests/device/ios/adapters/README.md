<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Physical iOS client and native developer-service bindings

[`adapter.py`](adapter.py) implements native input, UI and independently
observed acceptance operations. [`appium_adapter.py`](appium_adapter.py) retains
the iOS Appium transport and candidate preflight. The fixed shared CLI routes
iOS calls here; Android and generic imports use the shared implementation.

This is a namespace package so legacy utility search paths cannot shadow shared
Python adapters. See [Wi-Fi transport](WIFI_LAB.md) and the
[product test guide](../README.md) for host and physical qualification boundaries.
