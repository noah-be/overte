# Pico 4 distribution readiness

Checked against public vendor documentation on 2026-08-09. Portal-only limits
and contract terms must be rechecked by the release owner immediately before a
submission; this document is not store approval.

## One candidate, several channels

The signed `org.overte.pico` arm64 APK can be the common candidate for PICO
Consumer Store, PICO Business Store, a third-party store, direct download and
ADB installation only when a channel accepts an ordinary signed APK without
re-signing it. Never rebuild per channel after acceptance. If a distributor
re-signs an APK, treat its output as a different artifact and test it again.

Android accepts an in-place update only when application ID and signing
certificate match and the new version code is not lower. Consequently the
release certificate, package name and version-code allocation are permanent
cross-channel product decisions. Do not enroll a store in a signing service
that prevents use of the same certificate elsewhere without first deciding
that cross-channel updates are intentionally unsupported.

## PICO Store readiness

PICO's public distribution flow requires a developer account, a reviewed
individual or company organization, creation of an app, upload of the APK to a
Consumer or Business release channel, metadata, and review. Paid distribution
also requires payment information and the applicable distribution agreement.
PICO documents a typical review time of five to seven working days. Updates
must have a higher bundle version code and the same application signature.

Before the first submission, a release owner must verify in the authenticated
PICO Developer Platform:

- ownership and availability of the package name `org.overte.pico`;
- whether the approximately 500 MB APK is below the current channel limit or
  requires an expansion-file/content-delivery arrangement;
- supported PICO 4 regions, OS versions, controller/input declarations and
  required platform SDK or entitlement metadata;
- permissions, network endpoints, account/login behavior, user-generated
  content moderation, age rating and comfort/safety declarations;
- localized title, description, icons, screenshots, trailer, support contact,
  privacy policy and data-processing disclosures;
- open-source trademark authorization and all bundled-content licenses;
- whether PICO preserves the uploaded signing certificate.

Public PICO references:

- <https://developer.picoxr.com/document/unity/publish-you-app-overview/>
- <https://developer.picoxr.com/document/distribute/update-your-app/>
- <https://developer.picoxr.com/document/distribute/content-review-for-non-mainland-china>

## Direct APK and alternative stores

Direct distribution is technically supported by Android using a release-ready
APK. Interactive installation requires the user to permit the relevant source;
ADB installation remains a developer path. Each third-party store must be
checked for APK size, supported headsets, package ownership, signing behavior,
privacy/listing requirements and whether it hosts the original bytes. No
specific alternative store is approved by this repository merely because it
can ingest an APK.

Android developer verification is being rolled out during 2026 and 2027. For
wide non-Play distribution, plan to verify the publishing organization and
register `org.overte.pico` with proof based on the final signing key. ADB remains
available for development, but it is not a consumer distribution strategy.

Public Android references:

- <https://developer.android.com/studio/publish/app-signing>
- <https://developer.android.com/google/play/app-updates>
- <https://developer.android.com/distribute/marketing-tools/alternative-distribution>
- <https://developer.android.com/developer-verification/guides>
- <https://developer.android.com/tools/adb>

## Go/no-go evidence

For every channel, retain the immutable tag, commit, original APK digest,
certificate fingerprint, APK manifest, SBOM, dependency checksums, device
acceptance report, submitted store artifact digest and store review result. A
release is not ready while any portal-only item above remains unknown.
