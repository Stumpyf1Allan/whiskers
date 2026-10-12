# Whiskers for Android

The phone app is Whiskers itself: the same Python as the Windows and Mac versions,
running inside an Android app, with its page shown full-screen. Nothing here is a second
copy of the app. This folder is only the shell around it.

## How it fits together

- **Python on the phone.** [Chaquopy](https://chaquo.com/chaquopy/) puts Python 3.13 in
  the app. At build time `folio/` is copied in (`app/build.gradle.kts`), so the phone runs
  exactly the code in this repository.
- **Starting up.** `MainActivity` shows a start-up screen while `PythonServer` runs
  `app/src/main/python/whiskers_android.py` on a background thread. That points Whiskers
  at the app's private folder, plugs the phone's abilities into `folio/android.py`, and
  starts the same local server the PC uses, on 127.0.0.1:8766.
- **The page.** A WebView opens that address with the app's key after the `#`. The server
  answers only requests carrying the key (`config.phone_key()`), so other apps on the
  phone can't read the portfolio through the loopback address.
- **What the phone does for Python** (`Native.java`):
  - *Prices from Yahoo* go through Android 14's built-in copy of Chrome's network engine
    (`ChromiumNet.java`), the phone's equivalent of curl_cffi on the PC.
  - *Links* open in the phone's browser or mail app.
  - *Updates*: the app reads `latest-android.json` from the `android` pre-release,
    downloads the APK, checks its SHA-256, then hands it to Android's installer
    (`UpdateProvider.java`).
- **What the phone does for the page** (`JsBridge.java`): saves exports to Downloads, and
  colours the strips above and below the page to match its theme. File imports use the
  system file picker.
- **Data** stays in the app's private storage and is left out of Android's cloud backup,
  because the encrypted Trading 212 key and the key that decrypts it live side by side.

## Building

GitHub builds it: `.github/workflows/android.yml`. It runs the tests, builds an x86_64
debug copy and drives it on an Android 14 emulator (`ci/emulator-check.sh`), builds the
arm64 release copy, and on `main` publishes it to the `android` pre-release with
`latest-android.json` (`ci/manifest.py`).

Every build is signed with the same key, from the `ANDROID_SIGNING_KEY` secret (a base64
PKCS#12 keystore, alias `whiskers`). Android only installs an update signed with the key
the app was first installed with, so the workflow refuses to publish anything else. The
certificate's fingerprint is pinned in the workflow.

The launcher icon is drawn by `make_icons.py` from the same geometry as every other
Whiskers icon (`tools/make_icons.py`).

To build on a computer with Android Studio's SDK and Python 3.13 on the PATH:

    cd android
    gradle assembleDebug -PwhiskersAbis=arm64-v8a
