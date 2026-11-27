// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.protocol).
//
// The acceptance check. It runs the exchange a phone will have - pair, list, pull, pull, pull the same file
// again, settings, keepalive - against a host that answers out of
// `GUI Test Suite/fixtures/protocol/phone_session.json`, and compares what this client spoke and heard with
// the recording, frame for frame.
//
// This is the same contract `PW37` in `probe_phone_wire.py` keeps on the Python side. A Kotlin client that
// passes this is a client that speaks the protocol the desktop suite has already agreed to answer.
package dev.ytmsd.protocol

import dev.ytmsd.protocol.testing.FixtureLibrary
import dev.ytmsd.protocol.testing.PhoneSession
import dev.ytmsd.protocol.testing.ScriptedHost
import java.io.File
import java.nio.file.Files
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PhoneSessionTest {

    @Test
    fun `a phone's session is the recorded session, frame for frame`() {
        val session = PhoneSession.load()
        val root = Files.createTempDirectory("ytmsd-phone-session").toFile()
        val library = FixtureLibrary.writeInto(File(root, "host library"))
        val received = File(root, "phone library").apply { mkdirs() }

        val host = ScriptedHost(session, library)
        host.start()
        val trace = FrameTrace()
        try {
            val phone = WireClient("127.0.0.1", host.port, session.chain, session.clientIp, trace).connect()
            try {
                val auth = phone.authenticate()
                assertEquals(Protocol.STATUS_OK, FrameRead.status(auth))
                assertEquals("Phone Test", phone.chainName)
                assertEquals(Protocol.VERSION, phone.hostProtocolVersion)

                val (files, indexError) = phone.index()
                assertEquals(indexError, "")
                assertEquals(listOf("one.mp3", "two.mp3"), files.map { FrameRead.text(it, "name") })

                files.forEach { row ->
                    val name = FrameRead.text(row, "name")
                    val pulled = phone.pull(name, File(received, name))
                    assertTrue("$name: ${pulled.note}", pulled.ok)
                }

                // The recording pulls one.mp3 a second time and the host sends it whole again, from the
                // answer - not from the index that named it. So does this.
                val repeated = phone.pull("one.mp3", File(received, "one - again.mp3"))
                assertTrue(repeated.note, repeated.ok)

                val (configOk, configNote, config) = phone.fetchConfig()
                assertTrue(configNote, configOk)
                assertNotNull(config)
                assertEquals(60, FrameRead.int(config, "volume", -1))

                assertEquals(Protocol.STATUS_PONG, FrameRead.status(phone.ping()))
                assertEquals(Protocol.STATUS_PONG, FrameRead.status(phone.ping()))
            } finally {
                phone.close()
            }

            assertEquals(
                "the scripted host read frames it did not expect:\n" + host.mismatches.joinToString("\n"),
                emptyList<String>(),
                host.mismatches.toList(),
            )

            // The frames, in order, frame for frame. The recording's `recv_bytes` entries are the bodies the
            // desktop probe chose to hash (PW17 hashes the two files it pulls in its loop and PW18 re-pulls
            // one without hashing), while a client reads a body for every file the host sends - so the frames
            // are compared exactly, and the bodies are compared as the recording being inside the trace.
            val recordedFrames = session.frames.filter { FrameRead.text(it, "dir") != "recv_bytes" }
            val spokenFrames = trace.frames().filter { FrameRead.text(it, "dir") != "recv_bytes" }
            val difference = JsonCompat.firstDifference(recordedFrames, spokenFrames)
            assertNull("the session is not the recorded session:\n$difference", difference)

            val recordedBodies = session.framesOf("recv_bytes")
            val spokenBodies = trace.frames().filter { FrameRead.text(it, "dir") == "recv_bytes" }
                .mapNotNull { FrameRead.obj(it, "frame") }
            assertTrue(
                "the trace recorded ${spokenBodies.size} bodies and the recording hashed ${recordedBodies.size}",
                spokenBodies.size >= recordedBodies.size,
            )
            recordedBodies.forEachIndexed { position, wanted ->
                assertTrue(
                    "body " + (position + 1) + " is not the body the recording hashed:\n  recorded " +
                        JsonCompat.describe(wanted) + "\n  arrived      " +
                        JsonCompat.describe(spokenBodies[position]),
                    JsonCompat.equal(wanted, spokenBodies[position]),
                )
            }

            // The files that arrived are the files the recording says arrived, byte for byte.
            val recorded = session.framesOf("recv_bytes")
            val arrived = received.listFiles()!!.filter { it.name.endsWith(".mp3") }
            assertEquals(3, arrived.size.toLong())
            recorded.forEach { frame ->
                val name = FrameRead.text(frame, "filename")
                val promised = FrameRead.text(frame, "sha256")
                val onDisk = File(received, name)
                assertEquals(FrameRead.long(frame, "size", -1L), onDisk.length())
                assertEquals(promised, Transfer.sha256Hex(onDisk))
            }
            assertEquals(
                "the host's own copy of one.mp3 is the bytes the recording hashed",
                recorded.first().let { FrameRead.text(it, "sha256") },
                Transfer.sha256Hex(File(library, "one.mp3")),
            )
        } finally {
            host.stop()
            root.deleteRecursively()
        }
    }

    @Test
    fun `the session the recording describes asks for eleven frames and nothing else`() {
        val session = PhoneSession.load()
        assertEquals(
            "AUTH, GET_INDEX, PULL_FILE x3, GET_CONFIG, PING x2",
            listOf(
                Protocol.CMD_AUTH, Protocol.CMD_GET_INDEX, Protocol.CMD_PULL_FILE, Protocol.CMD_PULL_FILE,
                Protocol.CMD_PULL_FILE, Protocol.CMD_GET_CONFIG, Protocol.CMD_PING, Protocol.CMD_PING,
            ),
            session.sends().map { FrameRead.command(it) },
        )
        assertTrue(Protocol.isSyncCode(session.chain))
        assertEquals(Protocol.VERSION, session.protocolVersion)
    }
}
