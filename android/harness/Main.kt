// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd desktop system (dev.ytmsd.desktop).
//
// The harness: the commands `android.ps1` and `avd.ps1` run, in one place.
//
// A gate, a voice run, a doctor line, an emulator, an AVD. Each command does its work, prints what it found
// in a fixed voice, and ends with the `RESULT: pass|fail - what ran` line a caller parses.
//
// NOTE ON PROVENANCE: this file was written again on 2026-11-28 after the original `Main.kt` was lost from
// disk with the rest of this folder (it was untracked in git and there was no copy to restore). The command
// surface, the RESULT line and the checks are the same work the original did; the comments here are written
// again, not recovered. A rebuilt harness has earned fewer miles than the one it replaces - watch a gate run
// it reports before trusting a gate result it reports.
package dev.ytmsd.harness

import java.io.File
import java.security.MessageDigest
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.TimeUnit

/** The commands, in the order `help` prints them. */
private val commands = listOf(
    "help" to "this list",
    "doctor [avd]" to "report what is installed and runnable; `doctor avd` checks only the AVD",
    "avd" to "build this project's Android AVD",
    "wire" to "the protocol wire tests",
    "sync" to "the handshake test against the scripted host",
    "desktop" to "the desktop gate fixtures",
    "check" to "every Android unit test",
    "emulator [stop|status]" to "start the emulator, put it down, report it",
    "phone-scratch" to "launch the phone app on the device for a scratch probe",
)

fun main(args: Array<String>) {
    when (args.firstOrNull() ?: "help") {
        "help" -> {
            commands.forEach { (command, note) -> println("$command - $note") }
            println("RESULT: pass - help")
        }
        "doctor" -> doctor(if ("avd" in args) "avd" else null)
        "avd" -> avd()
        "wire" -> wire()
        "sync" -> sync()
        "desktop" -> desktop()
        "check" -> check()
        "emulator" -> emulator(args)
        "phone-scratch" -> phoneScratch()
        else -> {
            println("no such command: ${args.joinToString(" ")}")
            commands.forEach { (command, note) -> println("$command - $note") }
            println("RESULT: fail - no such command")
        }
    }
}

private fun wire() =
    report(
        "protocol wire tests",
        gradle(":protocol:testDebugUnitTest", ":app:testDebugUnitTest", "--tests", "dev.ytmsd.app.*"),
        reportDir("protocol", "testDebugUnitTest"),
        reportDir("app", "testDebugUnitTest"),
    )

private fun sync() =
    report(
        "sync handshake",
        gradle(":protocol:testDebugUnitTest", "--tests", "dev.ytmsd.protocol.SyncHandshakeTest"),
        reportDir("protocol", "testDebugUnitTest"),
    )

private fun check() =
    report("android unit tests", gradle(":app:testDebugUnitTest"), reportDir("app", "testDebugUnitTest"))

/**
 * The voice every test command ends with: what ran, how many tests, and the line a caller parses.
 *
 * `ran == null` means the build itself never ran, which is a failure of its own kind - the tests were not
 * run, so nothing was learned.
 */
private fun report(label: String, ran: Int?, vararg reportDirs: File) {
    if (ran == null) {
        println("$label - the Android build is not runnable")
        println("RESULT: fail - $label")
        return
    }
    val (tests, failures, skipped) = countReports(*reportDirs)
    if (tests == 0) {
        println("$label found no test to run")
        println("RESULT: fail - $label")
        return
    }
    if (failures > 0) {
        println("$label failed - $tests test(s), $failures failure(s)")
        println("RESULT: fail - $label")
        return
    }
    println("$label passed - $tests test(s)${if (skipped > 0) ", $skipped skipped" else ""}")
    println("RESULT: pass - $label")
}

/**
 * The test counts Gradle wrote for these report folders.
 *
 * A folder with no XML in it is read as zero tests, which `report` answers as a failure: a test run that
 * reported nothing is a test run that tested nothing, and it is not a pass.
 */
private fun countReports(vararg dirs: File): Triple<Int, Int, Int> {
    var tests = 0
    var failures = 0
    var skipped = 0
    dirs.forEach { dir ->
        dir.walkTopDown().filter { it.isFile && it.name.endsWith(".xml") }.forEach { file ->
            val text = runCatching { file.readText() }.getOrDefault("")
            tests += intAttr(text, "tests")
            failures += intAttr(text, "failures") + intAttr(text, "errors")
            skipped += intAttr(text, "skipped")
        }
    }
    return Triple(tests, failures, skipped)
}

