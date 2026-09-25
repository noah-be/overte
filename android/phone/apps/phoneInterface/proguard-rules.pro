# Qt 5 loads bindings/delegates by name and calls Java members through JNI and
# reflection. Those native entry points are not visible to R8's Java call graph.
-keep class org.qtproject.qt5.android.** { *; }

# QtApplication dispatches Activity methods reflectively; PhoneUrlHandler.cpp
# also exports Java_org_overte_phone_PhoneInterfaceActivity_* JNI entry points.
-keep class org.overte.phone.PhoneInterfaceActivity { *; }

# PhoneProtectedStoreRegistration.cpp resolves preparedStore by class/name;
# PhoneProtectedAccountStore.cpp resolves these instance methods from JNI.
-keep,includedescriptorclasses class org.overte.phone.SecureAccountStore {
    private static org.overte.phone.SecureAccountStore preparedStore();
    public byte[] read();
    public void write(byte[]);
    public void clear();
}

# Native exception handling calls this method without a Java call site.
-keep class org.overte.phone.SecureAccountStore$StoreException {
    public int nativeFailure();
}
