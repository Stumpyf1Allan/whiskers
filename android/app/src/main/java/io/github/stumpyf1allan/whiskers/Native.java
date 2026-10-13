package io.github.stumpyf1allan.whiskers;

import android.annotation.SuppressLint;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.util.Base64;
import android.util.Log;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * What Whiskers' Python asks the phone to do (folio/android.py describes each one).
 *
 * <p>Static, because Python calls it from its own threads with no Activity to hand, and
 * every argument and answer is a plain string, which crosses Chaquopy's bridge with
 * nothing to convert.
 */
public final class Native {
    private static final String TAG = "Whiskers";
    private static final int MAX_BODY = 64 * 1024 * 1024;

    @SuppressLint("StaticFieldLeak") // the Application context, which lives as long as the process
    private static Context app;
    private static Object chromium;            // android.net.http.HttpEngine, from Android 14
    private static boolean chromiumTried;

    private Native() {
    }

    static void init(Context context) {
        app = context.getApplicationContext();
    }

    /** "chromium" when requests go through Android's built-in Chrome engine, else "android". */
    public static String engine() {
        return chromium() != null ? "chromium" : "android";
    }

    private static synchronized Object chromium() {
        if (!chromiumTried) {
            chromiumTried = true;
            if (Build.VERSION.SDK_INT >= 34 && app != null) {
                try {
                    chromium = ChromiumNet.make(app);
                } catch (Throwable t) {
                    Log.w(TAG, "Android's built-in Chrome engine isn't available", t);
                }
            }
        }
        return chromium;
    }

    /**
     * GET a URL. Returns JSON: {status, headers, body (base64), via}, or {error, offline}
     * when no answer came back at all, which Python turns into the same errors it raises
     * on the PC. "offline" is true only when the failure looks like having no network
     * (no address, nothing to connect to), which is what puts Whiskers into its
     * offline pause; a server that resets or stalls the request doesn't.
     */
    public static String fetch(String url, String headersJson, int timeoutMs) {
        HttpURLConnection c = null;
        try {
            URL u = new URL(url);
            Object engine = chromium();
            String via;
            if (engine != null && Build.VERSION.SDK_INT >= 34) {
                c = ChromiumNet.open(engine, u);
                via = "chromium";
            } else {
                c = (HttpURLConnection) u.openConnection();
                via = "android";
            }
            c.setConnectTimeout(timeoutMs);
            c.setReadTimeout(timeoutMs);
            c.setInstanceFollowRedirects(true);
            JSONObject h = new JSONObject(headersJson == null || headersJson.isEmpty() ? "{}" : headersJson);
            for (Iterator<String> it = h.keys(); it.hasNext(); ) {
                String k = it.next();
                c.setRequestProperty(k, h.getString(k));
            }
            int status = c.getResponseCode();
            InputStream in = status >= 400 ? c.getErrorStream() : c.getInputStream();
            byte[] body = in == null ? new byte[0] : readAll(in);
            JSONObject headers = new JSONObject();
            for (Map.Entry<String, List<String>> e : c.getHeaderFields().entrySet()) {
                if (e.getKey() != null && e.getValue() != null && !e.getValue().isEmpty()) {
                    headers.put(e.getKey(), e.getValue().get(0));
                }
            }
            JSONObject out = new JSONObject();
            out.put("status", status);
            out.put("headers", headers);
            out.put("via", via);
            out.put("body", Base64.encodeToString(body, Base64.NO_WRAP));
            return out.toString();
        } catch (Exception e) {
            return error(e.getClass().getSimpleName() + ": " + e.getMessage(), looksOffline(e));
        } finally {
            if (c != null) c.disconnect();
        }
    }

    /** A web page in the phone's browser, or an email address in its mail app. */
    public static boolean openUrl(String url) {
        Uri u = Uri.parse(url);
        String scheme = u.getScheme() == null ? "" : u.getScheme().toLowerCase(Locale.ROOT);
        if (!scheme.equals("https") && !scheme.equals("http") && !scheme.equals("mailto")) return false;
        Intent i = new Intent(scheme.equals("mailto") ? Intent.ACTION_SENDTO : Intent.ACTION_VIEW, u);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            Context from = MainActivity.current();
            (from != null ? from : app).startActivity(i);
            return true;
        } catch (ActivityNotFoundException e) {
            return false;
        }
    }

    /**
     * Hand a verified update to Android's installer, which shows what it is and asks
     * before installing. The first time, Android wants the person to allow Whiskers to
     * install apps; this opens that switch and answers "allow".
     */
    public static String installApk(String path) {
        File f = new File(path);
        if (!f.isFile()) return "the download has gone";
        Context from = MainActivity.current();
        Context ctx = from != null ? from : app;
        try {
            if (!app.getPackageManager().canRequestPackageInstalls()) {
                Intent allow = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:" + app.getPackageName()));
                allow.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                ctx.startActivity(allow);
                return "allow";
            }
            Intent i = new Intent(Intent.ACTION_VIEW);
            i.setDataAndType(UpdateProvider.uriFor(app, f), "application/vnd.android.package-archive");
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            ctx.startActivity(i);
            return "started";
        } catch (ActivityNotFoundException e) {
            return "no installer answered";
        }
    }

    /**
     * Read a file the person chose in Android's picker (the PC's copy of Whiskers, in
     * OneDrive or Google Drive). Returns JSON {body (base64)}, or {error, offline}.
     * MainActivity kept lasting permission to read it, so this works on later days too,
     * for as long as the file is there and its cloud app can fetch it.
     */
    public static String readDocument(String uri) {
        if (app == null) return error("the app isn't ready yet", false);
        Uri u = Uri.parse(uri);
        if (!"content".equals(u.getScheme())) return error("not a file chosen in the picker", false);
        try {
            InputStream in = app.getContentResolver().openInputStream(u);
            if (in == null) return error("the file couldn't be opened", false);
            byte[] body = readAll(in);            // closes the stream
            return new JSONObject().put("body", Base64.encodeToString(body, Base64.NO_WRAP)).toString();
        } catch (SecurityException e) {
            return error("Whiskers is no longer allowed to read that file, so choose it again", false);
        } catch (Exception e) {
            return error(e.getClass().getSimpleName() + ": " + e.getMessage(), looksOffline(e));
        }
    }

    private static byte[] readAll(InputStream in) throws IOException {
        try (InputStream s = in; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[64 * 1024];
            int n;
            while ((n = s.read(buf)) != -1) {
                out.write(buf, 0, n);
                if (out.size() > MAX_BODY) throw new IOException("answer far bigger than expected");
            }
            return out.toByteArray();
        }
    }

    private static boolean looksOffline(Throwable e) {
        if (e instanceof java.net.UnknownHostException || e instanceof java.net.ConnectException
                || e instanceof java.net.NoRouteToHostException) {
            return true;
        }
        return Build.VERSION.SDK_INT >= 34 && ChromiumNet.looksOffline(e);
    }

    private static String error(String why, boolean offline) {
        try {
            return new JSONObject().put("error", why).put("offline", offline).toString();
        } catch (JSONException e) {
            return "{\"error\": \"unknown\"}";
        }
    }
}
