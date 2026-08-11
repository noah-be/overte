package io.highfidelity.hifiinterface.task;

import android.os.AsyncTask;
import android.util.Log;

import java.io.IOException;
import java.net.URL;

import io.highfidelity.hifiinterface.HifiUtils;

/**
 * This is a temporary solution until the profile picture URL is
 * available in an API
 */
public class DownloadProfileImageTask extends AsyncTask<String, Void, String> {
    // Note: This should now be available in the API, correct?
    private static final String BASE_PROFILE_URL = "https://mv.overte.org/server";
    private static final String TAG = "Interface";

    private final DownloadProfileImageResultProcessor mResultProcessor;

    public interface DownloadProfileImageResultProcessor {
        void onResultAvailable(String url);
    }

    public DownloadProfileImageTask(DownloadProfileImageResultProcessor resultProcessor) {
        mResultProcessor = resultProcessor;
    }

    @Override
    protected String doInBackground(String... usernames) {
        URL userPage = null;
        for (String username: usernames) {
            try {
                userPage = new URL(BASE_PROFILE_URL + "/users/" + username);
                String profilePage = LegacyProfilePagePolicy.read(userPage.openConnection());
                String profileImageUrl = LegacyProfilePagePolicy.extractProfileImageUrl(profilePage);
                if (profileImageUrl != null) {
                    return HifiUtils.getInstance().absoluteHifiAssetUrl(
                            profileImageUrl, BASE_PROFILE_URL);
                }
            } catch (IOException e) {
                Log.e(TAG, "Error getting profile picture for username " + username);
            }
        }
        return null;
    }

    @Override
    protected void onPostExecute(String url) {
        super.onPostExecute(url);
        if (mResultProcessor != null) {
            mResultProcessor.onResultAvailable(url);
        }
    }
}
