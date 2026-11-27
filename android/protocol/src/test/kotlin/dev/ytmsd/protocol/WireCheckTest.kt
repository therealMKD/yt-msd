// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.protocol).
//
// The wire itself: the header, the frame, the guard, the checksum, and the comparison the acceptance checks
// are built out of. These are the pieces a phone cannot get wrong and a host cannot forgive.
package dev.ytmsd.protocol

import dev.ytmsd.protocol.testing.FixtureLibrary
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.net.ServerSocket
import java.net.Socket
import java.nio.file.Files
import java.io.File
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class WireCheckTest {

    @Test
    fun `a frame is a four-byte big-endian length and that many bytes of UTF-8 JSON`() {
        val frame = buildJsonObject {
            put("cmd", Protocol.CMD_AUTH)
            put("sync_code", "7301")
            put(Protocol.VERSION_KEY, Protocol.VERSION)
        }
        val buffer = ByteArrayOutputStream()
        Frames.write(buffer, frame)
        val bytes = buffer.toByteArray()
        val payload = frame.toString().toByteArray(Charsets.UTF_8)
        assertEquals(payload.size, Frames.headerLength(bytes.copyOfRange(0, 4)))
        assertEquals(bytes.size, payload.size + 4)
        assertEquals(frame, Frames.read(ByteArrayInputStream(bytes)))
    }

    @Test
    fun `a stream of frames comes back in the order it went, and a closed connection reads as nothing`() {
        val buffer = ByteArrayOutputStream()
        Frames.write(buffer, buildJsonObject { put("cmd", Protocol.CMD_PING) })
        Frames.write(buffer, buildJsonObject { put("status", Protocol.STATUS_PONG) })
        val stream = ByteArrayInputStream(buffer.toByteArray())
        assertEquals(Protocol.CMD_PING, FrameRead.command(Frames.read(stream)))
        assertEquals(Protocol.STATUS_PONG, FrameRead.status(Frames.read(stream)))
        assertNull(Frames.read(stream))
    }

    @Test
    fun `a length that is not a length is refused before any bytes are read`() {
        val lying = Frames.header(0)
        val thrown = runCatching { Frames.read(ByteArrayInputStream(lying)) }.exceptionOrNull()
        assertTrue("expected the guard to fire, got $thrown", thrown is java.io.IOException)

        val giant = Frames.header(Frames.MAX_FRAME_BYTES + 1)
        assertTrue(runCatching { Frames.read(ByteArrayInputStream(giant)) }.exceptionOrNull() is java.io.IOException)

        // A promise of bytes that never arrive is a connection that ended mid-frame, not an empty frame.
        val half = Frames.header(20) + "short".toByteArray()
        assertTrue(runCatching { Frames.read(ByteArrayInputStream(half)) }.exceptionOrNull() is java.io.IOException)
    }

    @Test
    fun `two frames are compared the way Python compares the dicts it parsed`() {
        val pythonSide = PhoneJson.parseToJsonElement(
            """{"files":[{"size":36,"name":"one.mp3","mtime":1700000000.0}],"status":"OK"}"""
        )
        val phoneSide = buildJsonObject {
            put("status", Protocol.STATUS_OK)
            put(
                "files", kotlinx.serialization.json.JsonArray(
                    listOf(
                        buildJsonObject {
                            put("name", "one.mp3")
                            put("size", 36L)
                            put("mtime", 1.7E9)
                        }
                    )
                )
            )
        }
        assertTrue("key order and a JVM's 1.7E9 are not differences", JsonCompat.equal(pythonSide, phoneSide))
        assertFalse(JsonCompat.equal(pythonSide, buildJsonObject { put("status", Protocol.STATUS_OK) }))
        assertFalse(JsonCompat.equal(buildJsonObject { put("size", 1) }, buildJsonObject { put("size", "1") }))
        assertTrue(JsonCompat.equal(buildJsonObject { put("size", 1) }, buildJsonObject { put("size", 1.0) }))
        assertTrue("a missing answer is recorded as an empty frame", JsonCompat.equal(null, null))
    }

    @Test
    fun `the difference between two sessions is named as the frame that differs`() {
        val wanted = listOf(
            buildJsonObject { put("dir", "send"); put("frame", buildJsonObject { put("cmd", Protocol.CMD_AUTH) }) }
        )
        val spoken = listOf(
            buildJsonObject { put("dir", "send"); put("frame", buildJsonObject { put("cmd", Protocol.CMD_PING) }) }
        )
        val difference = JsonCompat.firstDifference(wanted, spoken)
        assertTrue("$difference", difference!!.contains("frame 1"))
        assertTrue(difference.contains("AUTH"))
        assertTrue(difference.contains("PING"))
        assertNull(JsonCompat.firstDifference(wanted, wanted))
    }
}
