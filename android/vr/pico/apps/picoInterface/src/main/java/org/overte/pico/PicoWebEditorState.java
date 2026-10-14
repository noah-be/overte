// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

import android.text.InputType;
import android.view.inputmethod.EditorInfo;
import android.webkit.WebView;

/** Public native editor metadata only: never field text, selection or DOM script. */
final class PicoWebEditorState {
    static final PicoWebEditorState INACTIVE = new PicoWebEditorState(false, false, false);
    final boolean focused, numeric, password;
    private PicoWebEditorState(boolean focused, boolean numeric, boolean password) {
        this.focused = focused; this.numeric = numeric; this.password = password;
    }
    static PicoWebEditorState inspect(WebView view, boolean admitted) {
        if (!admitted || !view.hasFocus() || !view.onCheckIsTextEditor()) return INACTIVE;
        EditorInfo info = new EditorInfo();
        if (view.onCreateInputConnection(info) == null) return INACTIVE;
        int kind = info.inputType & InputType.TYPE_MASK_CLASS;
        int variation = info.inputType & InputType.TYPE_MASK_VARIATION;
        boolean text = kind == InputType.TYPE_CLASS_TEXT;
        boolean number = kind == InputType.TYPE_CLASS_NUMBER;
        boolean numeric = number || kind == InputType.TYPE_CLASS_PHONE || kind == InputType.TYPE_CLASS_DATETIME;
        if (!text && !numeric) return INACTIVE;
        boolean password = text && (variation == InputType.TYPE_TEXT_VARIATION_PASSWORD
            || variation == InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD
            || variation == InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD)
            || number && variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD;
        return new PicoWebEditorState(true, numeric, password);
    }
    boolean same(PicoWebEditorState other) {
        return focused == other.focused && numeric == other.numeric && password == other.password;
    }
}
