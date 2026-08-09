package io.highfidelity.hifiinterface.provider;

import java.util.Collections;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.CountDownLatch;

public final class LegacyLatestRequestGateStandaloneTest {
    private static int assertions;

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        LegacyLatestRequestGate gate = new LegacyLatestRequestGate();
        long first = gate.begin();
        check(first > 0, "tickets must be positive");
        check(gate.isCurrent(first), "first ticket must be current");
        check(!gate.isCurrent(0), "zero must never be current");
        check(!gate.isCurrent(-1), "negative tickets must never be current");
        long second = gate.begin();
        check(second != first, "new requests need a new ticket");
        check(!gate.isCurrent(first), "new requests must invalidate old tickets");
        check(gate.isCurrent(second), "latest ticket must remain current");

        final int threadCount = 32;
        Set<Long> tickets = Collections.synchronizedSet(new HashSet<>());
        CountDownLatch ready = new CountDownLatch(threadCount);
        CountDownLatch start = new CountDownLatch(1);
        Thread[] threads = new Thread[threadCount];
        for (int index = 0; index < threadCount; ++index) {
            threads[index] = new Thread(() -> {
                ready.countDown();
                try {
                    start.await();
                } catch (InterruptedException error) {
                    throw new RuntimeException(error);
                }
                tickets.add(gate.begin());
            });
            threads[index].start();
        }
        ready.await();
        start.countDown();
        for (Thread thread : threads) {
            thread.join();
        }
        check(tickets.size() == threadCount,
                "parallel requests must receive unique tickets");
        long currentCount = tickets.stream().filter(gate::isCurrent).count();
        check(currentCount == 1,
                "exactly one parallel request ticket must remain current");
        System.out.println("LegacyLatestRequestGateStandaloneTest: " + assertions
                + " assertions passed");
    }
}
