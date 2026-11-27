import org.gradle.api.tasks.testing.logging.TestExceptionFormat
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

// The phone's protocol layer. Plain Kotlin/JVM on purpose: it compiles for a phone and it runs its own
// checks on this desktop, with no emulator, because the host it talks to is the yt-msd on this machine.
plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.serialization)
    `java-test-fixtures`
}

group = "dev.ytmsd"
version = "0.1.0"

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

dependencies {
    implementation(libs.kotlinx.serialization.json)
    testImplementation(libs.junit)
    testFixturesImplementation(libs.kotlinx.serialization.json)
    testFixturesImplementation(libs.junit)
}

// The acceptance contract is the recording the desktop suite already keeps. Its path is a property so a
// machine that keeps the suite elsewhere can point at it without editing a build file.
val phoneSessionFixture: String =
    (findProperty("ytmsd.fixture") as String?)
        ?: rootProject.projectDir.parentFile
            .resolve("GUI Source Code/GUI Test Suite/fixtures/protocol/phone_session.json")
            .absolutePath

tasks.withType<Test>().configureEach {
    useJUnit()
    systemProperty("ytmsd.fixture", phoneSessionFixture)
    systemProperty("ytmsd.chain", findProperty("ytmsd.chain")?.toString() ?: "7301")
    // A live-host run names the yt-msd host the desktop suite started. Name nothing and the live checks
    // skip themselves, which is what keeps a plain `gradlew test` runnable with no host and no phone.
    systemProperty("ytmsd.host", findProperty("ytmsd.host")?.toString() ?: "")
    systemProperty("ytmsd.port", findProperty("ytmsd.port")?.toString() ?: "")
    testLogging {
        events("passed", "failed", "skipped")
        exceptionFormat = TestExceptionFormat.FULL
        showStandardStreams = true
    }
}

description = "The sync protocol as a phone speaks it: framing, commands, a client, and the checks that " +
    "compare them with GUI Test Suite/fixtures/protocol/phone_session.json"
