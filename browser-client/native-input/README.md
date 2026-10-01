# Native Tablet text input

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
