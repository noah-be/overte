<!-- Copyright 2026 Overte contributors; SPDX-License-Identifier: Apache-2.0 -->
# Movement between render frames

World keyboard transitions and animation frames consume the same fixed-step
movement clock. Before accepting a new controlled key or releasing a held key,
the World advances the previous key state to the event timestamp. This retains
a press that begins and ends between rendered frames without assigning earlier
idle time to a new direction or counting an interval twice.

The existing 60 Hz steps, maximum 250 ms recovery, collision subdivision, initial
surface wait and fall-to-spawn safeguards remain active. Blur, hidden-document,
input-disable, session and spawn resets discard old elapsed time. This bounded
recovery does not promise full travel across a long suspended frame.

Run the actual World regression and existing physics controls from browser-client:

```sh
node --import tsx --test src/world-movement-input.test.ts src/simulation-clock.test.ts tests/world-simulation.test.ts tests/world-ground-support.test.ts
```

The new controls exercise the production listeners and animation/collision
methods without constructing a renderer. They are CPU regression evidence.
The original real native journey still requires over 0.5 m of browser movement,
native position agreement and subsequent native participant movement, collision,
interaction, audio and reconnect checks at their original deadlines.

The curated movement checkpoint now retains the already-produced document
visibility/focus and bounded initial-surface state. These fields help distinguish
input loss, loading safeguards and scheduling stalls; they cannot turn an
incomplete journey into a pass.
