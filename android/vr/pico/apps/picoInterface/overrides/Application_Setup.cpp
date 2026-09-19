// SPDX-License-Identifier: Apache-2.0
// Compile the common production setup with the reviewed Pico hooks.
// CMake excludes the standalone common translation unit for this target.
#if !defined(ANDROID_APP_PICO_INTERFACE)
#error "Pico setup requires the Pico application target"
#endif
#define OVERTE_PICO_SETUP 1
#include "../../../../../../interface/src/Application_Setup.cpp"
