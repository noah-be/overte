// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

import android.app.Activity;
import android.text.Editable;
import android.text.InputType;
import android.text.Selection;
import android.text.SpannableStringBuilder;
import android.view.inputmethod.BaseInputConnection;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.webkit.WebView;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

/** Real Android API execution; fixture provider metadata is not Chromium DOM evidence. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = {26, 35}, manifest = Config.NONE)
public final class PicoWebEditorApiTest {
    private static final class ProviderBoundary extends WebView {
        int type = InputType.TYPE_CLASS_TEXT, inspections;
        boolean editable = true, connected = true, providerFocus = true;
        final Editable document = new SpannableStringBuilder("original selection");
        final InputConnection input = new BaseInputConnection(this, true) {
            @Override public Editable getEditable() { return document; }
        };
        ProviderBoundary(Activity activity) { super(activity); setFocusableInTouchMode(true); }
        // Robolectric has no Chromium DOM focus provider. Supply that state
        // explicitly while executing actual EditorInfo/InputConnection APIs.
        @Override public boolean hasFocus() { return providerFocus; }
        @Override public boolean onCheckIsTextEditor() { return editable; }
        @Override public InputConnection onCreateInputConnection(EditorInfo info) {
            ++inspections; info.inputType = type;
            info.initialSelStart = Selection.getSelectionStart(document);
            info.initialSelEnd = Selection.getSelectionEnd(document);
            return connected ? input : null;
        }
    }
    private ProviderBoundary view() {
        Activity activity = Robolectric.buildActivity(Activity.class).setup().get();
        ProviderBoundary view = new ProviderBoundary(activity);
        activity.setContentView(view);
        Selection.setSelection(view.document, 3, 8); return view;
    }
    @Test public void maps_actual_native_input_types_without_reading_content() {
        ProviderBoundary view = view();
        int[][] cases = {
            {InputType.TYPE_CLASS_TEXT,0,0},
            {InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE,0,0},
            {InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD,0,1},
            {InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD,0,1},
            {InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD,0,1},
            {InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL,1,0},
            {InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_VARIATION_PASSWORD,1,1},
            {InputType.TYPE_CLASS_PHONE,1,0}, {InputType.TYPE_CLASS_DATETIME,1,0}
        };
        for (int[] value : cases) {
            view.type = value[0]; PicoWebEditorState state = PicoWebEditorState.inspect(view,true);
            assertTrue(state.focused); assertEquals(value[1]!=0,state.numeric); assertEquals(value[2]!=0,state.password);
            assertEquals("original selection",view.document.toString());
            assertEquals(3,Selection.getSelectionStart(view.document)); assertEquals(8,Selection.getSelectionEnd(view.document));
        }
        assertEquals(cases.length,view.inspections);
    }
    @Test public void rejects_inactive_blurred_non_editor_and_absent_connection() {
        ProviderBoundary view = view();
        assertFalse(PicoWebEditorState.inspect(view,false).focused); assertEquals(0,view.inspections);
        view.editable=false; assertFalse(PicoWebEditorState.inspect(view,true).focused); assertEquals(0,view.inspections);
        view.editable=true; view.connected=false; assertFalse(PicoWebEditorState.inspect(view,true).focused);
        view.connected=true; view.type=InputType.TYPE_NULL; assertFalse(PicoWebEditorState.inspect(view,true).focused);
        view.type=InputType.TYPE_CLASS_TEXT; view.providerFocus=false;
        assertFalse(PicoWebEditorState.inspect(view,true).focused);
    }
    @Test public void observation_preserves_actual_composition_commit_and_selection() {
        ProviderBoundary view = view(); Selection.setSelection(view.document,view.document.length());
        assertTrue(PicoTextInput.text(view.input,"pré",true));
        String composing=view.document.toString(); int cursor=Selection.getSelectionStart(view.document);
        assertTrue(PicoWebEditorState.inspect(view,true).focused);
        assertEquals(composing,view.document.toString()); assertEquals(cursor,Selection.getSelectionStart(view.document));
        assertTrue(PicoTextInput.text(view.input,"Unicode Ä🙂",false));
        assertTrue(view.document.toString().contains("Unicode Ä🙂"));
        assertTrue(PicoTextInput.text(view.input,"",true));
        assertTrue(PicoWebEditorState.inspect(view,true).focused);
    }
}
