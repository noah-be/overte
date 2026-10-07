"""Keep repository links usable and expose honest per-page review metadata."""

from datetime import date
from pathlib import Path
import subprocess
from urllib.parse import quote, unquote, urlsplit

from docutils import nodes
from sphinx import addnodes
from sphinx.errors import ExtensionError


def repository_references(app, doctree):
    """Link excluded repository content before MyST resolves document targets."""
    env = app.env
    root = Path(app.srcdir).resolve()
    for node in list(doctree.findall(addnodes.pending_xref)):
        if node.get("reftype") != "myst":
            continue
        target = urlsplit(node.get("reftarget", ""))
        if target.scheme or target.netloc or not target.path:
            continue
        fragment = target.fragment
        if node.get("refdomain") == "doc":
            # MyST has already normalized Markdown document names to the root.
            # Leave included documents and their anchors to the strict resolver.
            if target.path in env.found_docs:
                continue
            path = (root / (unquote(target.path) + ".md")).resolve()
            fragment = node.get("reftargetid") or ""
        else:
            source = Path(env.doc2path(node.get("refdoc", ""))).resolve()
            path = (source.parent / unquote(target.path)).resolve()
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if path.is_file() and path.suffix == ".md":
            url = app.config.repository_docs_url
        elif path.is_dir() and target.path.endswith("/"):
            url = app.config.repository_docs_url.replace("/blob/", "/tree/")
        else:
            # Missing targets retain MyST's warning and fail the strict build.
            continue
        url += quote(relative.as_posix(), safe="/")
        if fragment:
            url += "#" + quote(unquote(fragment), safe="-_")
        node.replace_self(nodes.reference("", "", *node.children, refuri=url))


def validate_metadata(app, env):
    for name in sorted(env.found_docs):
        if not name.startswith("docs/portal/"):
            continue
        metadata = env.metadata.get(name, {})
        if not metadata.get("scope"):
            raise ExtensionError(f"{name}: document scope is required")
        for key in ("last-updated", "last-reviewed"):
            value = str(metadata.get(key, ""))
            try:
                parsed = date.fromisoformat(value)
            except ValueError as error:
                raise ExtensionError(f"{name}: {key} must be YYYY-MM-DD") from error
            if parsed.isoformat() != value or parsed > date.today():
                raise ExtensionError(f"{name}: {key} must be a valid non-future ISO date")


def page_metadata(app, name, template, context, doctree):
    if name not in app.env.found_docs:
        return
    metadata = app.env.metadata.get(name, {})
    context["portal_scope"] = metadata.get("scope", "Shared fork main; canonical reference")
    context["portal_reviewed"] = metadata.get("last-reviewed", "Not recorded")
    updated = metadata.get("last-updated")
    if not updated:
        relative = Path(app.env.doc2path(name)).relative_to(Path(app.srcdir))
        result = subprocess.run(
            ["git", "log", "-1", "--no-merges", "--format=%cs", "--", relative.as_posix()],
            cwd=app.srcdir, capture_output=True, text=True, check=False, timeout=10,
        )
        updated = result.stdout.strip() if result.returncode == 0 else ""
        updated = f"{updated} (Git history)" if updated else "Not recorded"
    context["portal_updated"] = updated


def setup(app):
    app.add_config_value("repository_docs_url", "", "html")
    app.connect("doctree-read", repository_references)
    app.connect("env-updated", validate_metadata)
    app.connect("html-page-context", page_metadata)
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
