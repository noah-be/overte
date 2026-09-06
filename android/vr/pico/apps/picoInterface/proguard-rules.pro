# Native Qt/OpenXR entry points are reached through JNI.
-keepclasseswithmembers class * {
    native <methods>;
}
-keep class org.overte.pico.PicoAccountStoreBridge { *; }
-keep class org.overte.pico.PicoAccountStoreBridge$ReadResult { *; }
