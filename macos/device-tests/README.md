# macOS universal device adapter

The local Mac is exposed as a physical reservable target. The adapter launches
the configured Overte executable directly, tracks its process identity, samples
RSS/CPU with `ps`, and terminates only the process group it started. Set
`OVERTE_MACOS_EXECUTABLE` when the app is not installed at the default path.
