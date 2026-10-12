// Versions that are known to work together: Chaquopy 17.0 supports Android Gradle Plugin
// 7.3 to 9.2, and AGP 8.13 needs Gradle 8.13 or later and JDK 17.
plugins {
    id("com.android.application") version "8.13.2" apply false
    id("com.chaquo.python") version "17.0.0" apply false
}
