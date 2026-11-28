// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd desktop system (dev.ytmsd.desktop).
//
// The Android emulator, as the harness knows it.
//
// Testing the phone app needs a phone, and a phone is an emulator, and an emulator is a machine with a life of
// its own: it is asked to boot, its boot is a log to read, it is asked to stop, and it refuses - because the
// AVD has an emulator process attached to it that a harness cannot kill. That is all in one place here, so the
// commands that use it - `emulator`, `emulator stop`, `emulator status`, and the gates that need a phone - ask
// one question and get an answer.
//
// The AVD and its system image are this project's own, built by `avd.ps1`; the emulator answers only to that
// name, so the harness cannot reach a device belonging to something else.
// NOTE ON PROVENANCE: this file was written on 2026-11-28. The harness folder it belongs to was lost from
// disk that day - untracked in git, with no copy to restore - so what is here is written again from the work
// the original did, not recovered. It has not been compiled. A rebuilt harness has earned fewer miles than
// the one it replaces: watch a run it reports before trusting a result it reports.

package dev.ytmsd.harness

import java.io.File
import java.util.concurrent.TimeUnit

/** Where to find an emulator, and what to do with it. */
class EmulatorConfig(
    val sdkRoot: String? = System.getenv("ANDROID_HOME") ?: System.getenv("ANDROID_SDK_ROOT"),
    val avd: String = avdName(),
    val headless: Boolean = System.getenv("YTMSD_EMULATOR_HEADLESS")?.toBoolean() ?: true,
    val logDir: String = File(File(rootDir(), "build"), "emulator").absolutePath,
    val recordFile: File = File(File(rootDir(), "build"), "emulator.json"),
    val timeoutMinutes: Int = System.getenv("YTMSD_EMULATOR_BOOT_MINUTES")?.toIntOrNull() ?: 10,
)

/**
 * The state of one AVD, read from the harness record the phone build wrote when it launched the emulator.
 *
 * `use` of this stops the emulator when the block ends, which is what a gate that started an emulator owes it.
 */
class EmulatorState(
    private val record: JsonObject?,
    private val config: EmulatorConfig = EmulatorConfig(),
) : AutoCloseable {

    private val avd = config.avd

    /** Bring the emulator up, waiting for a device to appear on `adb`. */
    fun start(): JsonObject {
        val already = if (emulatorAlive()) {
            mapOf("state" to "already running", "note" to "a device is attached on adb")
        } else {
            val launched = launch()
            val deadline = System.currentTimeMillis() + config.timeoutMinutes * 60_000L
            var state = "not started"
            var device = ""
            while (System.currentTimeMillis() < deadline) {
                Thread.sleep(5000)
                device = sh(sdkBin("adb"), "devices").lines()
                    .filter { "\tdevice" in it }
                    .joinToString(", ") { it.substringBefore("\tdevice").trim() }
                    .ifBlank { "none" }
                if (device != "none") {
                    state = "ready"
                    break
                }
            }
            mapOf(
                "state" to state,
                "device" to device,
                "process" to (emulatorPid() ?: "not recorded"),
                "log" to launched.logFile.absolutePath,
            )
        }
        println(
            "emulator '${config.avd}' ${already["state"]}" +
                (already["device"]?.let { " - $it" } ?: ""),
        )
        println("  (a first emulator boot pulls the images and cold boots, which is slow; the next ones fast boot)")
        note()
        return JsonObject(already)
    }

    /** Put the emulator down. */
    fun stop(): JsonObject {
        val process = emulatorPid()
        val killed = process?.let { killEmulatorProcesses(it) } ?: 0
        val state = if (emulatorAlive()) {
            "still running"
        } else {
            if (record != null && config.recordFile.exists()) {
                config.recordFile.delete()
            }
            "stopped"
        }
        println("emulator '${config.avd}' $state" + if (killed > 0) " ($killed process(es) killed)" else "")
        note()
        return JsonObject(mapOf("state" to state, "killed" to killed.toString(), "pid" to (process ?: "none")))
    }

    /** Report the emulator's state. */
    fun status(): JsonObject = JsonObject(
        mapOf(
            "avd" to config.avd,
            "headless" to config.headless.toString(),
            "record" to config.recordFile.absolutePath,
            "recorded" to (record != null).toString(),
            "recordedPid" to (record?.string("pid") ?: "none"),
            "process" to (emulatorPid() ?: "not running"),
            "devices" to sh(sdkBin("adb"), "devices").lines()
                .filter { "\tdevice" in it }
                .joinToString(", ") { it.substringBefore("\tdevice").trim() }
                .ifBlank { "none" },
        ),
    )

    /** The line a harness run leaves in the doctor, about the machine it used. */
    fun note() {
        val pid = emulatorPid()
        println(
            "  emulator ${config.avd}: ${if (pid == null) "not running" else "running (pid $pid)"}" +
                " - ${config.recordFile.absolutePath}",
        )
    }

    override fun close() {
        stop()
    }
