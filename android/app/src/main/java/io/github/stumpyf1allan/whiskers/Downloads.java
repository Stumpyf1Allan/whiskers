package io.github.stumpyf1allan.whiskers;

import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;

/** Saves a file into the phone's Downloads folder, where Files, Drive and Excel can see it. */
final class Downloads {
    private Downloads() {
    }

    /** Returns the sentence the page shows: where the file went, under which name. */
    static String save(Context context, String name, String mime, byte[] data) throws IOException {
        String safe = name == null ? "" : name.replaceAll("[\\\\/:*?\"<>|\\p{Cntrl}]", "_").trim();
        if (safe.isEmpty()) safe = "Whiskers file";
        if (mime == null || mime.isEmpty()) mime = "application/octet-stream";

        if (Build.VERSION.SDK_INT >= 29) {
            ContentResolver r = context.getContentResolver();
            ContentValues v = new ContentValues();
            v.put(MediaStore.MediaColumns.DISPLAY_NAME, safe);
            v.put(MediaStore.MediaColumns.MIME_TYPE, mime);
            v.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);
            v.put(MediaStore.MediaColumns.IS_PENDING, 1);
            Uri uri = r.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
            if (uri == null) throw new IOException("Android wouldn't create the file");
            try (OutputStream out = r.openOutputStream(uri)) {
                if (out == null) throw new IOException("Android wouldn't open the file");
                out.write(data);
            } catch (IOException e) {
                r.delete(uri, null, null);
                throw e;
            }
            v.clear();
            v.put(MediaStore.MediaColumns.IS_PENDING, 0);
            r.update(uri, v, null, null);
            // Android adds " (1)" when a file of that name is already there; say what it used.
            String shown = safe;
            try (Cursor c = r.query(uri, new String[]{MediaStore.MediaColumns.DISPLAY_NAME}, null, null, null)) {
                if (c != null && c.moveToFirst() && c.getString(0) != null) shown = c.getString(0);
            }
            return "Saved to Downloads as " + shown + ".";
        }

        // Android 8 and 9: the app's own Downloads folder needs no permission.
        File dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
        if (dir == null) throw new IOException("the phone's storage isn't available");
        if (!dir.isDirectory() && !dir.mkdirs()) throw new IOException("couldn't make " + dir);
        File f = new File(dir, safe);
        try (OutputStream out = new FileOutputStream(f)) {
            out.write(data);
        }
        return "Saved as " + f.getAbsolutePath() + ".";
    }
}
