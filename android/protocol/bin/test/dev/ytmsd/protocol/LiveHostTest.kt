// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.protocol).
//
// The same session, against a host that is not a recording. Name a host on the command line -
//
//   gradlew :protocol:test --tests dev.ytmsd.protocol.LiveHostTest -Pytmsd.host=192.168.1.20 -Pytmsd.port=63350 -Pytmsd.chain=7301
//
// - and this runs the phone's opening moves against the yt-msd on this machine, the way a phone runs them.
// Name nothing and the checks skip themselves, which is what keeps a plain `gradlew test` runnable with no
// host running. The golden fixture stays the contract; a live host is what proves the fixture is a real
// exchange and not a story about one.
package dev.ytmsd.protocol

import java.io.File
import java.nio.file.Files
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

class LiveHostTest {

    private val host: String = System.getProperty("ytmsd.host", "")
    private val port: Int = System.getProperty("ytmsd.port", "").toIntOrNull() ?: Protocol.SYNC_PORT_START
    private val chain: String = System.getProperty("ytmsd.chain", "")

    @Test
    fun `a phone pairs with a host that is running, reads its list, and takes a file from it`() {
        assumeTrue("no host named - run with -Pytmsd.host=<ip> -Pytmsd.port=<port> -Pytmsd.chain=<code>",
            host.isNotEmpty())
        assumeTrue("no sync code named - run with -Pytmsd.chain=<code>", chain.isNotEmpty())

        val trace = FrameTrace()
        val phone = WireClient(host, port, chain, clientIp = Lan.localIp(), trace = trace)
        val folder = Files.createTempDirectory("ytmsd-live-host").toFile()
        try {
            phone.connect()
            val answer = phone.authenticate()
            val status = FrameRead.status(answer)
            assertTrue("the host at $host:$port answered ${JsonCompat.describe(answer)}",
                status == Protocol.STATUS_OK)
            val refusal = Protocol.versionRefusalFor(answer)
            assertTrue("the host at $host:$port refused the protocol version: $refusal", refusal == null)
            assertEquals(chain, FrameRead.text(answer, "chain_name").ifEmpty { chain })

            val (files, indexError) = phone.index()
            assertTrue("the host's list did not arrive: $indexError", indexError.isEmpty())

            if (files.isNotEmpty()) {
                val name = FrameRead.text(files.first(), "name")
                val size = FrameRead.long(files.first(), "size", 0L)
                val promised = FrameRead.text(files.first(), "sha256")
                val result = phone.pull(name, File(folder, name))
                assertTrue("the host refused '$name': ${result.note}", result.ok)
                assertEquals(size, File(folder, name).length())
                assertEquals(Transfer.sha256Hex(File(folder, name)), promised)
            }

            // A keepalive keeps a long-lived exchange warm, and says so in the trace.
            val pong = phone.keepalive(block = { phone.ping() })
            assertEquals(Protocol.STATUS_PONG, FrameRead.status(pong))
            assertTrue("no frame was traced", trace.size() > 0)
        } finally {
            phone.close()
            folder.deleteRecursively()
        }
    }

    @Test
    fun `a host that is not there is said to be not there`() {
        assumeTrue("no host named - run with -Pytmsd.host=<ip>", host.isNotEmpty())
        // Port 1 is a port nothing on a network is hosting, and a phone's answer to it is a sentence, not a
        // stack trace - the sentence the window shows.
        val phone = WireClient(host, 1, chain, clientIp = Lan.localIp())
        val problem = runCatching { phone.connect() }.exceptionOrNull()
        assertTrue("a closed port produced no complaint", problem != null)
        phone.close()
    }
}
