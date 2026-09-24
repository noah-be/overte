# Repository tool index

Run tools from the repository root. This index links their authoritative
instructions; it does not introduce another command wrapper or policy store.
For the first developer check, use [project testing](../tests/PROJECT_TESTING.md).

| Purpose | Tool location | Instructions and scope |
| --- | --- | --- |
| Run repository and host checks | [Project runner](../tests/run-project-tests.py) | [Testing guide](../tests/PROJECT_TESTING.md); local checks |
| Inspect local maintenance state | [Maintenance snapshot](repository-maintenance/) | [Maintenance guide](../docs/REPOSITORY_MAINTENANCE.md); offline report without fetching or deleting |
| Route and aggregate required PR checks | [Repository checks](repository-checks/) | [Required-check design](../docs/REPOSITORY_MAINTENANCE.md#required-checks); local fixtures, separate staged deployment |
| Check or regenerate policy-derived documentation | [Policy consistency](repository-policy/) | [Branch table](../docs/BRANCH_GOVERNANCE.md), [suite inventory](../tests/PROJECT_TESTING.md); default read-only, `--write` updates marked blocks |
| Validate branch direction and naming | [Branch policy](branch-policy/) | [Branch governance](../docs/BRANCH_GOVERNANCE.md); local validation and separate live inspection |
| Inspect repository health | [Repository Doctor](repository-health/) | [Doctor guide](../docs/REPOSITORY_HEALTH.md); local contracts or read-only live audit |
| Prepare integrated-branch cleanup | [Branch cleanup](branch-cleanup/) | [Cleanup policy](../docs/AUTOMATIC_BRANCH_CLEANUP.md); preview and explicit governed mutation are separate |
| Validate shared qualification reuse | [Synchronization checks](sync-test-reuse/) | [Branch workflow](../docs/BRANCH_WORKFLOW.md); exact revision and product gates |
| Structure and validate issues | [Issue intake](issue-intake/) | [Issue workflow](../docs/ISSUE_WORKFLOW.md); validation before an authorized issue write |
| Resolve pinned dependency bundles | [Dependency tools](dependency-releases/) | [Dependency policy](../docs/DEPENDENCY_RELEASES.md); local checks, live audit, and retirement have distinct commands |
| Validate release evidence | [Release tools](release/) | [Release bundle guide](release/README.md) |
| Understand device orchestration | [Device harness](../tests/device/) | [Device guide](../tests/device/README.md); host fixtures and target runs are distinct |
| Generate API documentation | [JSDoc](jsdoc/), [Doxygen](doxygen/) | [JavaScript documentation](jsdoc/README.md), [C++ documentation](doxygen/README.md) |

The repository checks exercise tools with local fixtures. Running a live audit,
device operation, release command, or write mode is a separate operation with
the prerequisites and boundaries in its guide.
