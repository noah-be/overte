# Android signing-key policy

No Android private key belongs in this repository.

## Repository keystore provenance

The former `android/common/keystore.jks` was not an Android debug keystore. Its
self-signed certificate carried a named legacy High Fidelity identity, and the
file contained a private-key entry. Repository history shows that it originated
under the legacy Quest client and was moved into a shared Android location by
commit `8802eeadf654e4ef2411961e19c8997067c36088` in 2019 for signed CI builds.
It moved to `android/common/keystore.jks` during the Android source
reorganization in commit `ce0e92cda2fb0b4804dc78dc8bc312349731f296`.

The file and its in-tree fallback credentials have therefore been removed.
Published Git history still contains them and must not be treated as a secure
key distribution mechanism.

## Debug builds

Debug builds use the Android Gradle plugin's normal per-developer debug key.
That disposable local key is generated outside the repository (normally below
the user's Android configuration directory), is not shared by CI, and must
never be promoted to an upload or release identity. A clean development
machine producing a different debug certificate is expected.

## Release builds

The legacy phone and Quest Gradle projects have no repository signing fallback.
Without all four external `HIFI_ANDROID_KEYSTORE*` /
`HIFI_ANDROID_KEY_ALIAS` properties they produce an unsigned release artifact.
Partial configuration and nonexistent keystore paths fail during Gradle
configuration. Release automation must supply a dedicated key from protected
CI or store-managed secret storage and verify the expected signer separately.

Do not copy a release keystore, password, key alias, certificate fingerprint,
or generated signing-properties file into the checkout.

## Required external follow-up

Removing the file does not rotate historical signing material. A release owner
must determine whether the former certificate signed any distributed APK or
store enrollment, then use the relevant Android store or distribution channel
to rotate or revoke it. Rotate every associated password and secret reference,
remove copies from CI and developer machines, and record the replacement
certificate through the protected release process. If it was never used for a
published application, explicitly record that finding before destroying the
remaining external copies.
