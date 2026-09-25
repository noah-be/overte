#!/usr/bin/env python3
"""Offline checks for all current workspace Markdown links and anchors.

Remote URLs (including links to other branches) are never fetched. The parser
handles balanced inline links, reference links, HTML links/anchors, ATX/Setext
headings, fenced/indented code and comments without third-party dependencies.
"""
from __future__ import annotations

import argparse
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import unicodedata
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def blank(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group())


def prose(text: str) -> str:
    """Remove code/comments while retaining rendered list and quote content."""
    text = re.sub(r"<!--.*?-->", blank, text, flags=re.S)
    result = []
    fence = None
    list_indents = []
    previous_quote = 0
    for original in text.splitlines(keepends=True):
        line = original.expandtabs(4)
        quote = 0
        while re.match(r"^ {0,3}> ?", line):
            line = re.sub(r"^ {0,3}> ?", "", line, count=1)
            quote += 1
        if line.strip() and quote != previous_quote:
            fence = None
            list_indents = []
        previous_quote = quote
        indentation = len(line) - len(line.lstrip(" "))
        if line.strip():
            while list_indents and indentation < list_indents[-1]:
                list_indents.pop()
        item = re.match(r"^( *)(?:[-+*]|[0-9]+[.)])([ \t]+)(.*)", line)
        if item and not fence and (indentation <= 3 or list_indents and indentation < list_indents[-1] + 4):
            content_indent = item.start(3)
            list_indents.append(content_indent)
            line = line[content_indent:]
        elif list_indents:
            line = line[list_indents[-1]:]
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if re.match(r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$", line):
                fence = None
            result.append(re.sub(r"[^\n]", " ", original))
        elif match:
            fence = match[1]
            result.append(re.sub(r"[^\n]", " ", original))
        elif line.startswith("    "):
            result.append(re.sub(r"[^\n]", " ", original))
        else:
            result.append(line)
    return "".join(result)


def without_inline_code(text: str) -> str:
    return re.sub(r"(`+)(?!`)(.*?)(?<!`)\1(?!`)", blank, text, flags=re.S)


def label_key(value: str) -> str:
    return " ".join(value.split()).casefold()


def destination(text: str, start: int, closing: bool = True) -> tuple[str, int] | None:
    """Read escaped/balanced destinations and optional quoted link titles."""
    i = start
    while i < len(text) and text[i].isspace():
        i += 1
    if i == len(text):
        return None
    angled = text[i] == "<"
    if angled:
        i += 1
    result = []
    depth = 0
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            result.append(text[i + 1])
            i += 2
            continue
        if angled and char == ">":
            i += 1
            break
        if not angled:
            if char == "(":
                depth += 1
            elif char == ")":
                if not depth:
                    break
                depth -= 1
            elif char.isspace() and not depth:
                break
        result.append(char)
        i += 1
    if depth or (angled and (not i or text[i - 1] != ">")):
        return None
    if not closing:
        return unescape("".join(result)), i
    while i < len(text) and text[i].isspace():
        i += 1
    if i < len(text) and text[i] in "\"'(":
        quote = ")" if text[i] == "(" else text[i]
        i += 1
        while i < len(text) and text[i] != quote:
            i += 2 if text[i] == "\\" else 1
        i += 1
        while i < len(text) and text[i].isspace():
            i += 1
    return (unescape("".join(result)), i + 1) if i < len(text) and text[i] == ")" else None


class HtmlLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, int]] = []
        self.anchors: set[str] = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ("href", "src"):
            if attrs.get(key):
                self.links.append((attrs[key], self.getpos()[0]))
        for key in ("id", "name" if tag == "a" else "id"):
            if attrs.get(key):
                self.anchors.add(attrs[key])


def links(text: str) -> list[tuple[str, int]]:
    visible = without_inline_code(prose(text))
    definitions = {}
    pattern = re.compile(r"^ {0,3}\[([^\]\n]+)\]:\s*(.+)$", re.M)
    for match in pattern.finditer(visible):
        parsed = destination(match[2], 0, closing=False)
        if parsed:
            definitions.setdefault(label_key(match[1]), parsed[0])
    visible = pattern.sub(blank, visible)
    result = []
    i = 0
    while i < len(visible):
        if visible[i] == "\\":
            i += 2
            continue
        if visible[i] != "[":
            i += 1
            continue
        start = i
        depth = 1
        i += 1
        while i < len(visible) and depth:
            if visible[i] == "\\":
                i += 2
                continue
            depth += (visible[i] == "[") - (visible[i] == "]")
            i += 1
        if depth:
            i = start + 1
            continue
        label = visible[start + 1:i - 1]
        target = None
        if i < len(visible) and visible[i] == "(":
            parsed = destination(visible, i + 1)
            if parsed:
                target, i = parsed
        elif i < len(visible) and visible[i] == "[":
            end = visible.find("]", i + 1)
            if end >= 0:
                target = definitions.get(label_key(visible[i + 1:end] or label))
                i = end + 1
        else:
            target = definitions.get(label_key(label))
        if target is not None:
            line = visible.count("\n", 0, start) + 1
            result.append((target, line))
            if "[" in label:
                result.extend((nested, line + offset - 1) for nested, offset in links(label))
        else:
            i = start + 1
    html = HtmlLinks()
    html.feed(visible)
    return result + html.links


