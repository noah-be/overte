package io.highfidelity.hifiinterface;

import java.net.URI;
import java.net.URISyntaxException;

/**
 * Created by Gabriel Calero & Cristian Duarte on 4/13/18.
 */

public class HifiUtils {

    public static final String METAVERSE_BASE_URL = "https://mv.overte.org/server";

    private static HifiUtils instance;

    private HifiUtils() {
    }

    public static HifiUtils getInstance() {
        if (instance == null) {
            instance = new HifiUtils();
        }
        return instance;
    }

    public String sanitizeHifiUrl(String urlString) {
        if (urlString == null) {
            return "";
        }
        urlString = urlString.trim();
        if (!urlString.isEmpty()) {
            URI uri;
            try {
                uri = new URI(urlString);
            } catch (URISyntaxException e) {
                return urlString;
            }
            // java.net.URI represents an absent scheme as null; an empty scheme
            // is rejected by its parser, so a second empty-string check is dead.
            if (uri.getScheme() == null || isLocalhostWithPort(urlString)) {
                urlString = "hifi://" + urlString;
            }
        }
        return urlString;
    }

    private boolean isLocalhostWithPort(String value) {
        return value.matches("(?i)^localhost:[0-9]+(?:[/?#].*)?$");
    }


    public String absoluteHifiAssetUrl(String urlString) {
        return absoluteHifiAssetUrl(urlString, METAVERSE_BASE_URL);
    }

    public String absoluteHifiAssetUrl(String urlString, String baseUrl) {
        if (urlString == null) {
            return "";
        }
        urlString = urlString.trim();
        if (!urlString.isEmpty()) {
            URI uri;
            try {
                uri = new URI(urlString);
            } catch (URISyntaxException e) {
                return urlString;
            }
            if (uri.getScheme() == null) {
                if (baseUrl == null || baseUrl.trim().isEmpty()) {
                    return urlString;
                }
                String normalizedBase = baseUrl.trim();
                if (uri.getRawAuthority() != null) {
                    try {
                        URI base = new URI(normalizedBase);
                        String scheme = base.getScheme();
                        if (base.getRawAuthority() == null || scheme == null
                                || !("http".equalsIgnoreCase(scheme)
                                || "https".equalsIgnoreCase(scheme))) {
                            return urlString;
                        }
                        return ("https".equalsIgnoreCase(scheme) ? "https" : "http")
                                + ":" + urlString;
                    } catch (URISyntaxException e) {
                        return urlString;
                    }
                }
                if (normalizedBase.endsWith("/") && urlString.startsWith("/")) {
                    urlString = normalizedBase + urlString.substring(1);
                } else if (normalizedBase.endsWith("/") || urlString.startsWith("/")) {
                    urlString = normalizedBase + urlString;
                } else {
                    urlString = normalizedBase + "/" + urlString;
                }
            }
        }
        return urlString;
    }

    public native String getCurrentAddress();

    public native String protocolVersionSignature();

    public native boolean isUserLoggedIn();

    public native void updateHifiSetting(String group, String key, boolean value);
    public native boolean getHifiSettingBoolean(String group, String key, boolean defaultValue);

    public native boolean isKeepingLoggedIn();
}
