// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;
import java.nio.ByteBuffer;

public final class WebFrameTest {
    private static void check(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] arguments) {
        Object activity = new Object(), replacement = new Object();
        WebFrameGate gate = new WebFrameGate(activity);
        check(gate.capture() == null);
        WebFrameGate.Ticket initial = gate.begin(activity,1,1,1,"https://one.test/document");
        check(initial != null && gate.capture() == null); // No pixels before the actual visual callback.
        check(gate.visual(initial,100) && gate.admits(initial));
        check(!gate.fresh(initial,99) && !gate.fresh(initial,100));
        check(gate.deliver(initial,101) && !gate.deliver(initial,101));
        check(!gate.deliver(initial,100) && gate.deliver(initial,102));
        gate.invalidate(); check(!gate.admits(initial) && !gate.visual(initial,100)); // Hide/pause while GL is in flight.
        WebFrameGate.Ticket resumed = gate.begin(activity,1,1,1,"https://one.test/document");
        check(!gate.visual(initial,100) && !gate.admits(resumed));
        check(gate.visual(resumed,100) && gate.admits(resumed));
        WebFrameGate otherInstance = new WebFrameGate(activity);
        WebFrameGate.Ticket other = otherInstance.begin(activity,1,1,1,"https://one.test/document");
        check(otherInstance.visual(other,100) && !otherInstance.deliver(resumed,1000));
        otherInstance.close();
        WebFrameGate.Ticket navigated = gate.begin(activity,1,2,1,"https://foreign.test/new");
        check(!gate.admits(resumed) && !gate.visual(resumed,100)); // A foreign document gets no old frame lease.
        check(gate.visual(navigated,100) && gate.matches(1,2,1,"https://foreign.test/new"));
        check(!gate.matches(1,2,1,"https://one.test/document"));
        WebFrameGate.Ticket resized = gate.begin(activity,1,2,2,"https://foreign.test/new");
        check(!gate.admits(navigated) && !gate.visual(navigated,100));
        check(gate.visual(resized,100));
        WebFrameGate.Ticket rebound = gate.begin(activity,2,2,2,"https://foreign.test/new");
        check(!gate.admits(resized) && !gate.visual(resized,100));
        check(gate.visual(rebound,100));
        check(gate.begin(replacement,2,2,2,"https://foreign.test/new") == null && !gate.admits(rebound));
        for (long surface = 3; surface < 30; ++surface) {
            WebFrameGate.Ticket old = gate.begin(activity,2,3,surface,"https://one.test/next");
            WebFrameGate.Ticket next = gate.begin(activity,2,4,surface+1,"https://one.test/next");
            check(!gate.visual(old,100)); check(gate.visual(next,100)); check(!gate.admits(old) && gate.admits(next));
        }
        WebFrameGate.Ticket inFlight = gate.capture();
        java.util.concurrent.CountDownLatch started = new java.util.concurrent.CountDownLatch(1);
        java.util.concurrent.CountDownLatch released = new java.util.concurrent.CountDownLatch(1);
        java.util.concurrent.atomic.AtomicBoolean rejected = new java.util.concurrent.atomic.AtomicBoolean();
        Thread gpu = new Thread(() -> {
            started.countDown();
            try { released.await(); } catch (InterruptedException failure) { throw new AssertionError(failure); }
            rejected.set(!gate.deliver(inFlight,1000));
        });
        gpu.start();
        try { started.await(); } catch (InterruptedException failure) { throw new AssertionError(failure); }
        gate.invalidate(); released.countDown();
        try { gpu.join(); } catch (InterruptedException failure) { throw new AssertionError(failure); }
        check(rejected.get());
        WebFrameGate.Ticket last = gate.begin(activity,2,4,33,"https://one.test/next"); gate.close();
        check(!gate.visual(last,100) && !gate.admits(last) && gate.begin(activity,3,5,40,"https://one.test") == null);
        // Simulate a two-row GL readback with pixel/row padding: bottom row blue+white,
        // top row red+half-alpha green. Packing must flip rows and retain alpha/BGRA.
        ByteBuffer raw = ByteBuffer.allocate(24);
        int[][] rgba = {{0,0,255,255},{255,255,255,255},{255,0,0,255},{0,64,0,128}};
        for (int pixel=0; pixel<4; ++pixel) for (int channel=0; channel<4; ++channel)
            raw.put((pixel/2)*12+(pixel%2)*5+channel,(byte)rgba[pixel][channel]);
        ByteBuffer packed = ByteBuffer.allocateDirect(16);
        WebFramePixels.pack(raw,packed,2,2,12,5);
        int[] expected = {0,0,255,255,0,64,0,128,255,0,0,255,255,255,255,255};
        for (int index=0; index<16; ++index) check((packed.get(index)&255)==expected[index]);
        check(packed.position()==0 && packed.limit()==16);
        int[][] invalid = {{0,2,12,5},{2,0,12,5},{2049,2,12,5},{2,2,9,5},{2,2,12,3}};
        for (int[] layout : invalid) {
            boolean denied=false;
            try { WebFramePixels.pack(raw,packed,layout[0],layout[1],layout[2],layout[3]); }
            catch (IllegalArgumentException expectedFailure) { denied=true; }
            check(denied);
        }
        raw.limit(8); boolean denied=false;
        try { WebFramePixels.pack(raw,packed,2,2,12,5); } catch (IllegalArgumentException expectedFailure) { denied=true; }
        check(denied);
        System.out.println("PASS: real frame leases reject late visual/GL results across document, source, resize, owner, pause and close; padded RGBA readback flips to BGRA with alpha");
    }
}
