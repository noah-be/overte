# SH-003 Shared Switch label/action/focus v001

The actual Shared Switch's ON/OFF labels now use one guarded user-choice
function: update checked, focus the native control and emit the existing clicked
signal once. This reaches real onClicked consumers such as Audio.qml's muteMic,
instead of changing only the visual checked state. Ordinary native click/Space
and existing checked-change signals remain unchanged; programmatic checked
assignments are not converted into user clicks.

The inner native Switch has visible/enabled StrongFocus and clears focus on
hide/disable. Its accessible name uses the existing ON label (OFF if absent).
The wrapper owns original HifiConstants and has a nonzero default implicit
height; explicit caller height and existing touch scaling remain authoritative.
The source helper rejects hidden/disabled label actions, including direct calls.

`test_ui_switch.py` loads the COMPLETE Shared Switch and COMPLETE original
Audio.qml muteMic component in real Qt6 Quick Controls. AudioScriptingInterface
storage is a QQmlPropertyMap boundary; layout and bar index are fixture inputs.
Desktop/HMD property selection, actual label clicks, canceled label press,
Space, Tab traversal, hidden/disabled guards, attached accessible name and
implicit height are checked. The existing OFF-label API is exercised as an
additional fixture variation; actual muteMic ON-label text stays unchanged.

Baseline1fe5a1feff RED: visual checked changed but clicked count stayed zero.
Fixed two actual Audio caller modes PASS. No physical audio/device/Qt5 claim.
The test uses sh003-tablet-preferences-actions/v001's block-extraction helper,
source1fe5a1feff84787b1237bcaf840284a82386e5c2, manifest
4819833cf98612da851f6e22e23023ba2462e2dfb5c65ab9edf3c6319e9b6316.
No additional production/native contract or new platform hook is required.

Pending: actual audio engine/hardware and native assistive-technology delivery,
other Switch consumers with persistence/bindings, custom settings/keyboard,
Qt5/whole-platform builds and original SH-003/SH-006 acceptance.
