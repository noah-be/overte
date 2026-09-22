# Android Phone fork icon

`launcher-navy.svg` is the unchanged `LOGO_Overte_Navy.svg` supplied by the fork
maintainer for distinguishing this Android app from the official Overte app.
The supplied palette identifies Navy as `#2a4d85`; the Deep Magenta variant is
not used here. This records the supplied source, not a new license grant.

The Phone launcher drawable at
`../apps/phoneInterface/src/main/res/drawable/ic_launcher.xml` represents the
same circle, white path, viewport and translation as an Android vector. Both
the application manifest and the Android 12+ splash screen use that drawable.

The 512×512 transparent F-Droid store PNG is rendered directly from the SVG,
without redesigning it. From the repository root, using ImageMagick:

```sh
magick -background none -density 900 android/phone/branding/launcher-navy.svg \
  -resize 512x512 -strip \
  PNG32:android/phone/fastlane/metadata/android/en-US/images/icon.png
```

The submission regression suite checks the Phone resource references and the
vector's source geometry/color. Review the rendered PNG when changing this
artwork. A resource compilation check with Android SDK `aapt2` validates the
Android XML. This change is confined to Android Phone branding and store assets.