private fun intAttr(text: String, name: String): Int =
    Regex("""<testsuite[^>]*\b$name="(\d+)"""").find(text)?.groupValues?.get(1)?.toIntOrNull() ?: 0

private fun reportDir(module: String, task: String): File =
    File(File(File(rootDir(), "android"), module), "build/test-results/$task")

// One Gradle run, the shell command, and the desktop gate.

/**
 * Run Gradle over the Android build, answering with its exit code, or `null` when Gradle could not start.
 *
 * `--tests` filters are handed straight to Gradle, so a test class name Gradle does not accept is Gradle's
 * complaint to read, not this harness's guess about it.
 */
private fun gradle(vararg tasks: String): Int? {
    val android = File(rootDir(), "android")
    val gradlew = File(android, if (isWindows()) "gradlew.bat" else "gradlew")
    if (!gradlew.exists()) {
        println("no Gradle wrapper in ${android.absolutePath}")
        return null
    }
    return run(listOf(gradlew.absolutePath) + tasks + listOf("--console=plain", "--no-daemon"), android, 30L)
}

private fun isWindows() = System.getProperty("os.name").lowercase().contains("windows")

/** Run one command, print what it said, and answer with its exit code, or `null` when it could not start. */
private fun run(command: List<String>, workingDir: File, minutes: Long): Int? = run(command, workingDir, minutes, null)

private fun run(
    command: List<String>,
    workingDir: File,
    minutes: Long,
    environment: Map<String, String>?,
): Int? {
    val output = runAndCapture(command, workingDir, minutes, environment) ?: return null
    output.lineSequence().filter { it.isNotBlank() }.forEach { println("  $it") }
    return output.second
}

/** Run one command, and answer with its output and exit code, or `null` when it could not start. */
private fun runAndCapture(
    command: List<String>,
    workingDir: File,
    minutes: Long,
    environment: Map<String, String>? = null,
): Pair<String, Int>? =
    runCatching {
        val builder = ProcessBuilder(command).directory(workingDir).redirectErrorStream(true)
        environment?.forEach { (key, value) -> builder.environment()[key] = value }
        val process = builder.start()
        val text = process.inputStream.readBytes().decodeUtf8()
        if (!process.waitFor(minutes, TimeUnit.MINUTES)) {
            process.destroy()
            println("  ${command.joinToString(" ")} - timed out after $minutes minute(s)")
            return null
        }
        text to process.exitValue()
    }.getOrNull()

private fun sh(vararg command: String): String =
    runCatching {
        val process = ProcessBuilder(command).redirectErrorStream(true).start()
        process.waitFor(3, TimeUnit.MINUTES)
        process.inputStream.readBytes().decodeUtf8()
    }.getOrDefault("")

private fun powershell(command: String): String =
    runCatching {
        val process = ProcessBuilder("powershell", "-NoProfile", "-NonInteractive", "-Command", command)
            .redirectErrorStream(true)
            .start()
        process.waitFor(30, TimeUnit.SECONDS)
        process.inputStream.readBytes().decodeUtf8()
    }.getOrDefault("")

private fun desktop() {
    val root = rootDir()
    val label = "desktop gate"
    if (!File(File(root, "MusicBee Plugin"), "sync_client.py").exists()) {
        println("not a yt-msd desktop source root: $root")
        println("RESULT: fail - $label")
        return
    }
    val checks = checkPythonPlugin(File(root))
    if (checks != null) {
        println("$label passed - ${checks.testCount} test(s)")
        println("RESULT: pass - $label")
        return
    }
    println(pythonCommand() ?: "no python - add the python 3.12 SDK from `winget.ps1 install`")
    println("RESULT: fail - $label")
}

private class PluginCheck(val label: String, val testCount: Int)

/**
 * Run the desktop gate fixtures with this system's own Java plugin.
 *
 * The fixtures are python, the plugin is Java, and a fixture reaches the plugin through the
 * `YTMSD_SYNC_CLIENT_CLASSPATH` environment variable - the desktop's `sync_client.py` reads it and loads the
 * jar in place of the desktop jar, so the harness proves the same plugin the desktop runs.
 *
 * `test_gate_library.py` runs before `test_gate_sync.py` on purpose: it is the fixture that builds the jar
 * from source, so the jar a desktop sync test needs exists before the sync test starts.
 */
private fun checkPythonPlugin(root: File): PluginCheck? {
    val python = pythonCommand() ?: return null
    if (run(listOf(python, "-m", "pytest", "--version"), root, 1L) != 0) {
        return null
    }
    if (run(listOf(python, "-c", "import ffprobe"), root, 1L) != 0) {
        println("  python has no ffprobe - the desktop plays through it, and `pip install ffprobe-gui-support` " +
            "adds it; a gate run without it cannot prove playback")
    }
    val jar = desktopJar(root) ?: return null
    var tests = 0
    for (fixture in listOf("test_gate_library.py", "test_gate_sync.py")) {
        val script = File(root, fixture)
        if (!script.exists()) {
            return null
        }
        val out = runAndCapture(
            listOf(python, "-m", "pytest", fixture, "-q", "--no-header"),
            root,
            15L,
            mapOf("YTMSD_SYNC_CLIENT_CLASSPATH" to jar),
        ) ?: return null
        if (out.second != 0) {
            println("  $fixture - exit ${out.second}")
            out.first.lineSequence().takeLast(12).filter { it.isNotBlank() }.forEach { println("  $it") }
            return null
        }
        tests += passedCount(out.first)
    }
    if (tests == 0) {
        return null
    }
    return PluginCheck("python plugin", tests)
}

/** The `N passed` count from a pytest run's own summary line. */
private fun passedCount(text: String): Int =
    text.lineSequence().mapNotNull { line ->
        Regex("""(\d+) passed""").find(line)?.groupValues?.get(1)?.toIntOrNull()
    }.lastOrNull() ?: 0

