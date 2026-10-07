"""Attribution evidence integrity; no automatic compatibility or ownership opinion."""
# SPDX-License-Identifier: Apache-2.0
import re

ASSET_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".bmp", ".ico", ".icns",
    ".ktx", ".ktx2", ".dds", ".tga", ".ttf", ".otf", ".woff", ".woff2", ".eot", ".arfont",
    ".wav", ".mp3", ".ogg", ".flac", ".aiff", ".m4a", ".mp4", ".webm", ".mov",
    ".fbx", ".gltf", ".glb", ".obj", ".mtl", ".fst", ".blend", ".usdz",
}


def is_license_file(name):
    return bool(re.search(r"(?i)license|copying|notice|attribution|copyright|(?:^|[._-])OFL(?:[._-]|$)", name))


def attribution_problems(record, asset, hashes):
    problems = []
    if not hashes.get(asset) or record.get("sha256") != hashes[asset]:
        problems.append("missing-or-stale-asset-hash")
    for field in ("license", "source", "copyright"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip() or value.strip().upper() == "UNKNOWN":
            problems.append("missing-" + field)
    notice = record.get("noticeFile")
    if not isinstance(notice, str) or not hashes.get(notice):
        problems.append("missing-tracked-notice")
    elif record.get("noticeSha256") != hashes[notice]:
        problems.append("missing-or-stale-notice-hash")
    return problems
