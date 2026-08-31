# Build Overte for Pico 4

The authoritative detailed command reference remains
[`android/vr/pico/docs/BUILD.md`](../../../android/vr/pico/docs/BUILD.md). Run its build
commands from `android/` on a 64-bit Linux host.

Required tools include Conan 2, Git, CMake, Ninja, Python, Perl, the Android SDK
and NDK, a supported JDK, and ADB for physical installation. Prefer the
checksum-verified prebuilt dependency path for ordinary development; source
dependency builds can take several hours and are maintainer work.

```bash
cd android
./build-pico.sh doctor
./build-pico.sh deps --download
./build-pico.sh prepare
./build-pico.sh build
```

Use `PICO_BUILD_JOBS` to bound general compilation and `PICO_SHADER_JOBS` to
bound shader generation independently. The script's `--help` output is the
authority for supported commands and path overrides.
