// The phone's window. It is thin by design: everything it says to a PC is in `:protocol`, and the checks
// that prove the exchange are run there. What is proved here is that the window drives it.
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.serialization)
}

// The acceptance contract is the recording the desktop suite already keeps. Its path is a property so a
// machine that keeps the suite elsewhere can point at it without editing a build file.
val phoneSessionFixture: String =
    (findProperty("ytmsd.fixture") as String?)
        ?: rootProject.projectDir.parentFile
            .resolve("GUI Source Code/GUI Test Suite/fixtures/protocol/phone_session.json")
            .absolutePath

android {
    namespace = "dev.ytmsd.phone"
    // API 36, with build-tools 36.0.0 installed: the API level this toolchain compiles end to end - AGP 8.13
    // compiles it, and Robolectric 4.15.1, which runs the app's own checks on this desktop's JVM, ships an
    // Android 16 (`sdk 36`) image, which is what a `compileSdk = 36` unit check needs to exist in.
    compileSdk = 36

    defaultConfig {
        applicationId = "dev.ytmsd.phone"
        // The lowest Android this app is written for. 26 is where the Java time and file APIs the protocol
        // layer uses exist on a phone, so no compatibility shim is needed between the two copies of it.
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    lint {
        // Media3 marks its player plumbing - `Renderer`, `DefaultRenderersFactory`, `DefaultAudioSink` and
        // the rest - `@UnstableApi`, and this app opts in to it with Kotlin's `@OptIn(UnstableApi::class)` on
        // the two classes that touch that plumbing. The Kotlin compiler accepts that, and the build compiles;
        // AGP's lint does not read a `@RequiresOptIn` marker defined in Java when it is opted in from Kotlin,
        // and reports every use of an opted-in declaration as unopted-in - one error per call, over the whole
        // file. This turns that one check off. It is not a way of ignoring a real problem: lint's own advice
        // in the message is `@OptIn(markerClass = UnstableApi.class)`, which is what the code already says.
        disable += "UnsafeOptInUsageError"
    }



    testOptions {
        unitTests {
            // Robolectric needs the app's own resources, and it runs the app's classes on this desktop's
            // JVM - no emulator, no phone.
            isIncludeAndroidResources = true
            // The recorded Python session and the chain it names, in the system properties the `:protocol`
            // test fixtures read them from - the same acceptance contract, on the phone's own side.
            all { test ->
                test.systemProperty("ytmsd.fixture", phoneSessionFixture)
                test.systemProperty("ytmsd.chain", findProperty("ytmsd.chain")?.toString() ?: "7301")
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(project(":protocol"))
    implementation(libs.kotlinx.serialization.json)
    // The view model asks for an index, a file, and a scan, all off the main thread.
    implementation(libs.kotlinx.coroutines.core)

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity)
    implementation(libs.androidx.activity.ktx)
    implementation(libs.androidx.lifecycle.viewmodel)
    implementation(libs.androidx.lifecycle.viewmodel.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)

    implementation(libs.media3.exoplayer)
    implementation(libs.media3.common)
    implementation(libs.media3.ui)

    testImplementation(libs.junit)
    testImplementation(libs.robolectric)
    testImplementation(libs.androidx.test.core)
    testImplementation(libs.kotlinx.coroutines.core)
    // The recorded Python session, the scripted host and the fixture files, from `:protocol`.
    testImplementation(testFixtures(project(":protocol")))
}

description = "The yt-msd phone client: scan, pair, list, pull, play - on top of :protocol"
