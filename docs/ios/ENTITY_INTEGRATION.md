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

The last three high-frequency paths log only their first successful observation where applicable. These markers report execution of existing client paths; they do not alter packets, decoding, query cadence, or rendering behavior.
