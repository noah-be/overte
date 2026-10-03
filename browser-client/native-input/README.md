# Native Tablet text input

The same private-worker extension also captures the owned offscreen GUI root when
a Qt Quick Controls popup is outside the tablet item. Qt 5.15's QML callback
`grabToImage` refuses the C++-created `QQuickRootItem` because it has no QML engine;
the public C++ `QSize` overload supports it. The extension accepts only the
`contentItem()` of its own parent item's window, at most 2048 × 2048 pixels, one
pending request and a finite positive safe-integer token. It has no file-path,
arbitrary-window or framebuffer API. `QPointer` guards the original owner/root/
window; a changed owner cannot receive old pixels. The trusted QML callback keeps
the original capture/revision/navigation identity and performs the existing
session-local save only while that capture remains active. Cancellation retains
the outstanding GPU ownership until its correlated completion.

`--test` also runs `grab-test`: a real engine-free C++ root with a known painted
QML child, exact image pixels, private-window/descendant/token/size refusal,
concurrent and reentrant refusal, result release, owner reparent revocation and
receiver destruction. This fixture shares the existing authenticated test Xvfb;
it never captures the operator desktop. Runtime popup proof remains a separate
native/browser acceptance test.

The browser commits text to the native Qt editor through a small Qt 5 QML
extension. `QInputMethodEvent` preserves the editor's selection, undo transaction,
validator, input mask, maximum length and plain-text composition. It avoids the
programmatic `TextEdit.insert()` path, which can interpret visitor markup and
does not enforce `readOnly`. Cut deletes the native selection with a genuine Qt
Backspace event; the browser exports the selected text to its own clipboard.
Neither operation reads or changes the operator's clipboard.

Build after extracting the reviewed native worker distribution:

```sh
python3 browser-client/tools/build-native-input.py --test
```

The builder downloads three SHA256-pinned official Ubuntu Jammy Qt 5.15.3 SDK
packages into `build/browser-lab/native-input`. It extracts headers and `moc`
without installing system packages, then links against the native worker's
existing Qt libraries. It verifies the loaded runtime is Qt 5.15, patch 3 or later;
Qt 6 and older Qt 5 ABIs are refused. `g++`, `ar`, `tar` and an authenticated Xvfb
are required. The tests create and clean up a separate virtual display; they do
not use the desktop profile or clipboard.

Add the generated `build/browser-lab/native-input/qml` directory to the worker's
`QML2_IMPORT_PATH`, alongside its existing Qt and QtQuickTest imports. The worker
sandbox mounts this exact runtime directory read-only. Do not copy a second Qt
runtime into Interface or load a plugin built against unrelated host headers.

The actual Qt 5.15.3 assertions cover Unicode and middle-selection replacement,
single undo/redo, writable and readonly cut, literal markup in a rich editor,
readonly/disabled/unfocused refusal, preservation of invalid selected text under
the native validator, valid replacement, input mask, maximum length, the 64 KiB
UTF-8 input limit, control-character refusal and unchanged private clipboard.

Qt's [input-method event documentation](https://doc.qt.io/archives/qt-5.15/qinputmethodevent.html)
describes commit strings, selection replacement and undo behavior. The actual
editor implementations are
[QQuickTextInput](https://github.com/qt/qtdeclarative/blob/5.15/src/quick/items/qquicktextinput.cpp)
and [QQuickTextEdit](https://github.com/qt/qtdeclarative/blob/5.15/src/quick/items/qquicktextedit.cpp).

The private WebEngine route now delivers ordinary text with the genuine Qt input
method event to the current WebEngine Quick delegate. A dedicated password
method requires that exact delegate class, the original root/window/thread/
focus/ancestry, and the hidden-text input hint. Password text is one complete
well-formed UTF-16 commit, at most 64 KiB UTF-8 and 65,536 UTF-16 units, with no
C0 or DEL characters. It emits no keyboard events and has no alternative after
delivery. This keeps a supplementary character and its neighbors in one undo
transaction. A failed native send is a refusal, not a reason to run a DOM setter.

The QML route performs one read-only DOM admission query, then checks current
focus, WebView URL, displayed surface, permission revision and navigation before
native delivery. The existing queue limit (64 operations), serialized request
limit (262,144 units), and five-second timeout remain unchanged. Cancellation
clears queued text and retained GUI references. It can prevent a future dispatch;
it cannot retract an input event already delivered. Multiple password elements
in the same page can share a Quick delegate, so these checks are **not** a lock
on a distinct password DOM element.

`build-native-input.py --test --test-web-editors` runs the existing `actual-qt-input` CI gate's
fourteen genuine WebEngine editor cases; no CI stage is added. It generates a
private fixture from the current production QML functions and verifies every
invoked native method is registered in both the fixture and compiled C++.
The ordinary text, number, textarea, literal contenteditable, password Unicode,
one Undo, Redo, maxlength, readonly, disabled, immediate cancellation and
navigation cancellation oracles keep their original values and five-second
case deadlines. The test refuses a stale plugin source, altered packaged
WebEngine resources, or a mismatched Qt 5.15.3 runtime. Prepare the lab first so
the matching QtTest module is present alongside the reviewed native libraries.

The equivalent standalone command after a successful plugin build is:

```sh
python3 browser-client/native-input/web-editor/run.py \
  --input-build build/browser-lab/native-input \
  --qt-libraries build/browser-lab/appimage/squashfs-root/usr/lib \
  --qt-test-libraries build/browser-lab/qt-tablet/usr/lib/x86_64-linux-gnu \
  --xvfb build/browser-lab/host-tools/usr/bin/Xvfb \
  --report build/browser-lab/evidence/native-web-editor.json
```

Use a new report filename for each run. Reports contain only fixed case enums,
lengths, boolean outcomes and source/resource hashes. The runner owns an
authenticated display and renderer process group, preserves the inherited
`HOME`, and confines configuration/cache/data to its temporary profile. Both
output streams are drained with 64 KiB retention caps; failure stderr is saved
privately beside the report. The editor's original 60-second outer deadline and
65-second runner deadline are retained. This fixture does not prove complete
Tablet app functionality or shipping browser reliability.

Portable control and registration tests run under the existing `npm test` glob;
`native-input/test-native-web-route.py` compiles the exact whole-password method
against controlled event contracts. These CPU checks cannot prove Blink's actual
editing semantics. The genuine fixture remains necessary.

The existing `npm test` registration also runs
`native-input/web-editor/test-owned-reaping.py`: sixteen Linux CPU controls with
real private Python zombie/orphan children, ownership refusals and a failed-reap
counterfactual. It starts no Qt, display, browser or lab service. Linux child
subreaping and pidfd facilities are required; an unavailable facility fails this
qualification explicitly rather than skipping it. The three existing bounded
pipe controls remain unchanged. Run the ownership controls directly with:

```sh
python3 -B browser-client/native-input/web-editor/test-owned-reaping.py
```

The explicit `--test-web-editors` flag requires `--test`. Jenkins enables it only
with the reviewed packaged native runtime. Ordinary `--test` still runs the
existing native input/root-grab tests against supported system Qt; it does not
claim the packaged WebEngine editor proof. A system Qt distribution cannot
substitute for the exact reviewed editor resources.
