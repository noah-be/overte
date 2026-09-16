# Shared Android device transport

`AdbTransport` contains device-tooling primitives shared by Phone, Pico, and
Quest adapters. It knows ADB and Android system output formats, but it does not
know Overte package names, launcher activities, XR policies, or target-specific
acceptance rules. Those remain in the platform adapters.
