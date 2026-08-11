package io.highfidelity.hifiinterface.provider;

import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

/** Framework-free sequencing for the tagged and complete legacy place requests. */
public final class UserStoryRetrievalCoordinator {
    private UserStoryRetrievalCoordinator() {
    }

    public interface PageLoader<T> {
        void load(String tagsFilter, LoadCallback<T> callback);
    }

    public interface LoadCallback<T> {
        void success(List<T> stories);
        void failure(Exception error);
    }

    public interface Completion<T> {
        void success(List<T> taggedStories, List<T> allStories);
        void failure(Exception error);
    }

    public static <T> void retrieve(PageLoader<T> loader, String taggedFilter,
            Completion<T> completion) {
        AtomicBoolean terminal = new AtomicBoolean();
        AtomicBoolean taggedSettled = new AtomicBoolean();
        loader.load(taggedFilter, new LoadCallback<T>() {
            @Override
            public void success(List<T> taggedStories) {
                if (!taggedSettled.compareAndSet(false, true) || terminal.get()) {
                    return;
                }
                if (taggedStories == null) {
                    failOnce(terminal, completion, new Exception("Tagged stories were missing"));
                    return;
                }
                AtomicBoolean allSettled = new AtomicBoolean();
                loader.load(null, new LoadCallback<T>() {
                    @Override
                    public void success(List<T> allStories) {
                        if (!allSettled.compareAndSet(false, true) || allStories == null) {
                            if (allStories == null) {
                                failOnce(terminal, completion, new Exception("Stories were missing"));
                            }
                            return;
                        }
                        if (terminal.compareAndSet(false, true)) {
                            completion.success(taggedStories, allStories);
                        }
                    }

                    @Override
                    public void failure(Exception error) {
                        if (allSettled.compareAndSet(false, true)) {
                            failOnce(terminal, completion, normalized(error));
                        }
                    }
                });
            }

            @Override
            public void failure(Exception error) {
                if (taggedSettled.compareAndSet(false, true)) {
                    failOnce(terminal, completion, normalized(error));
                }
            }
        });
    }

    private static Exception normalized(Exception error) {
        return error == null ? new Exception("Story retrieval failed") : error;
    }

    private static <T> void failOnce(AtomicBoolean terminal, Completion<T> completion,
            Exception error) {
        if (terminal.compareAndSet(false, true)) {
            completion.failure(error);
        }
    }
}
