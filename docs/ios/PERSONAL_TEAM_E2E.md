<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# iOS E2E with a free Apple Personal Team

This is the no-paid-membership alternative to the protected signing producer.
GitHub builds only a credential-free unsigned kit. Apple account authentication,
provisioning, signing, and installation stay on a trusted local macOS or Windows
host and never enter Actions, Jenkins, the repository, or shared logs.

Apple documents the Personal Team limits as ten App IDs, three devices, three
installed apps per device, and seven-day App ID/device/profile lifetimes. Reusing
the same identifiers with the same Apple account avoids intentionally creating
new identifiers on every refresh, but it does not remove Apple's seven-day
reprovisioning requirement. The fixed identifiers are:

- Overte: `org.overte.interface.e2e`
- WDA runner application: `org.overte.WebDriverAgentRunner.xctrunner`
- nested WDA XCTest bundle: `org.overte.WebDriverAgentRunner`

These are the preferred stable bundle identities and install two applications.
Do not remove the WDA `PlugIns/WebDriverAgentRunner.xctest` bundle. If
Sideloadly cannot preserve the preferred IDs because the Personal Team's
short-lived App-ID quota is already occupied, the device-observed variant may
instead attest one uniquely marker-selected remapped Overte/WDA pair. The
exported-signed-IPA variant still requires the preferred fixed identities.

The registered `ios-bootstrap.yml` entrypoint calls
`ios-personal-team-e2e-kit.yml`. Its public seven-day artifact contains exactly:

```text
Overte-PersonalTeam-E2E-unsigned.ipa
WebDriverAgentRunner-16.8.0-PersonalTeam-unsigned.ipa
personal-team-e2e-kit.json
```

The manifest binds both unsigned files by SHA-256 and size to one source
revision and exact GitHub repository ID, bootstrap/reusable workflow, protected
ref, run ID and attempt. It also binds XCUITest Driver 12.8.0, WDA 16.8.0, the
three fixed identifiers, and the `overte-ios-personal-team-e2e-kit-v1` contract.
It declares
`derivationBinding: human-verified` and
`signedBytesDerivableFromUnsignedKit: false`: a re-signing tool changes bundle
metadata, entitlements, Mach-O signatures, profiles, and archive bytes, so the
signed result cannot be cryptographically derived from the unsigned hash.

## Variant A: Sideloadly installs directly

This is the smallest manual process. Sideloadly's documented **Apple ID
sideload** mode signs and installs an IPA on the selected device. Its separately
documented **Export IPA** mode exports a modified IPA; it must not be treated as
proof that the Personal-Team-signed installation bytes were exported.

1. On a trusted local machine, verify the downloaded Actions archive and the two
   file hashes and sizes in `personal-team-e2e-kit.json`.
2. In Sideloadly, select Apple ID sideload and the intended trusted device.
   Prefer the fixed identifiers. If Sideloadly remaps them, do not create extra
   duplicate installations and use the explicit remapped-attestation flag
   below. Never remove WDA's nested XCTest plug-in.
3. Install the Overte IPA and then the WDA IPA with the same Apple account.
   Credentials and two-factor codes remain solely in Sideloadly on that host.
4. Trust the resulting developer application and enable Developer Mode on the
   device when iOS requests it.
5. Fedora may proceed only after its `personal-team-preinstalled` hardware gate
   observes either both exact identities or exactly one unambiguous remapped
   Overte/WDA pair selected by the E2E and WDA version markers. It additionally
   requires InstallationProxy's `ProfileValidated` flag, valid application
   identifiers, and the same team and signer on an exclusively reserved
   iOS/iPadOS 18+ target. The resulting receipt binds the observed IDs, including
   a suffixless WDA through Appium's `updatedWDABundleIdSuffix` capability.
   The receipt binds the reviewed unsigned-kit manifest hash and private human
   attestation hash, but has no installed-IPA byte hash or derivation claim.
   Profile expiration and successful WDA launch remain explicit session/hardware
   gates. Appium uses the already installed WDA and therefore does not set
   `appium:prebuiltWDAPath` in this mode.

The file-backed Personal Team importer does not accept this variant. In
particular, do not copy a temporary Sideloadly work file and label it a signed
export. Device observation is a weaker but honest trust boundary and must remain
visibly distinct in the receipt and Jenkins job.

## Variant B: retain two signed IPA files

Use this path when Xcode Personal Team or another trusted local signing process
can retain the exact signed outputs. The files must be outside the checkout and
named exactly:

```text
Overte-PersonalTeam-E2E-signed.ipa
WebDriverAgentRunner-16.8.0-PersonalTeam-signed.ipa
```

The local signing process must preserve the three fixed bundle identifiers,
sign both the WDA runner and nested XCTest, embed profiles authorized for the
same Personal Team, and leave the Overte E2E plist contract enabled. Do not put
Apple credentials, certificates, private keys, profiles, device identifiers, or
signed IPAs in GitHub artifacts or the repository.

After visually reviewing that both outputs came from the downloaded kit, create
the private human-boundary record:

```bash
umask 077
chmod 0600 \
  /private/personal-team/Overte-PersonalTeam-E2E-signed.ipa \
  /private/personal-team/WebDriverAgentRunner-16.8.0-PersonalTeam-signed.ipa
python3 ios/ci/create-personal-team-signed-attestation.py \
  --unsigned-kit /private/personal-team/personal-team-e2e-kit.json \
  --overte-ipa /private/personal-team/Overte-PersonalTeam-E2E-signed.ipa \
  --wda-ipa /private/personal-team/WebDriverAgentRunner-16.8.0-PersonalTeam-signed.ipa \
  --output /private/personal-team/personal-team-signed-handoff.json \
  --i-accept-resigning-boundary \
  --signed-from-reviewed-kit \
  --same-personal-team
```

`/private/personal-team` must already be a symlink-free, current-user-owned
directory outside the checkout with mode 0700. All three acknowledgement flags
are mandatory. The resulting mode-0600 JSON is durably flushed before success,
valid for at most seven days, hashes only the files that actually exist, and says
`derivationBinding: human-verified`; it does not claim a cryptographic link from
signed bytes to unsigned bytes. The Fedora `local-import` command then performs
the strong checks: full IPA structure and hashes, Mach-O/CMS signatures,
profiles, entitlements, exact team/application/bundle identities, expiry,
Overte E2E contract, and WDA runner/nested-XCTest pairing. Its receipt and IPAs
remain private and short-lived outside the checkout.

Both variants need periodic Personal Team refresh. Sideloadly advertises an
automatic refresh facility, but enabling saved credentials or background
refresh is a personal local choice and is not part of Overte automation.

References:

- [Apple: Personal Team account limits](https://developer.apple.com/help/account/basics/about-your-developer-account)
- [Sideloadly: signing/install modes and free-account lifetime](https://sideloadly.io/)
- [Appium: running prebuilt WDA](https://appium.github.io/appium-xcuitest-driver/latest/guides/run-prebuilt-wda/)
