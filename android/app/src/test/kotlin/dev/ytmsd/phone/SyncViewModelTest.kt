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

    @Test
    fun `a phone left showing a list keeps its connection warm`() {
        val session = PhoneSession.load()
        val root = Files.createTempDirectory("ytmsd-phone-warm").toFile()
        val library = FixtureLibrary.writeInto(File(root, "host library"))
        val host = ScriptedHost(session, library).also { it.start() }
        val model = SyncViewModel()
        try {
            model.init(Robolectric.buildActivity(MainActivity::class.java).setup().get())
            model.scan(targets = listOf("127.0.0.1"), ports = listOf(host.port))
            assertTrue("the scan found nothing: " + model.status.value, await { model.hosts.value.isNotEmpty() })
            model.pairAndLoad(model.hosts.value.first(), session.chain, session.clientIp)
            assertTrue("pairing left no list: " + model.status.value, await { model.tracks.value.isNotEmpty() })

            // The host reads its next command with a 30-second timeout and hangs up on a client that stopped to
            // read a screen - which is what a phone does every time it lists a library for a person to pick at.
            // The protocol's answer is a PING every 10 seconds, so the phone is left parked here exactly as it
            // is parked in front of a person, and both ends have to be able to say the pings went.
            assertTrue(
                "the phone sent no PING while it sat showing a list: " + model.warmPings(),
                await(millis = 25000) { model.warmPings() > 0 },
            )
            assertTrue(
                "the phone sent pings the host did not answer: " + host.pingsAnswered.get(),
                host.pingsAnswered.get() > 0,
            )
            assertTrue(
                "the host saw frames the recording does not have: " + host.mismatches,
                host.mismatches.isEmpty(),
            )
        } finally {
            model.clear()
            host.stop()
            root.deleteRecursively()
        }
    }

    @Test
    fun `a take from a host that has hung up is said, and said again on the second press`() {
        val session = PhoneSession.load()
        val root = Files.createTempDirectory("ytmsd-phone-hangup").toFile()
        val library = FixtureLibrary.writeInto(File(root, "host library"))
        val host = ScriptedHost(session, library).also { it.start() }
        val model = SyncViewModel()
        try {
            model.init(Robolectric.buildActivity(MainActivity::class.java).setup().get())
            model.scan(targets = listOf("127.0.0.1"), ports = listOf(host.port))
            assertTrue("the scan found nothing: " + model.status.value, await { model.hosts.value.isNotEmpty() })
            model.pairAndLoad(model.hosts.value.first(), session.chain, session.clientIp)
            assertTrue("pairing left no list: " + model.status.value, await { model.tracks.value.isNotEmpty() })

            // Half a minute of reading the list, and the host is gone. The phone cannot see this happen.
            host.hangUp()
            val track = model.tracks.value.first()
            val taking = "Taking ${track.name} ..."

            model.pull(track)
            assertTrue("the first take sat on the window: " + model.status.value,
                await(millis = 25000) { model.status.value != taking })
            assertTrue("the first take did not name the lost connection: " + model.status.value,
                model.status.value.contains("pair with it again", ignoreCase = true))
            assertTrue("the first take left a file behind: " + model.downloaded.value,
                model.downloaded.value.isEmpty())

            // The press a person makes when the first one "did not work". This is where a phone used to say
            // "Taking ..." and mean it forever, because the ask threw and nothing was listening for it.
            model.pull(track)
            assertTrue("the second take sat on the window saying Taking forever: " + model.status.value,
                await(millis = 25000) { model.status.value != taking })
            assertTrue("the second take did not name the lost connection: " + model.status.value,
                model.status.value.contains("pair with it again", ignoreCase = true))
        } finally {
            model.clear()
            host.stop()
            root.deleteRecursively()
        }
    }

    @Test
    fun `a host this app paired with is the host the app starts again with`() {
        val session = PhoneSession.load()
        val root = Files.createTempDirectory("ytmsd-phone-saved").toFile()
        val library = FixtureLibrary.writeInto(File(root, "host library"))
        val context = Robolectric.buildActivity(MainActivity::class.java).setup().get()
        SavedHosts(context).clear()

        val first = ScriptedHost(session, library).also { it.start() }
        val firstLaunch = SyncViewModel()
        var savedPort = 0
        try {
            firstLaunch.init(context)
            assertTrue(
                "a fresh phone started showing hosts it never paired with",
                firstLaunch.saved.value.isEmpty(),
            )

            firstLaunch.scan(targets = listOf("127.0.0.1"), ports = listOf(first.port))
            assertTrue("the scan found nothing: " + firstLaunch.status.value,
                await { firstLaunch.hosts.value.isNotEmpty() })
            firstLaunch.pairAndLoad(firstLaunch.hosts.value.first(), session.chain, session.clientIp)
            assertTrue("pairing left no list: " + firstLaunch.status.value,
                await { firstLaunch.tracks.value.isNotEmpty() })

            // The pair wrote the host down: the address, the port, the code typed, the chain the host called
            // itself, and the version it answered with.
            val records = firstLaunch.saved.value
            assertEquals("a successful pair remembered no host", 1, records.size)
            assertEquals("127.0.0.1", records.first().ip)
            assertEquals(first.port, records.first().port)
            assertEquals(session.chain, records.first().code)
            assertEquals("Phone Test", records.first().chainName)
            assertEquals(1, records.first().protocolVersion)
            savedPort = first.port
        } finally {
            firstLaunch.clear()
            first.stop()
        }

        // The app starts again: a new view model, the same phone. No scan has been run, and the host is
        // already on the list - the desktop's rule being that a chain you have synced with is a chain you
        // have, and not something a machine re-learns every time it wakes up.
        val secondLaunch = SyncViewModel()
        val second = ScriptedHost(session, library, bindPort = savedPort).also { it.start() }
        try {
            secondLaunch.init(context)
            assertEquals("the restarted app remembered no host", 1, secondLaunch.saved.value.size)
            assertEquals(
                "the saved host is on the screen before any scan",
                listOf("127.0.0.1:$savedPort"),
                secondLaunch.hosts.value.map { it.ip + ":" + it.port },
            )
            assertTrue("the saved host must be marked as saved", secondLaunch.hosts.value.first().saved)
            assertTrue(
                "a restarted app must say what it has: " + secondLaunch.status.value,
                secondLaunch.status.value.contains("saved host", ignoreCase = true),
            )

            // Pressing the saved host pairs with it - with the code typed at the time, and nothing typed now.
            // The address named on the AUTH is the one the recording was made from, for the same reason the
            // first pairing names it: two AUTH frames naming two addresses are two different frames.
            secondLaunch.pairSaved(secondLaunch.saved.value.first(), clientIp = session.clientIp)
            assertTrue(
                "the saved host did not answer with its list: " + secondLaunch.status.value,
                await { secondLaunch.tracks.value.isNotEmpty() },
            )
            assertEquals(listOf("one.mp3", "two.mp3"), secondLaunch.tracks.value.map { it.name })

            // And the host is usable, not merely listed: a file takes the way it did on the first start.
            secondLaunch.pull(secondLaunch.tracks.value.first())
            assertTrue(
                "the saved host took no file: " + secondLaunch.status.value,
                await { secondLaunch.downloaded.value.isNotEmpty() },
            )
            assertTrue(secondLaunch.downloadedFile("one.mp3").exists())

            // The pair spoke the frames the recording says a pair speaks, and nothing else: remembering a
            // host may not change what a client says to it.
            second.mismatches.forEach { line -> throw AssertionError("the host saw something else: $line") }

            // A host can be crossed off, and the next start does not show it.
            secondLaunch.forgetNewest()
            assertTrue("forgetting left the host saved", secondLaunch.saved.value.isEmpty())
            assertTrue("forgetting left the host on the list", secondLaunch.hosts.value.isEmpty())
            assertTrue(secondLaunch.status.value.contains("forgotten", ignoreCase = true))
            assertEquals(0, SavedHosts(context).all().size)
        } finally {
            secondLaunch.clear()
            second.stop()
            root.deleteRecursively()
        }
    }

    @Test
    fun `a host named by hand goes on the list, and a bad one is said as a bad one`() {
        val context = Robolectric.buildActivity(MainActivity::class.java).setup().get()
        val model = SyncViewModel()
        try {
            model.init(context)
            model.addHost("192.168.1.20", 63351)
            assertEquals(
                "the hand-added host is not on the list",
                "192.168.1.20:63351",
                model.hosts.value.firstOrNull()?.let { it.ip + ":" + it.port },
            )
            assertTrue(
                "a hand-added host is paired by typing its code: " + model.status.value,
                model.status.value.contains("type the code", ignoreCase = true),
            )

            model.addHost("   ", 63350)
            assertTrue(
                "an empty address has to be said as one: " + model.status.value,
                model.status.value.contains("Type the host's address first", ignoreCase = true),
            )
            model.addHost("192.168.1.20", 70000)
            assertTrue(
                "a port off the end of the dial has to be said as one: " + model.status.value,
                model.status.value.contains("not a port number", ignoreCase = true),
            )

            // An address with no host behind it answers the way an address with no host behind it answers, and
            // says it on the window. A host nobody paired with is not a host to remember.
            model.pairAndLoad(model.hosts.value.first(), "1234", "127.0.0.1")
            assertTrue(
                "a dead address left the window saying nothing: " + model.status.value,
                await(millis = 20000) { model.status.value.contains("could not be reached") },
            )
            assertTrue("a host nobody paired with must not be remembered", model.saved.value.isEmpty())
        } finally {
            model.clear()
        }
    }
}