def heading_slug(value: str) -> str:
    value = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"!?\[([^\]]+)\]\[[^\]]*\]", r"\1", value)
    value = re.sub(r"<[^>]*>", "", value)
    value = unescape(value).strip().lower()
    value = "".join(char for char in value if char in "_-" or not unicodedata.category(char).startswith(("P", "S", "C")))
    return re.sub(r"\s", "-", value)


def anchors(text: str, markdown: bool = True) -> set[str]:
    visible = prose(text) if markdown else text
    html = HtmlLinks()
    html.feed(without_inline_code(visible) if markdown else visible)
    found = set(html.anchors)
    if not markdown:
        return found
    counts: dict[str, int] = {}
    lines = visible.splitlines()
    for index, line in enumerate(lines):
        atx = re.match(r"^ {0,3}#{1,6}\s+(.+?)(?:\s+#+\s*)?$", line)
        setext = index + 1 < len(lines) and re.fullmatch(r" {0,3}(?:=+|-+)\s*", lines[index + 1])
        if atx or (setext and line.strip() and not re.match(r"\s*(?:[-*+] |>|#{1,6} )", line)):
            slug = heading_slug(atx[1] if atx else line)
            number = counts.get(slug, 0)
            candidate = f"{slug}-{number}" if number else slug
            while candidate in found:
                number += 1
                candidate = f"{slug}-{number}"
            found.add(candidate)
            counts[slug] = number + 1
    return found


def documents(root: Path) -> list[Path]:
    result = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root, check=True, capture_output=True)
    return sorted({root / name.decode() for name in result.stdout.split(b"\0") if name and name.decode().lower().endswith((".md", ".markdown")) and (root / name.decode()).is_file()})


def jsdoc_outputs(root: Path) -> set[str]:
    """Resolve generated API entry-page links against real JSDoc declarations.

    Only api-mainpage.md uses this generated context. Other missing HTML links
    remain errors. The generator's source directory list supplies the inputs.
    """
    plugin = root / "tools/jsdoc/plugins/hifi.js"
    if not plugin.exists():
        return set()
    block = re.search(r"const dirList = \[(.*?)\];", plugin.read_text(), re.S)
    if not block:
        return set()
    symbols = set()
    for line in block[1].splitlines():
        if line.lstrip().startswith("//"):
            continue
        match = re.search(r"['\"]([^'\"]+)['\"]", line)
        if not match:
            continue
        folder = root / "tools/jsdoc" / match[1]
        for source in folder.glob("*"):
            if source.is_file() and source.suffix in {".h", ".cpp", ".js"}:
                text = source.read_text(encoding="utf-8", errors="replace")
                for doclet in re.findall(r"/\*\*?@jsdoc(.*?)\*/", text, re.S):
                    symbols.update(name + ".html" for name in re.findall(r"@(?:namespace|class)\s+([\w.]+)", doclet))
    return symbols


def validate(path: Path, root: Path = ROOT, generated: set[str] | None = None, anchor_cache: dict | None = None) -> list[str]:
    errors = []
    if not path.resolve().is_relative_to(root.resolve()):
        return ["document symlink escapes the repository"]
    text = path.read_text(encoding="utf-8")
    if re.search(r"(?m)^(?:<{7}|>{7})(?: |$)", text):
        errors.append("contains an unresolved merge marker")
    anchor_cache = {} if anchor_cache is None else anchor_cache
    for target, line in links(text):
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue
        relative = unquote(parsed.path)
        resolved = ((root / relative.lstrip("/")) if relative.startswith("/") else (path.parent / relative if relative else path)).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            errors.append(f"line {line}: link escapes the repository: {target}")
            continue
        if not resolved.exists():
            is_api_page = path.relative_to(root).as_posix() == "tools/jsdoc/api-mainpage.md"
            if is_api_page and target in (generated or set()):
                continue
            errors.append(f"line {line}: local link target does not exist: {target}")
            continue
        fragment = unquote(parsed.fragment)
        if not fragment or not resolved.is_file():
            continue
        if resolved.suffix.lower() in {".md", ".markdown", ".html", ".htm"}:
            if resolved not in anchor_cache:
                anchor_cache[resolved] = anchors(resolved.read_text(encoding="utf-8"), resolved.suffix.lower() in {".md", ".markdown"})
            if fragment not in anchor_cache[resolved] and fragment.removeprefix("user-content-") not in anchor_cache[resolved]:
                errors.append(f"line {line}: local anchor does not exist: {target}")
        else:
            line_range = re.fullmatch(r"L([1-9][0-9]*)(?:-L([1-9][0-9]*))?", fragment)
            if line_range is None:
                errors.append(f"line {line}: unsupported local file fragment: {target}")
            else:
                first = int(line_range[1])
                last = int(line_range[2] or line_range[1])
                total = len(resolved.read_bytes().splitlines())
                if not first <= last <= total:
                    errors.append(f"line {line}: local source line range does not exist: {target}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="check every workspace document (the default)")
    parser.add_argument("--base", help="compatibility option; full scan also validates unchanged incoming links")
    parser.parse_args()
    files = documents(ROOT)
    generated = jsdoc_outputs(ROOT)
    cache = {}
    failures = [f"{path.relative_to(ROOT)}: {error}" for path in files for error in validate(path, ROOT, generated, cache)]
    if failures:
        print("Documentation checks failed:\n- " + "\n- ".join(failures))
        return 1
    print(f"Documentation checks passed for {len(files)} workspace Markdown files; remote URLs were not fetched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
