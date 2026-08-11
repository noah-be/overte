# Shared Android-VR OpenXR Policies

This directory owns small, header-only decisions that are independent of an
Android headset vendor and can be compiled without Qt, an Android SDK, or a vendor
SDK. A policy belongs here only after a working product consumes it and a native
host test proves its behavior.

`OpenXrDebugPolicy.h` classifies OpenXR debug severity flags using only fixed-width
integers from the C++ standard library. Pico's OpenXR callback is the first real
consumer. A future modern `questInterface` OpenXR implementation should consume the
same policy by translating Meta runtime severity flags to the standard OpenXR flag
values; it must not fork or copy this classifier into the Quest product directory.

Vendor extension selection, device workarounds, logging destinations, and store or
runtime policy remain in the relevant child product. Shared policies must not
include Pico, Meta/Oculus, Qt, JNI, Android, OpenXR platform, or graphics headers.
