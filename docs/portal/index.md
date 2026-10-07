---
last-updated: "2026-10-07"
last-reviewed: "2026-10-07"
scope: "noah-be/overte; shared main and explicitly named product branches"
---

# Overte Fork Documentation

This is the developer and test-operations portal for the experimental personal
fork **noah-be/overte**. Start with the task you want to perform.

| Task | Start here |
| --- | --- |
| Choose the right test layer | [Automated testing](testing/index.md) |
| Run checks without a device | [Local tests](testing/local-tests.md) |
| Understand required pull-request checks | [GitHub Actions](testing/github-actions.md) |
| Use the existing physical-device laboratory | [Jenkins laboratory](jenkins/index.md) |
| Check which laboratory jobs are enabled | [Dated laboratory status](jenkins/status.md) |
| Read or investigate a test result | [Results and troubleshooting](jenkins/results.md) |
| Build or update this website | [Maintaining the documentation](maintaining.md) |

The first portal chapter covers automated tests and Jenkins. The existing
[developer guide](../README.md), [architecture](../ARCHITECTURE.md),
[platform index](../interfaces/README.md), and [product roadmap](../ROADMAP.md)
remain the entry points for the rest of the fork.

## Testing

```{toctree}
:hidden:
:caption: Automated tests
:maxdepth: 1

testing/index
testing/local-tests
testing/github-actions
```

```{toctree}
:hidden:
:caption: Jenkins laboratory
:maxdepth: 1

jenkins/index
jenkins/run-tests
jenkins/results
Laboratory status <jenkins/status>
```

## Canonical references

These pages are rendered directly from their existing repository files. Their
procedures have one source; the portal does not maintain copies. Links to guides
outside this first chapter open the fork's current `main` on GitHub. Platform
references explicitly name their owning product branch.

```{toctree}
:hidden:
:caption: Reference guides
:maxdepth: 1

Project testing </tests/PROJECT_TESTING>
Physical-device harness </tests/device/README>
Shared Jenkins pipeline </tests/device/jenkins/README>
Recorded native CI qualification </docs/NATIVE_CI_QUALIFICATION>
```

## Documentation and upstream

```{toctree}
:hidden:
:caption: Documentation
:maxdepth: 1

maintaining
upstream
```

Each page shows its scope, content-change date, and review date. A Git-derived
change date is labelled as such; **Not recorded** means there is no documented
review. A date never turns a host check into evidence from a physical device.
