# Android Conan lockfile design

These Conan 2 lockfiles capture recipe revisions for every checked-in Android
host profile, resolved with the checked-in Linux x86_64 build profile:

| Lockfile prefix | Host profile | Recipe |
| --- | --- | --- |
| `pico4-arm64` | `profiles/pico4-arm64` | `conanfile-pico.py` |
| `phone-arm64-16k` | `profiles/phone-arm64-16k` | `conanfile-pico.py` |
| `phone-nonqt-arm64-16k` | `profiles/phone-nonqt-arm64-16k` | `conanfile-pico.py` |
| `phone-emulator-x86_64` | `profiles/phone-emulator-x86_64` | `conanfile-pico.py` |
| `pico-host-tools` | `profiles/phone-prebuilt-linux-x86_64` | `conanfile-pico-host-tools.py` |

The four Android graphs currently resolve to the same recipe revisions. They
remain separate files so a target-specific option or revision cannot silently
change another target's review evidence.

Regenerate only after exporting the three repository recipes and reviewing
remote recipe changes. For example:

```sh
conan export android/common/conan/recipes/libnode
conan export android/common/conan/recipes/nvidia-texture-tools --version=2023.01
conan export android/common/conan/recipes/onetbb-local --version=2021.10.0
conan lock create android/common/conan/conanfile-pico.py \
  -pr:h android/common/conan/profiles/pico4-arm64 \
  -pr:b android/common/conan/profiles/phone-prebuilt-linux-x86_64 \
  --lockfile='' --lockfile-clean \
  --lockfile-out=android/common/conan/locks/pico4-arm64-linux-x86_64.lock
```

An install using a reviewed graph must pass the matching file explicitly with
`--lockfile=<path>`. Build-script enforcement is intentionally deferred until
each existing online, offline, source-build, and checksum-pinned prebuilt path
can be tested together; strict Conan lockfiles reject graph additions that are
not represented in the selected lock.

The current Android locks record the existing OpenSSL 1.1 dependency and are
evidence of the migration starting point, not approval to keep it. See
[`../OPENSSL_3_MIGRATION.md`](../OPENSSL_3_MIGRATION.md).
