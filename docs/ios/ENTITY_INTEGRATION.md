# Native entity integration boundary

The machine-readable contract is [`ios/entity-integration-inventory.json`](../../ios/entity-integration-inventory.json). It describes the shortest existing Overte path from a domain connection to a populated `EntityTree`. The iOS port must link and drive that path; it must not implement a second wire protocol in Objective-C, Swift, or bootstrap code.

The boundary is deliberately split into observable gates: `DomainList` acceptance, discovery of `NodeType::EntityServer`, sending `EntityQuery`, routing version-compatible `EntityData`, decoding with `OctreeProcessor`/`EntityTree`, and handing real entities to `EntityTreeRenderer`. DNS or HTTP reachability only proves address reachability and does not satisfy the first gate. Generated Metal preview objects do not satisfy the final gate.

Run the source-drift check on Linux or macOS:

```sh
python3 ios/tests/entity-integration-inventory-test.py
```

The validator checks target declarations, source files, implementation anchors, packet names, and the essential acceptance gates. It intentionally does not claim iOS compatibility: platform compilation, signing, a live server, and an iPad render capture remain separate runtime evidence.

For the minimum first integration, scripts, physics, edits, avatars, and audio may remain disabled. Networking reliability, packet versioning, octree decoding, resource fetching required by visible entities, and the real render handoff may not be replaced with mocks in device acceptance.

## iOS runtime gate markers

The production client emits the following structured `qInfo` markers only when compiled for iOS. The fixed prefix is `OVERTE_IOS_ENTITY_GATE`; fields after the gate name are diagnostic and may grow without changing the contract.

| Order | Marker | Emission point |
| --- | --- | --- |
| 1 | `domain_list_connected` | A valid first `DomainList` changes `DomainHandler` to connected. |
| 2 | `entity_server_active` | `NodeType::EntityServer` becomes active. |
| 3 | `entity_query_sent` | An `EntityQuery` is handed to the existing `NodeList` transport. |
| 4 | `entity_data_received` | The first `EntityData` packet reaches `OctreePacketProcessor`. |
| 5 | `entity_tree_nonempty` | The existing decoder produces an entity found in `EntityTree`. |
| 6 | `render_handoff` | The first real entity produces a renderable and enters the scene transaction. |

The last three high-frequency paths log only their first successful observation where applicable. The tree/render pair is armed only after a serverless scene has parsed successfully or a version-compatible `EntityData` packet is about to be decoded. Both markers carry the same entity UUID: the entity must belong to that decoded/imported world and must have produced a real renderable. Startup and UI entities cannot satisfy these gates. The markers report execution of existing client paths; they do not alter packets, decoding, query cadence, or rendering behavior.

iOS skips the desktop-only `http://localhost:60332/status` Sandbox probe and asynchronously enters the existing "Sandbox absent" startup path. iOS cannot host that companion process; waiting for it would otherwise delay the command-line world URL before any serverless or online lookup begins.

Export the Overte device log to a text file and produce an offline acceptance report with:

```sh
python3 ios/tools/validate-entity-gate-log.py ipad.log --output entity-acceptance.json
```

The command exits successfully only when all six markers occur in order, UUIDs and positive packet sizes are plausible, the query/data node matches the active entity server, and the rendered entity matches the first decoded entity. Its JSON output contains ordered evidence with source line numbers and diagnostics. Messages from the bootstrap preview such as “scene loaded” are not accepted as native entity evidence.

On Fedora or Windows with Python 3, turn an already exported iPad text log into
a minimal offline handoff (PowerShell uses the same arguments):

```sh
python3 ios/tools/prepare-entity-evidence.py ipad-export.log ipad-entity-evidence \
  --source-revision 0123456789abcdef0123456789abcdef01234567 \
  --bundle-sha256 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --os-version 18.0 --device-model "iPad Pro"
```

The command requires all six gates, refuses to overwrite an existing handoff,
and creates both a directory and `ipad-entity-evidence.zip`. It does not access
the iPad or invoke Apple tooling. To minimize disclosure, the ZIP contains only
canonical gate records, the validator report, and provenance metadata. The full
raw device log is not copied; its SHA-256 is recorded so the locally retained
export can later be matched to the evidence. Review even the canonical UUIDs
before sharing the ZIP outside the test team.
