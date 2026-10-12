package io.github.stumpyf1allan.whiskers;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * Lets Android's installer read a downloaded update, and nothing else.
 *
 * <p>The update sits in Whiskers' private folder, where the installer can't look, so this
 * hands it over by name: read-only, only .apk files, only from the updates folder, and only
 * to the app the link is granted to. Python downloaded it and checked its SHA-256 against
 * latest-android.json before it ever gets here.
 */
public final class UpdateProvider extends ContentProvider {
    private static final String APK = "application/vnd.android.package-archive";

    static Uri uriFor(Context context, File apk) {
        return new Uri.Builder().scheme("content")
                .authority(context.getPackageName() + ".updates")
                .appendPath(apk.getName())
                .build();
    }

    private File find(Uri uri) throws FileNotFoundException {
        String name = uri.getLastPathSegment();
        if (name == null || name.contains("/") || name.startsWith(".") || !name.endsWith(".apk")) {
            throw new FileNotFoundException("not an update");
        }
        Context c = getContext();
        if (c == null) throw new FileNotFoundException("no context");
        File f = new File(new File(c.getFilesDir(), "whiskers/updates"), name);
        if (!f.isFile()) throw new FileNotFoundException(name);
        return f;
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (mode == null || !mode.equals("r")) throw new SecurityException("updates are read-only");
        return ParcelFileDescriptor.open(find(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public String getType(Uri uri) {
        return APK;
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        File f;
        try {
            f = find(uri);
        } catch (FileNotFoundException e) {
            return null;
        }
        MatrixCursor c = new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE});
        c.addRow(new Object[]{f.getName(), f.length()});
        return c;
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        throw new UnsupportedOperationException("read-only");
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] args) {
        return 0;
    }

    @Override
    public int delete(Uri uri, String selection, String[] args) {
        return 0;
    }
}
