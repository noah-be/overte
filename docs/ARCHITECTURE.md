# Source architecture and test map

Overte contains a native Interface client, server processes, shared libraries,
QML UI, and JavaScript behavior. This map explains where to start reading code.
[Source ownership](SOURCE_LAYOUT.md) determines the correct branch;
[project coverage](../tests/project-coverage.json) inventories test areas.

## Runtime components

The Interface application coordinates shared libraries, renders the world, and
hosts UI and scripts. QML and JavaScript reach application behavior through the
client's bindings and library interfaces. The domain server coordinates a
domain, and assignment clients run its assigned services. Shared networking
code connects the processes. Build and repository tools support this runtime
but are not application features.

| Area | Source entry points | Verification entry points |
| --- | --- | --- |
| Interface application, startup, and lifecycle | [Application.cpp](../interface/src/Application.cpp), [client UI bindings](../interface/src/ui/) | [Host lifecycle contracts](../tests/device/contracts/lifecycle/), then a target run |
| QML UI, dialogs, and tablet | [Interface QML](../interface/resources/qml/), [UI library](../libraries/ui/) | [QML host tests](../tests/device/qml/), [tablet E2E](../tests/device/TABLET_E2E.md) |
| JavaScript runtime and behavior | [ScriptEngine.cpp](../libraries/script-engine/src/ScriptEngine.cpp), [system scripts](../scripts/system/) | [Shared script tests](../tests/javascript/), [native script-engine tests](../tests/script-engine/) |
| Rendering and visual entities | [Rendering library](../libraries/render/), [GPU abstraction](../libraries/gpu/), [entity rendering](../libraries/entities-renderer/) | [GPU tests](../tests/gpu/), [host graphics contracts](../tests/device/contracts/graphics/), target rendering evidence |
| Avatars, animation, and physics | [Avatars](../libraries/avatars/), [animation](../libraries/animation/), [physics](../libraries/physics/) | [Avatar tests](../tests/avatars/), [animation tests](../tests/animation/), [physics tests](../tests/physics/) |
| Audio | [Audio library](../libraries/audio/), [client audio](../libraries/audio-client/) | [Native audio tests](../tests/audio/), [host audio contracts](../tests/device/contracts/audio/), [sound E2E](../tests/device/SOUND_E2E.md) |
| Network and server processes | [NodeList.cpp](../libraries/networking/src/NodeList.cpp), [domain server](../domain-server/src/), [assignment client](../assignment-client/src/), [ICE server](../ice-server/src/) | [Networking tests](../tests/networking/), [domain fixture](../tests/device/fixture/DOMAIN.md) |
| Input and device integration | [Controllers](../libraries/controllers/), [display plugins](../libraries/display-plugins/), [plugins](../plugins/) | [Device harness](../tests/device/README.md), owning product's tests |
| Build graph and dependencies | [CMakeLists.txt](../CMakeLists.txt), [CMake helpers](../cmake/), [Conan recipe](../conanfile.py) | [Build guides](../BUILD.md), [dependency policy](DEPENDENCY_RELEASES.md) |
| Repository automation | [Tools index](../tools/README.md), [versioned GitHub policies](../.github/) | [Project runner](../tests/PROJECT_TESTING.md), [Repository Doctor](REPOSITORY_HEALTH.md) |

These are reading entry points, not a promise that every behavior has coverage.
For example, syntax and policy tests cannot establish that a renderer works on
a GPU or that microphone input works on a physical device.

## Make a focused change

Read the relevant component and its nearby `*_CONTRACT.md` documents before
changing behavior. Contracts describe invariants such as ownership, lifetime,
threading, privacy, and failure handling; regression tests should exercise the
invariant. Keep that context near the implementation and link it from broader
guides when needed.

Choose the verification layer from [project testing](../tests/PROJECT_TESTING.md):
repository checks, standalone host C++/QML contracts, configured native CTest, or
target runtime evidence. A test under `tests/device/` may still be a host test;
its directory name does not establish physical-device execution.

Platform-specific code stays in its owning branch. Some shared mobile selectors
and interfaces retain historical Android or Phone names because iOS also uses
them; [source ownership](SOURCE_LAYOUT.md) explains that compatibility boundary.
Change those interfaces only with their consumers and tests identified.
