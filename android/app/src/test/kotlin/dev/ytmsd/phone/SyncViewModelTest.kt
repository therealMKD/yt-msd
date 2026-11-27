// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.phone).
//
// The window's logic, away from the window. These are Robolectric checks - they run on this machine, with
// the real Android framework classes, and they drive the same view-model the phone drives. The host is a
// ScriptedHost on a local port that answers out of the recorded Python session, so the scan, the pair, the
// list and the pull all happen with no phone, no emulator, and no PC hosting a chain.
package dev.ytmsd.phone

import dev.ytmsd.protocol.testing.FixtureLibrary
import dev.ytmsd.protocol.testing.PhoneSession
import dev.ytmsd.protocol.testing.ScriptedHost
import java.io.File
import java.nio.file.Files
import java.security.MessageDigest
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class SyncViewModelTest {

    /** Wait for a view-model to say what it is going to say - it works on a thread of its own. */
    private fun await(millis: Long = 30000, condition: () -> Boolean): Boolean {
        val until = System.currentTimeMillis() + millis
        while (System.currentTimeMillis() < until) {
            if (condition()) return true
            Thread.sleep(100)
        }
        return condition()
    }

    private fun sha256Of(file: File): String =
        MessageDigest.getInstance("SHA-256").digest(file.readBytes()).joinToString("") { "%02x".format(it) }

    @Test
    fun `scan finds a host, pairing reads its list, and a pull lands a file the player can open`() {
        val session = PhoneSession.load()
        val root = Files.createTempDirectory("ytmsd-phone-app").toFile()
        val library = FixtureLibrary.writeInto(File(root, "host library"))
        val host = ScriptedHost(session, library).also { it.start() }
        val model = SyncViewModel()
        try {
            model.init(Robolectric.buildActivity(MainActivity::class.java).setup().get())

            // The scan is bounded to the one address the scripted host stands on: the same call the phone
            // makes against its own subnet, only shorter. The recording has no `HELLO` in it - the scripted
            // host answers a `HELLO` with the `AUTH` answer it recorded, which is enough for a phone to put
            // a host on the screen, and that is the one frame the recording does not cover.
            model.scan(targets = listOf("127.0.0.1"), ports = listOf(host.port))
            assertTrue("the scan found nothing: " + model.status.value, await { model.hosts.value.isNotEmpty() })
            val card = model.hosts.value.first()
            assertEquals("127.0.0.1", card.ip)
            assertEquals(host.port, card.port)
            assertEquals(listOf("Phone Test"), card.chains)
            assertEquals(1, card.protocolVersion)
            val framesTheRecordingDoesNotCover = host.mismatches.size

            // Pairing, then the list. The scripted host walks the recording, so every frame the phone speaks
            // is compared with the frame the Python host recorded. Nothing new may appear in `mismatches`.
            model.pairAndLoad(card, session.chain, session.clientIp)
            assertTrue("pairing left no list: " + model.status.value, await { model.tracks.value.isNotEmpty() })
            assertEquals(listOf("one.mp3", "two.mp3"), model.tracks.value.map { it.name })
            assertEquals(listOf(36L, 43L), model.tracks.value.map { it.size })
            assertEquals(2, model.tracks.value.map { it.sha256 }.distinct().size)

            // A pull lands the file in the app's own folder, byte for byte, hashing to what the host promised.
            model.pull(model.tracks.value.first())
            assertTrue("the pull left nothing behind: " + model.status.value,
                await { model.downloaded.value.isNotEmpty() })
            val onPhone = model.downloadedFile("one.mp3")
            assertTrue(onPhone.exists())
            assertEquals(FixtureLibrary.bodies.getValue("one.mp3"), onPhone.readText(Charsets.UTF_8))
            val promised = session.framesOf("recv").mapNotNull { frame ->
                (frame["sha256"] as? JsonPrimitive)?.content
            }.first()
            assertEquals(promised, sha256Of(onPhone))

            host.mismatches.forEach { line -> throw AssertionError("the host saw something else: $line") }
            assertEquals(
                "the scan is the only frame the recording does not cover",
                framesTheRecordingDoesNotCover,
                host.mismatches.size,
            )
        } finally {
            model.clear()
            host.stop()
            root.deleteRecursively()
        }
    }
}
