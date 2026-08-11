# Native Qt/OpenXR entry points are reached through JNI.
-keepclasseswithmembers class * {
    native <methods>;
}

