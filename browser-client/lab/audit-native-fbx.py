#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a small ABI-matched shim and audit installed native FBX material values.

No downloads, servers, GPU context, or repository mutations. Inputs are operator-
reviewed local resources. Keep the output directory private; only report.json is
sanitized for publication. The native library parses raw, bounded FBX files.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess
import tarfile

HEADER_REVISION = "f91d15a08587dcd37c642234424b3215dd331724"
MAX_INPUT = 32 * 1024 * 1024
ABI_DEFINES = ("GLM_FORCE_CTOR_INIT", "GLM_FORCE_RADIANS", "GLM_ENABLE_EXPERIMENTAL")
NATIVE_LIBRARIES = {
    "libmodel-serializers.so": "310a4523168ebcd4b2b7149c881773197caa92bc158a6381acbc1ecc3a050f81",
    "libhfm.so": "abc8af44118c6de0aff44c4486386835c3de455aa53168d9f8fee998bf7c2b7c",
    "libgraphics.so": "7b33325f9c2da8ac55ed435522ab8b769096f55fb36fa809eac247c627bcabc7",
    "libQt5Core.so.5": "7d17398326dd44b442d2ea9f3b28d37ed5dbc71766ee13591a8816c4ddecbc66",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def synthetic_fixtures() -> dict[str, str]:
    base = ('P: "DiffuseColor", "Color", "", "A", .2,.4,.6\n'
            'P: "DiffuseFactor", "Number", "", "A", .5\n'
            'P: "Opacity", "Number", "", "A", 0\n')
    cases = {
        "factor-after-color": ([(301, "DiffuseColor"), (302, "DiffuseFactor")], ""),
        "color-after-factor": ([(302, "DiffuseFactor"), (301, "DiffuseColor")], ""),
        "factor-only": ([(302, "DiffuseFactor")], ""),
        "pbs-alpha-overrides-other": ([(301, "DiffuseColor"), (303, "TransparentColor")],
                                      'P: "ReflectionFactor", "Number", "", "A", .7\n'),
        "stingray-disabled-debug-map": ([(301, "Maya|TEX_color_map"), (304, "Maya|TEX_roughness_map")],
                                       'P: "Maya|use_color_map", "Number", "", "A", 0\n'
                                       'P: "Maya|use_roughness_map", "Number", "", "A", 0\n'
                                       'P: "Maya|roughness", "Number", "", "A", .2\n'),
        "ordinary-other-opacity": ([(301, "DiffuseColor"), (303, "TransparentColor")], ""),
    }
    result = {}
    for label, (connections, extra) in cases.items():
        textures = "\n".join(
            f'Texture: {key}, "Texture::Audit{key}", "TextureVideoClip" {{\n'
            f' RelativeFilename: "{filename}"\n}}'
            for key, filename in [(301, "color.png"), (302, "factor.png"),
                                  (303, "other-alpha.png"), (304, "roughness.png")])
        bindings = "\n".join(f'C: "OP",{key},101,"{channel}"' for key, channel in connections)
        result[label] = ('; FBX 7.4\nObjects: {\nMaterial: 101, "Material::Audit", "" {\n'
                         'ShadingModel: "phong"\nProperties70: {\n' + base + extra +
                         '}\n}\n' + textures + '\n}\nConnections: {\n' + bindings + '\n}\n')
    return result


def check_fixture(label: str, result: dict) -> None:
    assert result["qtVersion"] == "5.15.3", "Native Qt ABI version changed"
    assert result["glmVersion"] == 995, "Native GLM ABI version changed"
    assert result["meshes"] == 0 and len(result["materials"]) == 1
    material = result["materials"][0]
    assert math.isclose(material["diffuseFactor"], .5, abs_tol=1e-7)
    assert material["opacity"] == 0 and material["effectiveOpacity"] == 1
    assert all(math.isclose(value, expected, abs_tol=1e-4)
               for value, expected in zip(material["effectiveAlbedoSRGB"], [.1, .2, .3], strict=True))
    expected_albedo = "factor.png" if label in {"factor-after-color", "factor-only"} else "color.png"
    assert material["albedoTexture"] == expected_albedo
    pbs = label in {"pbs-alpha-overrides-other", "stingray-disabled-debug-map"}
    assert material["pbs"] is pbs
    expected_opacity = "color.png" if pbs else "other-alpha.png" if label == "ordinary-other-opacity" else ""
    assert material["opacityTexture"] == expected_opacity
    if label == "pbs-alpha-overrides-other":
        assert math.isclose(material["effectiveMetallic"], .7, abs_tol=1e-6)
    if label == "stingray-disabled-debug-map":
        assert material["roughnessTexture"] == "roughness.png"
        assert not material["useAlbedoMapDebug"] and not material["useRoughnessMapDebug"]
        assert math.isclose(material["effectiveRoughness"], .2, abs_tol=1e-6)


def check_known_avatar(input_sha: str, result: dict) -> bool:
    """Assert numeric/binding contracts only for these exact reviewed asset bytes."""
    materials = result["materials"]
    if input_sha == "9234bbeaa13b09bdeafb3e0b811da7427d245f278a50470b01af569adb56670f":
        assert result["meshes"] == 12 and len(materials) == 12
        assert all(material["opacity"] == 0 and material["effectiveOpacity"] == 1 and not material["pbs"]
                   and material["albedoTexture"] and material["opacityTexture"] == material["albedoTexture"]
                   for material in materials)
        return True
    # The fork normalization only changes skin weights; material bindings are unchanged.
    if input_sha in {"e247f3342ff109e17f7ae90916f81935d17ff4f51f60c60908094bb4f38db7da",
                     "b9ca9d23f488bbc579968708895c8d998a0e49a5f24cbfc25157ffaebf14d7a8"}:
        assert result["meshes"] == 2 and len(materials) == 3
        by_name = {material["name"]: material for material in materials}
        lambert = by_name["lambert1"]
        assert not lambert["pbs"] and math.isclose(lambert["diffuseFactor"], .8, abs_tol=1e-6)
        assert all(math.isclose(value, .4, abs_tol=1e-4) for value in lambert["effectiveAlbedoSRGB"])
        assert math.isclose(lambert["effectiveRoughness"], .77, abs_tol=1e-6)
        assert math.isclose(lambert["effectiveMetallic"], .02, abs_tol=1e-6)
        stingray = by_name["StingrayPBS10"]
        assert stingray["pbs"] and stingray["albedoTexture"] == stingray["opacityTexture"] == "StingrayPBS10_Base_Color.png"
        assert stingray["roughnessTexture"] == "lambert1_Roughness.png"
        assert math.isclose(stingray["effectiveRoughness"], .33, abs_tol=1e-6)
        assert all(material["effectiveOpacity"] == 1 for material in materials)
        return True
    return False


def validate_report(value: object) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            validate_report(nested)
    elif isinstance(value, list):
        for nested in value:
            validate_report(nested)
    elif isinstance(value, float):
        assert math.isfinite(value), "Native parser returned a non-finite numeric value"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("repository", "native-libs", "qt-include", "glm-include", "output"):
        parser.add_argument("--" + option, required=True, type=Path)
    parser.add_argument("--input", action="append", default=[], metavar="PUBLIC_LABEL=LOCAL_FBX")
    parser.add_argument("--synthetic", action="store_true", help="Verify six generated raw FBX contract fixtures")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = utc()
    shim = Path(__file__).with_suffix(".cpp")
    native_hashes = {name: sha256(args.native_libs / name) for name in NATIVE_LIBRARIES}
    assert native_hashes == NATIVE_LIBRARIES, "Require the reviewed shipping native library bytes"
    assert re.search(r'GLM_VERSION_MESSAGE\s+"GLM: version 0\.9\.9\.5"', (args.glm_include / "glm/detail/setup.hpp").read_text()), "Require GLM 0.9.9.5"
    names = subprocess.check_output(["git", "-C", str(args.repository), "ls-tree", "-r", "--name-only",
                                     HEADER_REVISION, "libraries"], timeout=30).decode().splitlines()
    headers = [name for name in names if name.endswith((".h", ".hpp"))]
    archive = subprocess.check_output(["git", "-C", str(args.repository), "archive", HEADER_REVISION, *headers], timeout=30)
    assert len(archive) <= MAX_INPUT, "Bound native header export"
    source = output / "headers"
    with tarfile.open(fileobj=io.BytesIO(archive)) as package:
        for member in package.getmembers():
            target = source / member.name
            assert target.resolve().is_relative_to(source.resolve())
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                assert member.isfile() and member.name in headers and member.size <= MAX_INPUT
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(package.extractfile(member).read())
    binary = output / "native-fbx-audit"
    command = ["g++", "-std=c++17", "-fPIC", "-O0", *["-D" + define for define in ABI_DEFINES]]
    for include in [args.glm_include, args.qt_include, *[args.qt_include / module for module in ("QtCore", "QtGui", "QtNetwork")],
                    *sorted((source / "libraries").glob("*/src"))]:
        command += ["-I", str(include)]
    command += [str(shim), "-o", str(binary), "-L", str(args.native_libs), "-lmodel-serializers", "-lhfm", "-lgraphics",
                str(args.native_libs / "libQt5Core.so.5"), "-Wl,-rpath," + str(args.native_libs),
                "-Wl,-rpath-link," + str(args.native_libs)]
    write_json(output / "compile-private.json", command)
    compiled = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    (output / "compile-private.log").write_bytes(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, "Native audit shim compilation failed; inspect private compile log"
    inputs = []
    for value in args.input:
        label, separator, path = value.partition("=")
        assert separator and re.fullmatch(r"[a-zA-Z0-9-]{1,64}", label), "Require an explicit public label"
        inputs.append((label, Path(path), "operator-reviewed-native-FBX"))
    if args.synthetic:
        fixture_dir = output / "fixtures"
        fixture_dir.mkdir(exist_ok=True)
        for label, contents in synthetic_fixtures().items():
            fixture = fixture_dir / (label + ".fbx")
            fixture.write_text(contents)
            inputs.append((label, fixture, "synthetic-raw-FBX-contract"))
    assert inputs, "Specify an operator-reviewed input or --synthetic"
    assert len({label for label, _, _ in inputs}) == len(inputs), "Input labels must be unique"
    reports = []
    for label, path, kind in inputs:
        assert 0 < path.stat().st_size <= MAX_INPUT, "FBX input exceeds 32 MiB or is empty"
        input_started = utc()
        audited = subprocess.run([str(binary), str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        (output / (label + "-private-stderr.log")).write_bytes(audited.stderr)
        assert audited.returncode == 0, f"Native parser failed for public input label {label}; inspect private stderr"
        result = json.loads(audited.stdout)
        validate_report(result)
        result["materials"].sort(key=lambda material: material["name"])
        assert result["qtVersion"] == "5.15.3" and result["glmVersion"] == 995
        input_sha = sha256(path)
        known_avatar = check_known_avatar(input_sha, result)
        if kind == "synthetic-raw-FBX-contract":
            check_fixture(label, result)
            # The older guessed factor-reset behavior must fail the comparator.
            incorrect = copy.deepcopy(result)
            incorrect["materials"][0]["diffuseFactor"] = 1
            try:
                check_fixture(label, incorrect)
            except AssertionError:
                pass
            else:
                raise RuntimeError("Contract comparator accepted incorrect factor-reset behavior")
        reports.append({"label": label, "kind": kind, "bytes": path.stat().st_size, "sha256": input_sha,
                        "started": input_started, "completed": utc(), "exitCode": audited.returncode,
                        "contractChecksPassed": kind == "synthetic-raw-FBX-contract" or known_avatar, "result": result})
    report = {"schemaVersion": 1, "scope": "Actual shipping native CPU FBX parser and graphics material values; no GPU, texture loading, browser visibility or network proof",
              "started": started, "completed": utc(), "headerRevision": HEADER_REVISION, "headerCount": len(headers),
              "abiDefines": ABI_DEFINES, "compiler": subprocess.check_output(["g++", "--version"]).decode().splitlines()[0],
              "sourceHashes": {shim.name: sha256(shim), Path(__file__).name: sha256(Path(__file__))},
              "nativeLibraryHashes": native_hashes,
              "negativeControlChecksPassed": sum(item["kind"] == "synthetic-raw-FBX-contract" for item in reports),
              "inputs": reports}
    write_json(output / "report.json", report)
    print(json.dumps({"passedNativeParserInputs": len(reports), "syntheticContractInputs": sum(item["kind"] == "synthetic-raw-FBX-contract" for item in reports)}))


if __name__ == "__main__":
    main()
