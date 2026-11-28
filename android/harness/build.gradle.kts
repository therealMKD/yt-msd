// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd desktop system (dev.ytmsd.desktop).
//
// The build of the harness that runs the tests a desktop can run.
//
// `java` and not `kotlin-jvm` on purpose: `application` is a `java`-plugin plugin, and the jar task the
// `application` plugin creates is a `java`-plugin task. A `kotlin-jvm` module has no `jar` task of its own
// - it has `jar` as a Kotlin `Libraries` task, and a build script that names `tasks["jar"]` gets the
// Kotlin task, which has no `mainClass` to set.
plugins {
    id("java")
    id("application")
    id("org.jetbrains.kotlin.jvm")
    id("com.diffplug.spotless")
}

repositories {
    mavenCentral()
}

kotlin {
    jvmToolchain(17)
}

sourceSets {
    main {
        java.srcDirs(".")
        // This module's sources are the module folder itself, so the folder Gradle has to keep out of the
        // compile is its own output. Gradle's own build dir is not excluded by default, and Kotlin 2.0
        // writes a `.kotlin` folder - the incremental compile's IC data - beside the sources, and then
        // offers its own build output as a source file, which the compiler answers with a wall of UTF-8
        // decoding errors naming a class file as a source.
        java.exclude("build/**")
        java.exclude(".kotlin/**")
    }
}

application {
    // `mainClass.get()` is Java `ApplicationPlugin`'s property: Kotlin's `mainClass` extension takes no
    // argument on the `java` plugin, so this is the property the `run` task and the manifest read.
    mainClass.set("dev.ytmsd.harness.MainKt")
}

tasks.withType<Jar>().configureEach {
    destinationDirectory = file("out")
}

// The harness is a tool, not a library, and it is not published - a formatting check over its sources is
// the same code style every other module in the system is kept to, and nothing more.
spotless {
    kotlin {
        target("*.kt")
        ktlint()
    }
}
