# SH-003 retained preference enforcement

Implementation-only continuation of sh003-profiles/v001. Product/selector/control
IDs are unchanged. `ConfiguredCapabilityProfile.h` selects the actual compiled
product for BOTH FileUtils and Preferences; a missing/unknown Android app or
mixed Android+iOS stack is Unknown, never Desktop.

`preferenceAllowed(Product, category, name)` binds the retained legacy registry
to the profile. Phone/iOS HMD, VR Movement, Controllers and Dominant Hand are
denied; Pico retains these supported VR categories. Mixed User Interface is
Pico-only among mobile products. Mobile desktop plugin, snapshot directory and
unsupported/no-op Privacy categories are denied. Other enumerated existing
categories are retained (graphics remains Tolerated); unknown mobile categories
are denied. Desktop registration remains extensible and unchanged. Category and
preference names here are the exact stable registration keys, not localized
labels or a new native control-ID schema.

The actual production callers are `Preferences::addPreference`, all four typed
Preference load/save implementations, ButtonPreference::trigger, FileUtils and
both retained `Preference.qml` bases. A const, non-writable `profileAllowed`
property is determined at construction. Unsupported objects retain QObject
ownership but never enter categories/preferencesByCategory. Both existing
Section builders therefore cannot construct them through registry lookup.
Direct C++/QML references cannot persist or trigger the unsupported action;
changing enabled/value cannot override the profile. No denied getter is invoked
by load/save. Both actual QML bases hide and disable a directly supplied denied
preference and its descendants, excluding keyboard/tab focus. This is not
generic access control for arbitrary JavaScript/native Settings APIs.

Import all changed Shared paths together after v001. No native implementation
changes are required. Reconcile the small FileUtils delta and preserve any
platform-specific code around it. If a product has a genuinely new preference
category, request its reviewed behavior in General; do not broaden the native
allowlist or infer platform identity from a presentation selector. These two
QML files are Shared-owned; owners must not rewrite their local variations.

Focused check: `python3 tests/device/contracts/test_retained_preferences.py`.
It compiles the actual Preferences header/source plus original Qt-generated moc
against host Qt6 Core/QML/Quick, executes both original QML components, checks
registry omission, all typed write/trigger negatives, supported writes and
disabled descendant focus. Six application define stacks are tested. Qt host
ABI headers are loaded before selecting application test macros; this is NOT
Android/iOS SDK compilation. The C++14 profile test remains applicable.

Pending: full Qt5/Qt6 product builds, QFileSelector resolved-resource snapshots,
every custom ControllerSettings/graphics/audio control and script-setting entry,
accessible name/geometry/IME/touch/pointer/controller behavior on real products.
This does not establish SH-003 PASS, native UI acceptance, or a new APK identity.
