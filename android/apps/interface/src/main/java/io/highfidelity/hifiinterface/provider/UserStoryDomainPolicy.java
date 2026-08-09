package io.highfidelity.hifiinterface.provider;

import io.highfidelity.hifiinterface.HifiUtils;

/** Framework-free URL and pagination rules for the legacy place provider. */
public final class UserStoryDomainPolicy {
    public enum PageDecision { INVALID, STOP, CONTINUE }

    private UserStoryDomainPolicy() {
    }

    public static String destinationUrl(String placeName, String path) {
        String destination = HifiUtils.getInstance().sanitizeHifiUrl(placeName);
        if (destination.isEmpty()) {
            return "";
        }
        if (path == null || path.isEmpty()) {
            return destination;
        }
        if (destination.endsWith("/") && path.startsWith("/")) {
            return destination + path.substring(1);
        }
        if (destination.endsWith("/") || path.startsWith("/")) {
            return destination + path;
        }
        return destination + "/" + path;
    }

    public static String thumbnailUrl(String thumbnail) {
        return HifiUtils.getInstance().absoluteHifiAssetUrl(thumbnail);
    }

    public static boolean shouldRequestNextPage(int currentPage, int totalPages, int maxPages) {
        return currentPage > 0 && totalPages > 0 && maxPages > 0
                && currentPage < totalPages && currentPage < maxPages;
    }

    public static PageDecision classifyPage(boolean successfulResponse, boolean bodyPresent,
            boolean storiesPresent, int currentPage, int totalPages, int maxPages) {
        if (!successfulResponse || !bodyPresent || !storiesPresent
                || currentPage <= 0 || totalPages <= 0 || currentPage > totalPages) {
            return PageDecision.INVALID;
        }
        return shouldRequestNextPage(currentPage, totalPages, maxPages)
                ? PageDecision.CONTINUE : PageDecision.STOP;
    }
}
