# SH-011 shared setup translation unit

Phone and Pico now use the actual functions in Application_Setup.cpp. Pico's
existing CMake source replacement selects an eight-line wrapper that defines
OVERTE_PICO_SETUP and includes that file; the standalone common translation
unit remains excluded from the Pico target. The wrapper rejects a non-Pico
application target. No second initialize/setupSignalsAndOperators implementation
is retained, and platform startup order is unchanged.

The 28 conditional selection sites preserve the preceding implementation's
includes, resources, account-store registration, crash recovery, concurrency,
updater, window/texture policy, safe landing, debug controller/Tablet hooks,
metrics and child QML-context creation. These are compile-time setup hooks,
not a new runtime registration or policy API. The common bodies and dependency
initialization now have one source. Existing Phone-only guards remain effective.
Pico E2E input still requires its separate compile-time gate; a normal release
does not gain the debug controller override.

The local differential at predecessor 9005e1d346d03a5bb43658be0dcab4de97b71e8a
compares complete C++ preprocessor output for Phone, Pico debug, Pico release
and desktop against both original files. All four are identical after removing
include directives only. Header resolution is separately checked for the new
wrapper and the two moved Pico include paths. This is conditional/body identity,
not native type checking, linking, initialization execution or startup evidence.

Pico's tests/pico-shared-setup-test.py preprocesses the selected production bodies,
checks one definition and the distinct Phone/Pico policies, and rejects using
the Pico wrapper for Phone. Existing Pico account JNI, lifecycle, accessibility,
package and Tablet tests read the actual common source after the refactor.
Native Phone/Pico startup and all original SH-011 dependency gates remain pending.

Import the Shared change and matching Pico wrapper/test migration together on a
Pico target. A common-source update alone does not remove an old full-copy
override from a different target tree. Apple has its own setup variant and must
not receive a whole-file replacement from this Android cohort.
