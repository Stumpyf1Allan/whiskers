package io.github.stumpyf1allan.whiskers;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.util.ArrayList;
import java.util.List;

/**
 * Starts Whiskers' own Python, once per process, off the main thread.
 *
 * <p>The first start on a new install unpacks Python and takes a few seconds; later ones
 * are quick. Python then stays up for as long as Android keeps the process, so a window
 * that is closed and reopened finds the server already answering.
 */
final class PythonServer {
    interface Listener {
        void onReady(String url);

        void onFailed(String why);
    }

    private static final String TAG = "Whiskers";
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final List<Listener> waiting = new ArrayList<>();
    private static String url;
    private static String failure;
    private static boolean starting;

    private PythonServer() {
    }

    /** Calls back on the main thread: at once if Whiskers is already running. */
    static synchronized void start(Context context, Listener listener) {
        if (url != null) {
            final String u = url;
            MAIN.post(() -> listener.onReady(u));
            return;
        }
        if (failure != null) {
            final String f = failure;
            MAIN.post(() -> listener.onFailed(f));
            return;
        }
        if (!waiting.contains(listener)) waiting.add(listener);
        if (starting) return;
        starting = true;
        final Context app = context.getApplicationContext();
        Native.init(app);
        new Thread(() -> {
            String u = null;
            String f = null;
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(app));
                PyObject boot = Python.getInstance().getModule("whiskers_android");
                u = boot.callAttr("start",
                        app.getFilesDir().getAbsolutePath(),
                        app.getCacheDir().getAbsolutePath(),
                        BuildConfig.VERSION_NAME,
                        BuildConfig.DEBUG).toString();
                Log.i(TAG, "Whiskers " + BuildConfig.VERSION_NAME + " is running");
            } catch (Throwable t) {
                f = Log.getStackTraceString(t);
                Log.e(TAG, "Whiskers didn't start", t);
            }
            finish(u, f);
        }, "whiskers-start").start();
    }

    /** Lets "Try again" start from scratch after a failure. */
    static synchronized void forgetFailure() {
        failure = null;
    }

    static synchronized void forget(Listener listener) {
        waiting.remove(listener);
    }

    private static synchronized void finish(String u, String f) {
        url = u;
        failure = (u == null) ? (f == null ? "Unknown problem" : f) : null;
        starting = false;
        final List<Listener> now = new ArrayList<>(waiting);
        waiting.clear();
        final String ok = url;
        final String bad = failure;
        for (Listener l : now) {
            MAIN.post(() -> {
                if (ok != null) l.onReady(ok);
                else l.onFailed(bad);
            });
        }
    }
}
