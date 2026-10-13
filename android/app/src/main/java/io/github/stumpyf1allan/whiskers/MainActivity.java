package io.github.stumpyf1allan.whiskers;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.res.Configuration;
import android.database.Cursor;
import android.graphics.Color;
import android.graphics.Insets;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.webkit.ConsoleMessage;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.lang.ref.WeakReference;
import java.util.Calendar;

/**
 * The one window: Whiskers' own page, full-screen, served by its Python inside the app.
 *
 * <p>While Python starts, a small start-up screen shows. Anything that isn't Whiskers' own
 * address (a web link, an email address) opens in the phone's own apps rather than in
 * here. Files the page asks for come from the system file picker; files it hands out go to
 * Downloads (JsBridge).
 */
public class MainActivity extends Activity implements PythonServer.Listener {
    private static final String TAG = "Whiskers";
    private static final int PICK_FILE = 41;
    private static final int PICK_SYNC = 42;
    /** Opens a given screen, e.g. "holdings". The emulator check uses it for screenshots. */
    static final String EXTRA_VIEW = "whiskers.view";
    private static final int MATCH = ViewGroup.LayoutParams.MATCH_PARENT;
    private static final int WRAP = ViewGroup.LayoutParams.WRAP_CONTENT;
    // The page's own --ground and --ink colours (styles.css), light and dark.
    private static final int GROUND_LIGHT = 0xFFF3F5F7;
    private static final int GROUND_DARK = 0xFF0F1419;
    private static final int INK_LIGHT = 0xFF15202B;
    private static final int INK_DARK = 0xFFE5ECF2;

    private static WeakReference<MainActivity> current = new WeakReference<>(null);

    private FrameLayout root;
    private WebView web;
    private ScrollView splashScroll;
    private TextView splashTitle;
    private TextView splashText;
    private ProgressBar spinner;
    private Button retry;
    private ValueCallback<Uri[]> chooser;
    private String serverUrl;
    private boolean pageShown;
    private boolean loadFailed;

