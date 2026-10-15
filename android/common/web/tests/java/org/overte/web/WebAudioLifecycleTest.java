// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;
import java.util.ArrayList;
import java.util.List;

public final class WebAudioLifecycleTest {
    static void check(boolean value) { if (!value) throw new AssertionError(); }
    static final class Output implements WebAudioLifecycle.Output {
        boolean muted, supported = true, throwsMute;
        int closed;
        List<String> effects = new ArrayList<>();
        @Override public boolean mute(boolean value) {
            effects.add("mute:" + value);
            if (throwsMute) throw new IllegalStateException();
            if (!supported) return false;
            muted = value; return true;
        }
        @Override public void closeDocument() { effects.add("close"); closed++; }
    }
    static boolean audible(WebAudioLifecycle a, WebAudioLifecycle.Ticket t, Object view, Object owner,
            long revision, long page, String url, boolean visible, boolean foreground) {
        return a.audible(t, view, owner, revision, page, url, visible, foreground, true, true);
    }
    public static void main(String[] args) {
        Object owner = new Object(), first = new Object(), second = new Object();
        Output outA = new Output(), outB = new Output();
        WebAudioLifecycle a = new WebAudioLifecycle(outA), b = new WebAudioLifecycle(outB);
        check(outA.muted && outB.muted);
        var ta = a.document(first, owner, 5, 7, "https://a.test");
        var tb = b.document(second, owner, 5, 7, "https://b.test");
        check(audible(a,ta,first,owner,5,7,"https://a.test",true,true));
        check(audible(b,tb,second,owner,5,7,"https://b.test",true,true));
        check(!outA.muted && !outB.muted);
        check(a.suspend() && outA.muted && !outB.muted && outB.closed == 0);
        check(!audible(a,ta,first,owner,5,7,"https://a.test",true,true));
        ta = a.document(first,owner,6,7,"https://a.test");
        check(!audible(a,ta,first,owner,6,7,"https://a.test",true,false));
        check(!audible(a,ta,first,owner,6,7,"https://a.test",false,true));
        check(outA.muted);
        check(!audible(a,ta,new Object(),owner,6,7,"https://a.test",true,true));
        check(!audible(a,ta,first,new Object(),6,7,"https://a.test",true,true));
        check(!audible(a,ta,first,owner,5,7,"https://a.test",true,true));
        check(!audible(a,ta,first,owner,6,8,"https://a.test",true,true));
        check(!audible(a,ta,first,owner,6,7,"https://other.test",true,true));
        check(!a.audible(ta,first,owner,6,7,"https://a.test",true,true,false,true));
        check(!a.audible(ta,first,owner,6,7,"https://a.test",true,true,true,false));
        var next = a.document(first,owner,7,8,"https://a.test/new");
        check(!audible(a,ta,first,owner,6,7,"https://a.test",true,true));
        check(audible(a,next,first,owner,7,8,"https://a.test/new",true,true));
        check(a.suspend() && b.suspend() && outA.muted && outB.muted);
        Output old = new Output(); old.supported = false;
        WebAudioLifecycle fallback = new WebAudioLifecycle(old);
        var ot = fallback.document(first,owner,5,7,"https://a.test");
        check(audible(fallback,ot,first,owner,5,7,"https://a.test",true,true) && old.closed == 0);
        check(!fallback.suspend() && fallback.closed() && old.closed == 1);
        check(!fallback.suspend() && old.closed == 1);
        check(!audible(fallback,ot,first,owner,5,7,"https://a.test",true,true));
        Output fail = new Output(); WebAudioLifecycle failed = new WebAudioLifecycle(fail); fail.throwsMute = true;
        check(!failed.suspend() && fail.closed == 1 && fail.effects.get(fail.effects.size()-1).equals("close"));
        Output unmuteFail = new Output(); WebAudioLifecycle unmute = new WebAudioLifecycle(unmuteFail);
        var ut = unmute.document(first,owner,5,7,"https://a.test"); unmuteFail.throwsMute = true;
        check(!audible(unmute,ut,first,owner,5,7,"https://a.test",true,true) && unmuteFail.closed == 1);
        final int[] effect = {0}; Runnable count = () -> effect[0]++;
        check(WebLifecycleDispatch.apply(first,first,owner,owner,second,second,8,8,count));
        check(!WebLifecycleDispatch.apply(first,first,owner,owner,second,second,8,0,count));
        check(!WebLifecycleDispatch.apply(first,new Object(),owner,owner,second,second,8,8,count));
        check(!WebLifecycleDispatch.apply(first,first,owner,new Object(),second,second,8,8,count));
        check(!WebLifecycleDispatch.apply(first,first,owner,owner,second,new Object(),8,8,count));
        check(!WebLifecycleDispatch.apply(first,first,owner,owner,second,second,7,8,count));
        check(effect[0] == 1);
        WebNavigationArchive history = new WebNavigationArchive();
        history.remember(List.of("https://a.test","https://b.test","https://c.test"),1);
        check(history.back() && history.forward());
        check(history.select(-1).equals("https://a.test") && !history.back());
        check(history.select(1).equals("https://b.test"));
        history.visit("https://new.test"); check(history.back() && !history.forward());
        for (int i = 0; i < 200; ++i) history.visit("https://history.test/"+i);
        for (int i = 0; i < 127; ++i) check(history.select(-1) != null);
        check(history.select(-1) == null);
        System.out.println("PASS: real production per-view output/lifecycle effects, unsupported/throw fallback, stale tickets, two-page isolation and bounded GET-only URL archive; no DOM/audio assertion");
    }
}
