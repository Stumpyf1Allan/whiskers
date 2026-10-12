plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

// ---------------------------------------------------------------- one source of truth
// The version and the Python come from the rest of the repository, so the phone runs
// exactly the code the PC and the Mac run. folio/config.py holds the version; each phone
// build adds its own number (GitHub's run number), so a rebuild of the same version
// still counts as an update, and Android's version code only ever goes up.
val repoRoot: File = rootProject.projectDir.parentFile
val appVersion: String = Regex("""APP_VERSION\s*=\s*"([^"]+)"""")
    .find(File(repoRoot, "folio/config.py").readText())?.groupValues?.get(1)
    ?: error("APP_VERSION wasn't found in folio/config.py")
val buildNumber: Int = (System.getenv("WHISKERS_BUILD_NUMBER") ?: System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()
// arm64-v8a for phones; the emulator check builds x86_64 instead.
val abis: List<String> = ((findProperty("whiskersAbis") as String?) ?: "arm64-v8a")
    .split(",").map { it.trim() }.filter { it.isNotEmpty() }

// The folio package, copied in fresh on every build (never edited here).
val pythonStage: File = layout.buildDirectory.dir("whiskers-python").get().asFile
project.sync {
    from(File(repoRoot, "folio")) {
        exclude("**/__pycache__/**", "**/*.pyc", "resources/*.ico", "resources/*.icns")
    }
    into(File(pythonStage, "folio"))
}

// The signing key arrives from the ANDROID_SIGNING_KEY secret (see the Android workflow).
// Without it, a release build is signed with the throwaway debug key, and the workflow
// refuses to publish that.
val keystore: String? = System.getenv("WHISKERS_KEYSTORE")?.takeIf { File(it).isFile }

android {
    namespace = "io.github.stumpyf1allan.whiskers"
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.stumpyf1allan.whiskers"
        minSdk = 26
        targetSdk = 35
        versionCode = buildNumber
        versionName = "$appVersion.$buildNumber"
        ndk {
            abiFilters += abis
        }
    }

    signingConfigs {
        create("whiskers") {
            if (keystore != null) {
                storeFile = File(keystore)
                storeType = "pkcs12"
                storePassword = "whiskers-android"
                keyAlias = "whiskers"
                keyPassword = "whiskers-android"
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName(if (keystore != null) "whiskers" else "debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
    }

    lint {
        checkReleaseBuilds = false
    }
}

chaquopy {
    defaultConfig {
        version = "3.13"
        pip {
            // requirements.txt, less what has no place on a phone: pywebview (the PC's
            // window), keyring (the PC's credential store) and curl_cffi (the phone's own
            // network engine does that job; see folio/android.py).
            install("openpyxl==3.1.5")
            install("cryptography==42.0.8")
        }
        // The server finds its page next to its own code (folio/web/static), so the
        // package is unpacked onto the phone's storage rather than read from inside the app.
        extractPackages("folio")
    }
    sourceSets {
        getByName("main") {
            srcDir(pythonStage)
        }
    }
}
