// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.protocol).
//
// The contract before the exchange. Every check in this module reads
// `GUI Test Suite/fixtures/protocol/phone_session.json`, so every one of them is a check against a file that
// can be missing, stale, or recorded by a host that no longer speaks this version. Each of those states is
// said here, in a sentence, before anything tries to pair with a recording.
package dev.ytmsd.protocol

import dev.ytmsd.protocol.testing.PhoneSession
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class FixtureContractTest {

    @Test
    fun `the golden fixture is where the build says it is, and says what version it was recorded from`() {
        val path = PhoneSession.fixturePath()
        val file = File(path)
        assertTrue(
            "no golden fixture at $path - the Android checks compare a phone's frames with the recording the " +
                "desktop suite makes, so run python \"GUI Test Suite\\probe_phone_wire.py\" --record from " +
                "GUI Source Code, read what it wrote, and run this again",
            file.exists(),
        )
        assertTrue("the fixture at $path is empty", file.length() > 0)

        val session = PhoneSession.load()
        assertEquals(
            "the fixture was recorded from a host speaking protocol " + session.protocolVersion +
                " and this copy speaks " + Protocol.VERSION,
            Protocol.VERSION,
            session.protocolVersion,
        )
        assertTrue("the fixture names no chain", session.chain.isNotEmpty())
        assertTrue(
            "the fixture's chain '" + session.chain + "' is not a sync code",
            Protocol.isSyncCode(session.chain),
        )
        assertTrue("the fixture's client address is empty", session.clientIp.isNotEmpty())
        assertTrue("the fixture records no frames", session.frames.isNotEmpty())
    }

    @Test
    fun `the recording opens the way a phone opens, and every frame is the shape this client reads`() {
        val session = PhoneSession.load()
        val first = session.frames.first()
        assertEquals("send", FrameRead.text(first, "dir"))
        val opening = FrameRead.obj(first, "frame")!!
        assertEquals(Protocol.CMD_AUTH, FrameRead.text(opening, "cmd"))
        assertEquals(session.chain, FrameRead.text(opening, "sync_code"))
        assertEquals(session.clientIp, FrameRead.text(opening, "client_ip"))
        assertEquals(
            "the recording names the protocol version under '" + Protocol.VERSION_KEY + "'",
            session.protocolVersion,
            Protocol.requestedProtocolVersion(opening),
        )

        // Every frame a client is recorded sending is a frame this client can name, and every answer is one
        // this client can read a status out of.
        session.sends().forEach { frame ->
            val command = FrameRead.text(frame, "cmd")
            assertTrue("the recording has a client sending '$command'", Protocol.clientCommands.contains(command))
        }
        session.framesOf("recv").forEach { frame ->
            val status = FrameRead.status(frame)
            assertTrue("the recording has an answer with status '$status'", Protocol.hostStatuses.contains(status))
        }
        // The bodies the recording traced. The desktop probe hashes the files it pulls in its own loop
        // (PW17) and not in the re-pull (PW18), so a host can promise more files than the recording has
        // bodies for - and `ScriptedHost` answers a `SENDING` with the file, the way the real host does,
        // whether or not the recording recorded it.
        val promises = session.framesOf("recv").count { FrameRead.status(it) == Protocol.STATUS_SENDING }
        val bodies = session.framesOf("recv_bytes")
        assertTrue("the host promised $promises file(s) and the recording traced $bodies bodies", promises > 0)
        assertTrue(
            "the recording traced ${bodies.size} bodies for $promises `SENDING` answers - a body " +
                "was recorded that no answer promised",
            bodies.size <= promises,
        )
        val promisedNames = session.framesOf("recv").filter { FrameRead.status(it) == Protocol.STATUS_SENDING }
            .map { FrameRead.text(it, "filename") }
        bodies.forEach { frame ->
            assertTrue(
                "the recording traced bytes for '" + FrameRead.text(frame, "filename") +
                    "' which no answer promised",
                promisedNames.contains(FrameRead.text(frame, "filename")),
            )
        }
    }
}
