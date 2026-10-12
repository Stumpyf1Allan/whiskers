// Whiskers for Android. The app itself is the shared Python in ../folio; this project is
// the thin Android shell around it (see README.md in this folder).
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "Whiskers"
include(":app")
