# Native input/runtime changes — revision 09

PI-003/005/007 production callers now apply these local rules:

- PicoInterfaceActivity forwards alphabetic external keyboard events to Qt only
  while focused and only for keyboard sources without gamepad/joystick source
  flags. Controller-origin Android keys remain consumed; OpenXR owns controllers.
- Android window focus loss cancels all registered WebView touch gestures,
  clears fractional scrolling and releases WebView focus.
- AndroidAudioInput checks microphone permission before creating a recorder and
  both before and after each blocking read. Revocation prevents that read from
  reaching JNI and enters existing cleanup. Recorder identity is volatile, and
  capture buffers are zeroed on loop exit.

Actual callers are under apps/picoInterface/src/main/java/org/overte/pico.
These entry files are authorized by revision 09 to connect the backlog-owned
input, lifecycle and audio nodes; no Shared Qt/QML or runtime file was changed.

Focused tests execute the keyboard decision, compile audio against API 26 and
all production Pico Java callers against SDK 36, and validate the native/JNI
delivery boundary. Compile-only Qt/resource stubs live exclusively under tests.
They do not prove a Qt runtime, device input, microphone route, OpenXR focus
transition or worn-headset behavior. Shared SH-003/005/006 binding remains pending.
