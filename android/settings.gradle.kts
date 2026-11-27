// yt-msd phone client - the Android app and the Qt-free protocol layer it is built on.
//
// `:protocol` is plain Kotlin/JVM: it is the phone's copy of `yt_msd.sync.wire` and `yt_msd.sync.protocol`,
// and every check in it runs on this desktop with no phone and no emulator. `:app` is the window on top of it.

pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
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

rootProject.name = "yt-msd-phone"
include(":protocol")
include(":app")
