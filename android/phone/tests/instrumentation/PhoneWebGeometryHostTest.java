// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.phone;
import java.util.Arrays;
public final class PhoneWebGeometryHostTest {
    private static void equal(int[] actual, int... expected) { if (!Arrays.equals(actual, expected)) throw new AssertionError(Arrays.toString(actual)); }
    public static void main(String[] args) {
        equal(PhoneWebGeometry.map(200, 160, new int[]{10,48,190,140}, new int[]{100,40,500,360}, new int[]{100,40,500,360}),120,136,480,320,120,136,480,320);
        equal(PhoneWebGeometry.map(200,160,new int[]{10,48,190,140},new int[]{100,40,500,360},new int[]{200,200,460,300}),120,136,480,320,200,200,460,300);
        equal(PhoneWebGeometry.map(100,100,new int[]{-20,0,120,100},new int[]{0,0,300,150},new int[]{0,0,300,150}),-60,0,360,150,0,0,300,150);
        if (PhoneWebGeometry.map(0,100,new int[]{0,48,100,100},new int[]{0,0,300,150},new int[]{0,0,300,150}) != null) throw new AssertionError();
        if (PhoneWebGeometry.map(100,100,new int[]{0,110,100,130},new int[]{0,0,300,150},new int[]{0,0,300,150}) != null) throw new AssertionError();
        System.out.println("PASS: actual scene-to-surface mapping, 48px toolbar, clipping, nonuniform scale and invalid layouts");
    }
}
