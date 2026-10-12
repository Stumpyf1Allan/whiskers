package io.github.stumpyf1allan.whiskers;

import android.annotation.TargetApi;
import android.content.Context;
import android.net.http.HttpEngine;
import android.net.http.NetworkException;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Android 14's built-in copy of Chrome's network engine (HttpEngine), kept in a class of
 * its own so that older phones never load it.
 *
 * <p>This is the phone's answer to curl_cffi on the PC: Yahoo turns away connections whose
 * handshake doesn't look like a browser's, and this one is a browser's.
 */
@TargetApi(34)
final class ChromiumNet {
    private ChromiumNet() {
    }

    static Object make(Context context) {
        return new HttpEngine.Builder(context).build();
    }

    static HttpURLConnection open(Object engine, URL url) throws IOException {
        return (HttpURLConnection) ((HttpEngine) engine).openConnection(url);
    }

    /** True for the engine's errors that mean no network, rather than a difficult server. */
    static boolean looksOffline(Throwable e) {
        for (Throwable t = e; t != null; t = t.getCause()) {
            if (t instanceof NetworkException) {
                int c = ((NetworkException) t).getErrorCode();
                return c == NetworkException.ERROR_HOSTNAME_NOT_RESOLVED
                        || c == NetworkException.ERROR_INTERNET_DISCONNECTED
                        || c == NetworkException.ERROR_ADDRESS_UNREACHABLE
                        || c == NetworkException.ERROR_CONNECTION_REFUSED
                        || c == NetworkException.ERROR_CONNECTION_TIMED_OUT;
            }
        }
        return false;
    }
}
