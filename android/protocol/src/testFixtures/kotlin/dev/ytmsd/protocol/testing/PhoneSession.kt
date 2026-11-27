// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.protocol, test fixtures).
//
// `PhoneSession` reads the recording the desktop suite keeps in
// `GUI Test Suite/fixtures/protocol/phone_session.json`, and `FixtureLibrary` rebuilds the two files that
// recording was made from, byte for byte. Together with `ScriptedHost` these are how a phone's exchange is
// proved on a desktop with no phone in the house.
package dev.ytmsd.protocol.testing

import dev.ytmsd.protocol.FrameRead
import dev.ytmsd.protocol.PhoneJson
import dev.ytmsd.protocol.Protocol
import java.io.File
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject

/** The recorded session, read off the golden fixture. */
class PhoneSession(val root: JsonObject) {

    val frames: List<JsonObject> = FrameRead.array(root, "frames").map { it as JsonObject }
    val chain: String = FrameRead.text(root, "chain")
    val clientIp: String = FrameRead.text(root, "client_ip")
    val protocolVersion: Int = FrameRead.int(root, "protocol_version", Protocol.VERSION)

    /** The frames the recording says a client sends, in the order it sends them. */
    fun sends(): List<JsonObject> = framesOf("send")

    /** Every frame in the recording, with its `dir` marker - the shape the acceptance check compares. */
    fun framesOf(direction: String): List<JsonObject> =
        frames.filter { FrameRead.text(it, "dir") == direction }.mapNotNull { FrameRead.obj(it, "frame") }

    companion object {

        /** Where the recording lives. `protocol/build.gradle.kts` points at the suite; a machine that keeps
         *  the suite elsewhere overrides it with `-Pytmsd.fixture=<path>`. */
        fun fixturePath(): String =
            System.getProperty("ytmsd.fixture")
                ?: error("no fixture path - run these tests through Gradle, which supplies ytmsd.fixture")

        fun load(): PhoneSession {
            val file = File(fixturePath())
            require(file.exists()) {
                "the golden fixture is not at ${file.path} - run the desktop suite's " +
                    "probe_phone_wire.py --record, then run this again"
            }
            return PhoneSession(PhoneJson.parseToJsonElement(file.readText()) as JsonObject)
        }

        /** The Python module this Kotlin copy mirrors, when this checkout has it. */
        fun pythonProtocolSource(): File? {
            val fixture = File(fixturePath())
            // fixtures/protocol -> GUI Test Suite -> GUI Source Code -> yt_msd/sync/protocol.py
            val suite = fixture.parentFile?.parentFile?.parentFile ?: return null
            val candidate = File(File(suite.parentFile, "yt_msd"), "sync/protocol.py")
            return if (candidate.exists()) candidate else null
        }
    }
}

/**
 * The fixture's library, rebuilt on this machine.
 *
 * These are the recording's own bytes: `probe_phone_wire.py` writes these two files with these contents and
 * these timestamps, which is why a recorded index entry's size and checksum are the same on every machine,
 * and why the golden fixture is a recording of a real exchange rather than a template of one.
 */
object FixtureLibrary {

    const val FIXED_MTIME_SECONDS = 1_700_000_000.0

    val bodies: Map<String, String> = linkedMapOf(
        "one.mp3" to "the first track a phone will ask for",
        "two.mp3" to "the second track, longer than the first one",
    )

    fun writeInto(folder: File): File {
        folder.mkdirs()
        bodies.forEach { (name, body) ->
            val path = File(folder, name)
            path.writeBytes(body.toByteArray(Charsets.UTF_8))
            path.setLastModified((FIXED_MTIME_SECONDS * 1000).toLong())
        }
        return folder
    }
}
