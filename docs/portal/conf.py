"""Build the fork portal from an explicit selection of repository documents."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "_ext"))

project = "Overte Fork Documentation"
author = "noah-be/overte contributors"
copyright = "2026, noah-be/overte contributors"
language = "en"
needs_sphinx = "9.1"
extensions = ["myst_parser", "repository_docs"]
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
root_doc = "docs/portal/index"

# The repository is the source directory. Read canonical guides directly,
# without copying them or discovering unrelated Markdown and local artifacts.
include_patterns = [
    "docs/portal/*.md",
    "docs/portal/**/*.md",
    "tests/PROJECT_TESTING.md",
    "tests/device/README.md",
    "tests/device/jenkins/README.md",
    "docs/NATIVE_CI_QUALIFICATION.md",
]
exclude_patterns = ["build/**", ".git/**"]
myst_heading_anchors = 6
nitpicky = True

html_theme = "sphinx_rtd_theme"
html_title = "Overte Fork Documentation"
html_theme_options = {"navigation_depth": 3, "collapse_navigation": False}
templates_path = ["_templates"]
html_static_path = ["_static"]
html_css_files = ["portal.css"]
html_show_sourcelink = False
html_copy_source = False
html_show_sphinx = False
html_additional_pages = {"index": "portal-home.html"}

# Excluded repository guides remain links to the fork's current main branch.
# Product guides use explicit platform-branch URLs in the authored pages.
repository_docs_url = "https://github.com/noah-be/overte/blob/main/"
