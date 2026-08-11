package io.highfidelity.hifiinterface.provider;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public final class UserStoryRetrievalCoordinatorStandaloneTest {
    private static int assertions;

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static final class Result implements UserStoryRetrievalCoordinator.Completion<String> {
        int successes;
        int failures;
        List<String> tagged;
        List<String> all;

        @Override
        public void success(List<String> taggedStories, List<String> allStories) {
            successes++;
            tagged = taggedStories;
            all = allStories;
        }

        @Override
        public void failure(Exception error) {
            failures++;
            check(error != null, "failures must carry an exception");
        }
    }

    public static void main(String[] args) {
        Result success = new Result();
        int[] calls = { 0 };
        UserStoryRetrievalCoordinator.retrieve((tags, callback) -> {
            calls[0]++;
            if (tags == null) {
                callback.success(Arrays.asList("tagged", "other"));
            } else {
                check("mobile".equals(tags), "tag filter must reach the first request");
                callback.success(Collections.singletonList("tagged"));
            }
        }, "mobile", success);
        check(calls[0] == 2, "success must make exactly two requests");
        check(success.successes == 1 && success.failures == 0, "success must be terminal once");
        check(success.tagged.size() == 1 && success.all.size() == 2, "both results must be preserved");

        Result taggedFailure = new Result();
        int[] taggedCalls = { 0 };
        UserStoryRetrievalCoordinator.retrieve((tags, callback) -> {
            taggedCalls[0]++;
            callback.failure(null);
            callback.success(Collections.singletonList("late"));
        }, "mobile", taggedFailure);
        check(taggedCalls[0] == 1, "tagged failure must not start the full request");
        check(taggedFailure.failures == 1 && taggedFailure.successes == 0,
                "tagged failure must terminate exactly once");

        Result fullFailure = new Result();
        UserStoryRetrievalCoordinator.retrieve((tags, callback) -> {
            if (tags == null) {
                callback.failure(new Exception("full"));
                callback.success(Collections.singletonList("late"));
            } else {
                callback.success(Collections.singletonList("tagged"));
            }
        }, "mobile", fullFailure);
        check(fullFailure.failures == 1 && fullFailure.successes == 0,
                "full failure must terminate exactly once");

        Result missing = new Result();
        UserStoryRetrievalCoordinator.retrieve((tags, callback) -> callback.success(null),
                "mobile", missing);
        check(missing.failures == 1 && missing.successes == 0, "null results must fail closed");

        Result retry = new Result();
        UserStoryRetrievalCoordinator.retrieve((tags, callback) -> callback.failure(new Exception("first")),
                "mobile", retry);
        UserStoryRetrievalCoordinator.retrieve((tags, callback) -> {
            if (tags == null) callback.success(Collections.singletonList("all"));
            else callback.success(Collections.singletonList("tagged"));
        }, "mobile", retry);
        check(retry.failures == 1 && retry.successes == 1,
                "a later independent retrieval must retry after failure");

        System.out.println("UserStoryRetrievalCoordinatorStandaloneTest: " + assertions
                + " assertions passed");
    }
}
