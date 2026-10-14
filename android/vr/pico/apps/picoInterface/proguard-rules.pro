# Native Qt/OpenXR entry points are reached through JNI.
-keepclasseswithmembers class * {
    native <methods>;
}
-keep class org.overte.pico.PicoAccountStoreBridge { *; }
-keep class org.overte.pico.PicoAccountStoreBridge$ReadResult { *; }
# These readiness methods are called by JNI, outside Java reachability.
-keep class org.overte.pico.PicoNativeDocumentHost {
    static boolean nativeBindingsReady(java.lang.Object);
}
-keep class org.overte.pico.PicoClientVisibility {
    static boolean nativeBindingsReady(java.lang.Object);
}
