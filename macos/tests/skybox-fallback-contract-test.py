#!/usr/bin/env python3
"""Require a valid cubemap while a production skybox texture is pending."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "libraries/graphics/src/graphics/Skybox.cpp"

source = SOURCE.read_text(encoding="utf-8")
fallback_start = source.index("const gpu::TexturePointer& getFallbackCubemap()")
constructor_start = source.index("\nSkybox::Skybox()", fallback_start)
fallback = source[fallback_start:constructor_start]

required_fallback_fragments = (
    "gpu::Texture::createCubeStrict",
    "gpu::Element::COLOR_RGBA_32",
    "face < 6",
    "assignStoredMipFace",
)
for fragment in required_fallback_fragments:
    if fragment not in fallback:
        raise SystemExit(f"skybox fallback is missing: {fragment}")

prepare_start = source.index("void Skybox::prepare(gpu::Batch& batch) const")
render_start = source.index("\nvoid Skybox::render(", prepare_start)
prepare = source[prepare_start:render_start]

fallback_condition = prepare.index("if (!skymap || !skymap->isDefined())")
fallback_assignment = prepare.index("skymap = getFallbackCubemap()")
binding = prepare.index(
    "batch.setResourceTexture(graphics::slot::texture::Skybox, skymap)"
)
if not fallback_condition < fallback_assignment < binding:
    raise SystemExit(
        "Skybox::prepare must replace a missing or pending cubemap before binding"
    )

if prepare.count(
    "batch.setResourceTexture(graphics::slot::texture::Skybox, skymap)"
) != 1:
    raise SystemExit("Skybox::prepare must bind exactly one valid cubemap")

print("skybox pending-texture fallback contract valid")
