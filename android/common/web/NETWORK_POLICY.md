# Embedded browser network capability

Normal embedded documents support HTTP and HTTPS. Android WebView observes the
application's cleartext policy for targets 26 and later; Network Security Config
takes precedence on Android 24 and later. There is no public per-WebView policy
for arbitrary HTTP hosts. This module therefore declares the honest application
scope in `network-capability.json`, rather than presenting an ignored manifest
flag or a partial request proxy as isolation.

Each product must explicitly select the shared resource and capability:

```xml
<application android:usesCleartextTraffic="true"
    android:networkSecurityConfig="@xml/overte_embedded_web_network_security_config">
    <meta-data android:name="org.overte.web.NETWORK_CAPABILITY"
        android:value="overte.android.embedded-web.http-https.v1" />
</application>
```

`target.gradle` supplies the resource. No consumer manifest is rewritten by the
module. The resource keeps only system certificate authorities and does not add
user CAs, custom TLS trust, or debug overrides. Existing SSL-error cancellation,
mixed-content denial, frame/origin/source/lifetime fences and file restrictions
remain separate browser enforcement.

The capability permits cleartext for Android's application-scoped high-level
network stacks. It is not a claim that HTTP is restricted to one browser view.
Native Qt/OpenSSL/socket transports do not gain HTTPS enforcement from this XML;
the independent Main-owned credential policy and its actual tests are required
before credential transport is qualified. Browser HTTP/release/device acceptance
remains open until those independently reviewed changes are integrated.

`network_policy.py` validates the explicit consumer declaration, exact capability
schema, and actual source resource. Packaged validation resolves the selected
resource ID and all configuration variants from AAPT's actual inventory. This
also covers optimized filenames such as `res/a.xml`; every selected file must be
decoded with `apkanalyzer resources xml` and validated. Source XML alone cannot
qualify a packaged artifact or an actual device WebView.

Android's authoritative behavior is documented in
[the application manifest reference](https://developer.android.com/guide/topics/manifest/application-element#usesCleartextTraffic)
and [Network Security Configuration](https://developer.android.com/privacy-and-security/security-config).
The [WebViewClient reference](https://developer.android.com/reference/android/webkit/WebViewClient#shouldInterceptRequest(android.webkit.WebView,%20android.webkit.WebResourceRequest))
also documents interception's redirect limits; an interception shim would not
preserve complete browser request and media behavior.
