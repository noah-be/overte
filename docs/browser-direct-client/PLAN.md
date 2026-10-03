# Direct browser client implementation plan

Material AI assistance: implementation, analysis, documentation, and tests are
being developed with OpenAI Codex. Generated changes require source review and
runtime evidence; generation itself is not verification.

## Authorized scope

- Fork and only GitHub write target: `noah-be/overte`.
- Base: fork `main`, `d569930678d2edb61330a96bcdcab17ee68a732f`, fetched on
  2026-10-02.
- Topic: `feature/main/browser-direct-client`.
- Worktree: `/home/user/Documents/github/overte-browser-direct-client`.
- The concurrent gateway browser client is read-only. Reuse must identify an
  immutable source commit or individual local-file content hashes.
- This user-authorized browser feature does not change the product roadmap or
  complete any issue. No permanent integration branches are changed.

## Architecture constraints

Rendering, navigation, interaction, voice capture/playback, and the tablet run
on the visitor's device. The browser connects to the domain server and its
responsible assignment services. Browser-capable endpoints inside those
processes are permitted. A separate translating gateway, visitor-specific native
client process, world video stream, or streamed native tablet is excluded.

Native admission, account/domain authentication, permissions, and session
boundaries remain authoritative. Native clients continue to use their supported
transport. Public worlds and servers are read-only.

## Implementation sequence

1. Read the real networking code, historical WebRTC transport, current Vircadia
   Web/Web SDK primary sources, and reusable browser code. Establish protocol
   compatibility with executable tests before selecting a transport.
2. Implement the selected browser transport in the responsible Overte server
   components, with bounded input/queues, admission and session isolation,
   configurable isolated ports, and tests for native coexistence.
3. Implement the browser's direct domain lifecycle, entities and assets
   (HTTPS and `atp:`), renderer, collision/navigation, and entity interaction.
4. Implement native-compatible avatar synchronization and bidirectional voice,
   including microphone consent, mute, and playback.
5. Implement a local browser tablet with working domain/navigation, people,
   audio, and settings applications; add clear loading and failure states.
6. Build an isolated domain and import a representative scene derived from
   actual `overte_hub` data with recorded provenance. Run short browser/native
   tests on separate ports, profiles, displays, and registered processes.
7. Measure post-join and texture-loading changes with identical assets,
   appearance, and quality. Preserve comparative measurements and limitations.
8. Run production builds, Chrome checks, relevant native
   and repository checks, and CI. Commit and push only the authorized topic;
   create and read back an English draft PR in the fork.

## Acceptance evidence

Each item is pending until real evidence is recorded in `STATUS.md`:

- Select/join/leave/reconnect a real domain directly.
- Render actual entities, models, materials, HTTPS and ATP textures.
- Smooth keyboard/mouse movement, collisions, and basic interactions.
- Visible own/remote avatars with native position synchronization.
- Bidirectional browser/native speech; real microphone evidence is distinct
  from deterministic synthetic audio.
- Locally executed, functional tablet applications.
- Production build and documented self-hosting with open components.
- Current desktop Chrome runtime evidence. The user narrowed future browser
  work to Chrome only on 2026-10-02; no further Firefox runs are authorized.
- Loading improvements under equal visual quality.
- No separate gateway or native client intermediary.

Public direct access to `overte_hub` cannot pass until its actual server supports
the new transport. Isolated-domain evidence is recorded separately.

## Continuation

Read this file, `STATUS.md`, research/architecture notes, and the latest evidence
before resuming. Preserve the active scope and existing work. Do not report
completion from unit tests alone or close issues automatically.
