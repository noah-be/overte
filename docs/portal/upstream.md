---
last-updated: "2026-10-07"
last-reviewed: "2026-10-07"
scope: "Upstream handbook references and fork-specific reuse policy"
---

# Upstream documentation

The original project maintains [the Overte handbook](https://docs.overte.org/en/latest/)
in [overte-org/overte-docs-sphinx](https://github.com/overte-org/overte-docs-sphinx).
It covers exploration, content creation, scripts, hosting and development.
JavaScript API and C++ reference sites are linked from the
[upstream repository](https://github.com/overte-org/overte#documentation).

## What this portal reuses

The fork uses the same Sphinx/MyST approach so existing Markdown guides can be
rendered alongside future reviewed reStructuredText content. The theme and
navigation serve the fork's test operations. The initial chapter is authored
for this fork; it does not copy the complete upstream handbook or its
translations.

Follow the upstream handbook for shared user concepts. Follow the fork's own
platform and test instructions for its Android Phone, Pico, iOS, CI and local
laboratory behavior. An upstream command or support statement is not evidence
that a fork-specific path is implemented or accepted.

## Reuse a specific upstream page

Record the original repository, path and commit, preserve its license and
attribution, and review the commands against the owning fork branch. Identify
intentional fork differences and maintain the upstream version as a comparison
source. The original documentation's
[build configuration](https://github.com/overte-org/overte-docs-sphinx/blob/aedb3e16ce92bf9cb85b4e46dd735aacb125f320/Makefile)
downloads some build guides from upstream `master`; importing that configuration
unchanged would render upstream build instructions instead of this fork's.

This comparison inspected upstream documentation commit
`aedb3e16ce92bf9cb85b4e46dd735aacb125f320` and fork `main` commit
`a0102a0133078b36ce3a384a974348b57c22501a`. New upstream changes require a fresh
review. Upstream repositories remain read-only for this work; all authored
repository changes belong to `noah-be/overte`.
