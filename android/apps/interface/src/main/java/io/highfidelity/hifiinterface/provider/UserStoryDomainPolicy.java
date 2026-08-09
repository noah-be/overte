package io.highfidelity.hifiinterface.provider;

import io.highfidelity.hifiinterface.HifiUtils;

/** Framework-free URL and pagination rules for the legacy place provider. */
public final class UserStoryDomainPolicy {
    private UserStoryDomainPolicy() {
    }

    public static String destinationUrl(String placeName, String path) {
        return HifiUtils.getInstance().sanitizeHifiUrl(placeName) + "/" + path;
    }

    public static String thumbnailUrl(String thumbnail) {
        return HifiUtils.getInstance().absoluteHifiAssetUrl(thumbnail);
    }

    public static boolean shouldRequestNextPage(int currentPage, int totalPages, int maxPages) {
        return currentPage < totalPages && currentPage <= maxPages;
    }
}
