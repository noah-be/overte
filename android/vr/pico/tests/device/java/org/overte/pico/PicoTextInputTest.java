// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;
import android.view.inputmethod.InputConnection;
import java.lang.reflect.Proxy;
public final class PicoTextInputTest {
    static String operation;
    static Object[] arguments;
    static String selection;
    static void check(boolean value) { if (!value) throw new AssertionError("Pico editor contract"); }
    public static void main(String[] unused) {
        InputConnection input = (InputConnection) Proxy.newProxyInstance(InputConnection.class.getClassLoader(),
            new Class<?>[] {InputConnection.class}, (proxy, method, args) -> {
                operation = method.getName(); arguments = args;
                if (operation.equals("getSelectedText")) return selection;
                return method.getReturnType() == boolean.class ? Boolean.TRUE : null;
            });
        for (String text : new String[] {"", "abc", "e\u0301", "😀", "👩‍💻", "עברית", "日本語", "\n\t", "\"');alert(1);//"}) {
            check(PicoTextInput.text(input, text, false));
            check(operation.equals("commitText") && arguments[0].equals(text));
        }
        check(PicoTextInput.text(input, "pré", true)); check(operation.equals("setComposingText"));
        check(PicoTextInput.text(input, "", true)); check(operation.equals("finishComposingText"));
        check(!PicoTextInput.text(null, "abc", false));
        check(!PicoTextInput.valid(null)); check(!PicoTextInput.valid("\ud800")); check(!PicoTextInput.valid("\udc00"));
        check(PicoTextInput.valid("x".repeat(4096))); check(!PicoTextInput.valid("x".repeat(4097)));
        for (int i = 0; i < 32; ++i) if (i != 9 && i != 10) check(!PicoTextInput.valid(Character.toString((char)i)));
        selection = null;
        check(PicoTextInput.key(input, 67)); check(operation.equals("deleteSurroundingTextInCodePoints"));
        check(arguments[0].equals(1) && arguments[1].equals(0));
        check(PicoTextInput.key(input, 112)); check(arguments[0].equals(0) && arguments[1].equals(1));
        selection = "😀";
        check(PicoTextInput.key(input, 67)); check(operation.equals("commitText") && arguments[0].equals(""));
        check(!PicoTextInput.key(input, 0)); check(!PicoTextInput.key(null, 67));
        System.out.println("Pico production editor Unicode/composition/selection/delete boundaries PASS (test InputConnection)");
    }
}
