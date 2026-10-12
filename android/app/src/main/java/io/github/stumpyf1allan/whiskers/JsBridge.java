package io.github.stumpyf1allan.whiskers;

import android.util.Base64;
import android.webkit.JavascriptInterface;

/**
 * What the page can ask the app for, as window.WhiskersAndroid. The page is only ever
 * Whiskers' own, from 127.0.0.1: every other address opens in the phone's browser instead
 * of this window (MainActivity), so no other page can reach these.
 */
final class JsBridge {
    private final MainActivity activity;

    JsBridge(MainActivity activity) {
        this.activity = activity;
    }

    /** A file the server built (the spreadsheet, the plan file), into Downloads. */
    @JavascriptInterface
    public String saveFile(String name, String mime, String base64) {
        try {
            return Downloads.save(activity, name, mime, Base64.decode(base64, Base64.DEFAULT));
        } catch (Exception e) {
            return "error: " + e.getMessage();
        }
    }

    /** "light" or "dark": the strips above and below the page follow the page's theme. */
    @JavascriptInterface
    public void themeChanged(String theme) {
        activity.runOnUiThread(() -> activity.applyTheme("dark".equals(theme)));
    }
}