    /** The window on screen now, if there is one: links and the installer open from it. */
    static Context current() {
        return current.get();
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        current = new WeakReference<>(this);
        root = new FrameLayout(this);
        web = new WebView(this);
        web.setVisibility(View.INVISIBLE);
        root.addView(web, new FrameLayout.LayoutParams(MATCH, MATCH));
        root.addView(buildSplash(), new FrameLayout.LayoutParams(MATCH, MATCH));
        setContentView(root);
        edgeToEdge();
        // The page's default theme darkens from 7pm to 7am; the page corrects this as soon
        // as it loads if a different theme was chosen.
        int hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY);
        applyTheme(hour >= 19 || hour < 7);
        setUpWeb();
        PythonServer.start(this, this);
    }

    // ---------------------------------------------------------------- start-up screen

    private View buildSplash() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        int pad = dp(28);
        box.setPadding(pad, pad, pad, pad);

        ImageView icon = new ImageView(this);
        icon.setImageResource(R.mipmap.ic_launcher);
        box.addView(icon, new LinearLayout.LayoutParams(dp(88), dp(88)));

        splashTitle = new TextView(this);
        splashTitle.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        splashTitle.setTypeface(Typeface.DEFAULT_BOLD);
        splashTitle.setGravity(Gravity.CENTER);
        splashTitle.setText(R.string.starting);
        box.addView(splashTitle, spaced(dp(18)));

        splashText = new TextView(this);
        splashText.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        splashText.setGravity(Gravity.CENTER);
        splashText.setText(R.string.starting_note);
        box.addView(splashText, spaced(dp(8)));

        spinner = new ProgressBar(this);
        box.addView(spinner, spaced(dp(20)));

        retry = new Button(this);
        retry.setText(R.string.try_again);
        retry.setVisibility(View.GONE);
        retry.setOnClickListener(v -> tryAgain());
        box.addView(retry, spaced(dp(16)));

        splashScroll = new ScrollView(this);
        splashScroll.setFillViewport(true);
        splashScroll.addView(box, new ScrollView.LayoutParams(MATCH, WRAP));
        return splashScroll;
    }

    private LinearLayout.LayoutParams spaced(int top) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(WRAP, WRAP);
        p.topMargin = top;
        return p;
    }

    private void showFailure(String why) {
        spinner.setVisibility(View.GONE);
        splashTitle.setText(R.string.failed);
        splashText.setGravity(Gravity.START);
        splashText.setTextIsSelectable(true);
        splashText.setText(why);
        retry.setVisibility(View.VISIBLE);
        splashScroll.setVisibility(View.VISIBLE);
        web.setVisibility(View.INVISIBLE);
        pageShown = false;
    }

    private void tryAgain() {
        retry.setVisibility(View.GONE);
        spinner.setVisibility(View.VISIBLE);
        splashTitle.setText(R.string.starting);
        splashText.setGravity(Gravity.CENTER);
        splashText.setText(R.string.starting_note);
        PythonServer.forgetFailure();
        if (serverUrl != null) web.loadUrl(withView(serverUrl, getIntent()));
        else PythonServer.start(this, this);
    }

    private void reveal() {
        pageShown = true;
        web.setVisibility(View.VISIBLE);
        splashScroll.setVisibility(View.GONE);
    }

    // ---------------------------------------------------------------- Python is ready

    @Override
    public void onReady(String url) {
        if (isFinishing() || isDestroyed()) return;
        serverUrl = url;
        web.loadUrl(withView(url, getIntent()));
    }

    @Override
    public void onFailed(String why) {
        if (!isFinishing() && !isDestroyed()) showFailure(why);
    }

    private static String withView(String url, Intent intent) {
        String v = intent == null ? null : intent.getStringExtra(EXTRA_VIEW);
        return (v != null && v.matches("[a-z]{2,20}")) ? url + "&view=" + v : url;
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        String v = intent.getStringExtra(EXTRA_VIEW);
        if (pageShown && v != null && v.matches("[a-z]{2,20}")) {
            web.evaluateJavascript("typeof go === 'function' && go('" + v + "')", null);
        }
    }

    // ---------------------------------------------------------------- the page

    @SuppressLint("SetJavaScriptEnabled")
    private void setUpWeb() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);        // the page keeps its key in localStorage
        s.setAllowFileAccess(false);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setSupportZoom(false);             // laid out for the screen, like any app
        s.setTextZoom(textZoom(getResources().getConfiguration()));
        s.setUserAgentString(s.getUserAgentString() + " WhiskersAndroid/" + BuildConfig.VERSION_NAME);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        web.addJavascriptInterface(new JsBridge(this), "WhiskersAndroid");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (isOurs(request.getUrl())) return false;
                Native.openUrl(request.getUrl().toString());
                return true;
            }

            @Override
            public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                loadFailed = false;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                // A load that failed still "finishes", showing WebView's own error page; the
                // start-up screen with its explanation and Try again stays up instead.
                if (!pageShown && !loadFailed && isOurs(Uri.parse(url))) reveal();
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    loadFailed = true;
                    showFailure(getString(R.string.page_failed) + "\n\n" + error.getDescription());
                }
            }

            @Override
            public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                // The page's renderer was stopped (usually to free memory). The WebView can't
                // be used again, so the window starts afresh; Python carries on regardless.
                Log.w(TAG, "The page's renderer stopped; reopening the window");
                root.removeView(view);
                view.destroy();
                if (view == web) web = null;
                recreate();
                return true;
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                return pickFile(callback);
            }

            @Override
            public boolean onConsoleMessage(ConsoleMessage m) {
                Log.d("WhiskersPage", m.message() + " (" + m.sourceId() + ":" + m.lineNumber() + ")");
                return true;
            }
        });
    }

    /** The page's text follows the phone's own text size setting. */
    private static int textZoom(Configuration c) {
        return Math.round(c.fontScale * 100);
    }

    @Override
    public void onConfigurationChanged(Configuration c) {
        super.onConfigurationChanged(c);
        if (web != null) web.getSettings().setTextZoom(textZoom(c));
    }

    private boolean isOurs(Uri u) {
        if (u == null || serverUrl == null) return false;
        Uri ours = Uri.parse(serverUrl);
        return "http".equals(u.getScheme()) && "127.0.0.1".equals(u.getHost()) && u.getPort() == ours.getPort();
    }

    /** The Freetrade file and the plan file: any file, from wherever the person keeps it. */
    private boolean pickFile(ValueCallback<Uri[]> callback) {
        if (chooser != null) chooser.onReceiveValue(null);
        chooser = callback;
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        try {
            startActivityForResult(i, PICK_FILE);
        } catch (ActivityNotFoundException e) {
            chooser = null;
            callback.onReceiveValue(null);
        }
        return true;
    }

    /**
     * The PC's copy of Whiskers, chosen once in Android's own picker, which can open files
     * in OneDrive or Google Drive. Whiskers keeps permission to read that one file, so the
     * phone can load it again whenever it opens (folio/sync.py).
     */
    void pickSyncFile() {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        try {
            startActivityForResult(i, PICK_SYNC);
        } catch (ActivityNotFoundException e) {
            Log.w(TAG, "No file picker answered", e);
        }
    }

    private void syncFileChosen(Uri u) {
        if (u == null || web == null) return;
        try {
            getContentResolver().takePersistableUriPermission(u, Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch (SecurityException e) {
            Log.w(TAG, "No lasting permission to read " + u, e);
        }
        String name = "";
        try (Cursor c = getContentResolver().query(u, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (c != null && c.moveToFirst() && c.getString(0) != null) name = c.getString(0);
        } catch (Exception e) {
            Log.w(TAG, "The chosen file's name couldn't be read", e);
        }
        web.evaluateJavascript("window.whiskersSyncFilePicked && window.whiskersSyncFilePicked("
                + JSONObject.quote(u.toString()) + ", " + JSONObject.quote(name) + ")", null);
    }

    @Override
    protected void onActivityResult(int request, int result, Intent data) {
        if (request == PICK_SYNC) {
            syncFileChosen(result == RESULT_OK && data != null ? data.getData() : null);
            return;
        }
        if (request == PICK_FILE) {
            if (chooser != null) {
                Uri u = (result == RESULT_OK && data != null) ? data.getData() : null;
                chooser.onReceiveValue(u == null ? null : new Uri[]{u});
                chooser = null;
            }
            return;
        }
        super.onActivityResult(request, result, data);
    }

    /** Back at the front: the page loads the PC's copy if it has changed since (folio/sync.py). */
    @Override
    protected void onResume() {
        super.onResume();
        if (pageShown && web != null) {
            web.evaluateJavascript("window.whiskersResumed && window.whiskersResumed()", null);
        }
    }

    /** Back closes what's open in the page first, then returns to the overview, then leaves. */
    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (!pageShown || web == null) {
            super.onBackPressed();
            return;
        }
        web.evaluateJavascript("(window.whiskersBack && window.whiskersBack()) ? 1 : 0", answer -> {
            // Leaving keeps Whiskers in memory, so coming back is instant.
            if (!"1".equals(answer)) moveTaskToBack(true);
        });
    }

    // ---------------------------------------------------------------- the edges of the screen

    @SuppressWarnings("deprecation")
    private void edgeToEdge() {
        if (Build.VERSION.SDK_INT < 30) return;      // older phones colour their own bars
        Window w = getWindow();
        w.setDecorFitsSystemWindows(false);
        w.setStatusBarColor(Color.TRANSPARENT);
        w.setNavigationBarColor(Color.TRANSPARENT);
        w.setNavigationBarContrastEnforced(false);
        // The page sits between the status bar, the navigation bar and the keyboard; the
        // strips behind them take the page's background colour (applyTheme).
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            Insets bars = insets.getInsets(WindowInsets.Type.systemBars()
                    | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return WindowInsets.CONSUMED;
        });
    }

    /** Called with the page's theme: light or dark strips, and icons that show on them. */
    @SuppressWarnings("deprecation")
    void applyTheme(boolean dark) {
        int ground = dark ? GROUND_DARK : GROUND_LIGHT;
        int ink = dark ? INK_DARK : INK_LIGHT;
        root.setBackgroundColor(ground);
        if (web != null) web.setBackgroundColor(ground);
        splashTitle.setTextColor(ink);
        splashText.setTextColor(ink);
        Window w = getWindow();
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController c = w.getInsetsController();
            if (c != null) {
                int light = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                        | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                c.setSystemBarsAppearance(dark ? 0 : light, light);
            }
        } else {
            w.setStatusBarColor(ground);
            w.setNavigationBarColor(ground);
            View d = w.getDecorView();
            int light = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            int flags = d.getSystemUiVisibility();
            d.setSystemUiVisibility(dark ? (flags & ~light) : (flags | light));
        }
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    @Override
    protected void onDestroy() {
        PythonServer.forget(this);
        if (chooser != null) {
            chooser.onReceiveValue(null);
            chooser = null;
        }
        if (current.get() == this) current = new WeakReference<>(null);
        if (web != null) {
            root.removeView(web);
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }
}
