# Shared Android bootstrap implementation

The Phone application, legacy Android Interface and Pico application call
`overte-android-bootstrap.cmake` and the neutral `android-modules` directory.
The shared bootstrap uses `android-compat` for the existing Qt compatibility
headers. Previous Pico-named implementation paths are forwarding entry points;
the moved header and module implementations retain their original bytes.

The bootstrap no longer chooses a Pico host-tool or target-generator directory.
`HIFI_ANDROID_HOST_TOOLS` and `HIFI_ANDROID_CONAN_GENERATORS` are explicit caller
inputs. When `OVERTE_FDROID_CONAN_DIR` is set, its generated source-built
`fdroid-host-tools.cmake` takes precedence over the legacy host-tool directory.
An empty or missing declared source graph fails rather than selecting a fallback.
The existing job-pool governor and its environment name are retained.

The three Gradle consumers still declare their existing prepared legacy input
locations, including Pico-labelled directories where those are the current
consumer inputs. This relocation does not prove those legacy graphs equivalent
to the source-only F-Droid graph, qualify a native build, or finish SH-010.
Consumer graph provenance and exact built artifacts remain separate requirements.
No prepared directory is moved, generated, downloaded or cleaned by this change.

The neutral profile input map hashes the actual bootstrap, compatibility headers
and module implementations as well as the existing toolchain/profile inputs.
The recipe source manifest binds those implementations and current callers.
The profile scanner applies executable-input policy to profile/CMake/Python
inputs; C++ headers are hash-bound without treating `= default` constructors as
Conan profile selection.

Focused checks execute the actual bootstrap in a network-isolated CMake project
with `LANGUAGES NONE`, fixture Qt/Conan metadata and temporary host directories.
They verify imported targets, neutral include paths, generated host-tool mapping,
source-graph precedence, the unchanged governor, old entry-point forwarding and
missing/empty-input failures. No compiler, SDK, Gradle, Conan or native build runs.
Existing caller/package/parallelism and profile contract checks cover affected
source bindings; native JNI/WebEngine/Discord behavior is not newly qualified.
