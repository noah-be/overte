---
last-updated: "2026-10-07"
last-reviewed: "2026-10-07"
scope: "Manual runs through the existing local Jenkins installation"
---

# Run a laboratory test

Use an enabled job for the intended platform. Check the
[dated job inventory](status.md), then review its current configuration in the
local Jenkins UI. Job parameters can differ from checked-in migration templates
and can change between product branches.

## Prepare one explicit run

Before starting, record:

- the job and the exact source revision being tested;
- the candidate artifact and the verified installed-app binding, where required;
- the suite and all optional suite switches;
- the availability of the physical target and the required fixture/adapter.

Use the existing configured device resource and credential bindings. Enter
private deployment values through the local job's parameter form. The device
selector is supplied by Jenkins Secret Text binding, not pasted into a command.
The [shared configuration guide](../../../tests/device/jenkins/README.md#job-configuration)
explains which inputs belong outside the repository.

## Start and follow the run

For parameter sets containing only public job/suite values, the official CLI
supports explicit parameters and a synchronous result:

```text
overte-jenkins build <job> -p <public-parameter>=<value> ... -s -v
```

Replace the placeholders with the reviewed job and complete intended parameter
set. This is a command shape, not a ready-to-run invocation. Use the local UI
when the required deployment values include private agent/resource names or
paths. Device selectors remain in the configured credential binding. Do not
rely on remembered defaults for optional suites.

`-s` waits and returns the build outcome; `-v` streams the console. Interrupting
`-s` also interrupts the build. Jenkins can queue while its agent or device
resource is occupied. Optional soaks, campaigns, accessibility and upgrade runs
require their own prerequisites and explicit selection.

## Follow a known build

```text
overte-jenkins console <job> <build-number> -n 100
overte-jenkins console <job> <build-number> -f
```

Keep the console private until reviewed for publication. Do not share raw job
XML: it can contain private deployment configuration. For a terminal that only
needs to inspect a run, an explicit build number avoids silently following a
different latest build.

## Finish the record

Capture the build number, source/artifact binding, selected suites, result and
cleanup outcome. Inspect the JSON/JUnit evidence rather than reporting only the
Jenkins badge. Continue with [Results and troubleshooting](results.md).
