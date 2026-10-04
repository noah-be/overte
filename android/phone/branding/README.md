# Android Phone fork icon

`launcher-deep-magenta.svg` is the unmodified `LOGO_Overte_DeepMagenta.svg`
supplied to the fork maintainer. Its background is Deep Magenta `#a12371`.
The Android launcher and splash drawable use the same geometry and color;
the 512×512 Fastlane PNG is rendered from this source.

On 2026-10-04, the maintainer confirmed that Overte supplied the purple logo
and authorized its use for this Android client, and separately confirmed
permission for the name "Overte Mobile (Unofficial)". This records the
maintainer's statement, not an independently verified public permission
letter or a general trademark license. No private correspondence is included.

The 0.1.2 source actually used the Navy variant (`#2a4d85`). This local
follow-up selects the supplied Deep Magenta artwork that the maintainer
identified as authorized. App ID, Java/JNI namespace and signing identity
are unchanged; no change to the published 0.1.2 APK is implied.

Render the store icon from the repository root:

```sh
magick -background none -density 900 android/phone/branding/launcher-deep-magenta.svg \
  -resize 512x512 -strip \
  PNG32:android/phone/fastlane/metadata/android/en-US/images/icon.png
```

`android/phone/fdroid/submission/test_submission.py` verifies source geometry,
color, name and launcher/splash references. Android SDK `aapt2 compile`
checks the drawable resource. The app remains an unofficial client and
makes no claim of endorsement by Overte e.V.
