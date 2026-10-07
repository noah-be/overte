# Native FBX material audit

The [sanitized report](evidence/native-fbx-material-audit.json) records eight successful reads by the **shipping native** `FBXSerializer` and `graphics::Material` code: the actual bundled default mannequin, the actual Kim avatar, and six generated raw FBX contract fixtures. All eight exited 0 and passed their numeric and filename-binding assertions; six negative controls rejected the incorrect factor-reset behavior on 2026-10-01, 00:20:09.304–00:20:12.684 UTC.

This is an offline CPU parser audit. It starts a `QCoreApplication` without a GPU context, event loop, server, or network request. It does not load texture images, classify their GPU alpha flags, show the corrected browser avatar, or prove visual equivalence. Public material names and texture basenames are retained; operator paths, participant identifiers, credentials and private compiler/stderr logs are omitted.

## Reproducer

The tool compiles only a small read-only C++ shim against the existing checked native package. It does not rebuild Overte or download dependencies. Supply the reviewed April package, its matching Qt 5.15.3 development headers, existing GLM 0.9.9.5 headers, and a repository containing the pinned `f91d15a08587dcd37c642234424b3215dd331724` revision. The tool checks all four linked native-library SHA-256 values before compilation and checks the actual Qt/GLM versions returned by the shim.

Set `OVERTE_REPOSITORY`, `OVERTE_APPIMAGE_ROOT`, `OVERTE_QT_INCLUDE`, `OVERTE_GLM_INCLUDE`, and `OVERTE_KIM_FBX` to those locally reviewed resources. From the browser-client directory run:

```sh
python3 lab/audit-native-fbx.py \
  --repository "$OVERTE_REPOSITORY" \
  --native-libs "$OVERTE_APPIMAGE_ROOT/usr/lib" \
  --qt-include "$OVERTE_QT_INCLUDE" \
  --glm-include "$OVERTE_GLM_INCLUDE" \
  --output /tmp/overte-native-fbx-audit \
  --input "default-mannequin=$OVERTE_REPOSITORY/browser-client/public/default-avatar/mannequin/mannequin.fbx" \
  --input "kim=$OVERTE_KIM_FBX" \
  --synthetic
```

The audited mannequin is 3,655,100 bytes (`e247f3342ff109e17f7ae90916f81935d17ff4f51f60c60908094bb4f38db7da`); Kim is 3,062,028 bytes (`9234bbeaa13b09bdeafb3e0b811da7427d245f278a50470b01af569adb56670f`). Assertions for these two assets activate only when the exact reviewed SHA matches. Other explicitly supplied inputs are parsed and reported, without claiming the known-avatar contract checks.

Successful stdout is `{"passedNativeParserInputs": 8, "syntheticContractInputs": 6}`. Keep the output directory private: compile arguments and native stderr may contain local paths. Its `report.json` is sanitized; the curated report also explains the resolved bootstrap error and the limits of this proof.

The final compiler was GCC 16.2.1; Qt reports 5.15.3 and GLM reports 995 (0.9.9.5). The three native ABI definitions are mandatory: `GLM_FORCE_CTOR_INIT`, `GLM_FORCE_RADIANS`, and `GLM_ENABLE_EXPERIMENTAL`. The first diagnostic shim omitted `GLM_FORCE_CTOR_INIT` and crashed at `graphics::Material::getAlbedo` because of a GLM return-value ABI mismatch. Correcting the shim resolved that harness defect; it is not evidence of a native parser defect.

## Observations

- **Kim:** all twelve non-PBS materials have authored opacity 0, but the actual native graphics material has opacity 1. Each opacity filename matches its albedo filename. A browser that directly keeps authored zero opacity diverges from the native consolidation; whether the resulting browser fix is visible still needs an actual browser run.
- **Default mannequin:** `lambert1` has diffuse RGB 0.5 and diffuse factor 0.8; effective sRGB is approximately 0.400006, roughness 0.77, and metallic 0.02. `StingrayPBS10` preserves its roughness map and 0.33 roughness. `phong2` is PBS with metallic 0.5.
- **Generated raw FBX:** a `DiffuseFactor` texture behaves as a diffuse texture. The last connection selects the final albedo filename, while the numeric factor remains 0.5. Reversing connection order changes the filename; a factor-only connection does not reset the scalar to 1.
- **Generated raw FBX:** PBS forces the opacity filename to the diffuse filename even when a distinct transparency texture is connected. Non-PBS preserves the distinct transparency filename. Stingray debug `use_*_map = 0` does not remove actual bindings; its positive authored roughness 0.2 reaches the native material unchanged.

The primary pinned [connection parser](https://github.com/noah-be/overte/blob/f91d15a08587dcd37c642234424b3215dd331724/libraries/model-serializers/src/FBXSerializer.cpp#L1148) lowercases the connection name before testing a mixed-case `DiffuseFactor` condition; that condition is unreachable. These actual binary probes confirm the resulting behavior rather than assuming the adjacent fallback comment describes the executed path. The [material consolidation](https://github.com/noah-be/overte/blob/f91d15a08587dcd37c642234424b3215dd331724/libraries/model-serializers/src/FBXSerializer_Material.cpp#L218) multiplies diffuse by its factor, derives non-PBS roughness from shininess and metallic from specular color, preserves positive PBS roughness (otherwise falling back to shininess), and maps authored opacity values at or below zero to effective opacity 1.

No endurance test was run, following the user's cancellation. These new files and results exist only in the writable continuation snapshot; the original branch remains unchanged while platform permissions prevent writing it. AI assistance was substantial in the shim, reproducer, audit and documentation.
