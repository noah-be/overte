# Closed world diagnostic events v002

Additive proposal for Shared review, used by the owned Pico diagnostic candidate. Existing wire values and rejection rules are unchanged. C++ and Java catalogs add WORLD_STARTUP, WORLD_TUTORIAL_IMPORTED, WORLD_OTHER_IMPORTED, WORLD_IMPORT_FAILED, WORLD_PHYSICS_READY and WORLD_FRAME_SUBMITTED with the OVT_ prefix. All values are fixed ASCII strings <=32 bytes. Callers emit a single enum-derived value selected from control flow; no URL, identifier, entity count, position or context is appended.

WORLD_STARTUP means startup address selection was reached; IMPORTED means the parser and entity transfer returned successfully (not rendered or collision-ready); PHYSICS_READY means the existing physics activation occurred; FRAME_SUBMITTED means a world render frame reached the display-plugin submission call (not proof the headset displayed useful pixels). First-frame reporting is bounded once per process. These events never manufacture build or device acceptance.

Both sanitizers still reject every non-exact string, including an allowed event plus a payload. Existing sinks are unchanged; no logging bypass is added. Native conformance covers new enum values, maximum length, and contaminated event rejection.

Additive diagnostic refinement: WORLD_TUTORIAL_SELECTED identifies the known default selection branch, WORLD_REDIRECT_IMPORTED identifies content identical to the bundled error scene, WORLD_NAVIGATION_BLOCKED identifies lookup rejected by foreground/request-scope admission, and WORLD_EMPTY_IMPORTED identifies an empty transferred entity list. Outputs contain no variable fields.
