// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.phone).
//
// The phone's memory of the hosts it has synced with. What is checked here is the one thing a person notices
// about it: the app was closed, the app is opened again, and the host is still there. That has to be checked
// against the store the phone keeps, on a phone-shaped runtime, and not against a list in a window.
package dev.ytmsd.phone

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class SavedHostsTest {

    /** The app's own store, as the next start of the app opens it. */
    private fun store(): SavedHosts = SavedHosts(ApplicationProvider.getApplicationContext())

    private fun host(ip: String, port: Int, code: String, chain: String, seen: Long) =
        SavedHost(ip, port, code, chain, 1, seen)

    @Test
    fun `a host written in one start of the app is there in the next`() {
        store().clear()
        assertTrue(store().all().isEmpty())

        store().remember(host("10.0.2.2", 63350, "6767", "(G)i-dle - HWAA", 1_700_000_000_000L))

        val reopened = SavedHosts(ApplicationProvider.getApplicationContext())
        assertEquals("the store was empty on the next start", 1, reopened.all().size)
        val record = reopened.all().first()
        assertEquals("10.0.2.2", record.ip)
        assertEquals(63350, record.port)
        assertEquals("a pair needs the code it paired with, written down", "6767", record.code)
        assertEquals("(G)i-dle - HWAA", record.chainName)
        assertEquals(1, record.protocolVersion)
        assertEquals(1_700_000_000_000L, record.lastSeen)
        store().clear()
    }

    @Test
    fun `the same address is updated rather than doubled, and the newest pairing is first`() {
        store().clear()
        store().remember(host("192.168.1.20", 63350, "1234", "Kitchen", 10L))
        store().remember(host("192.168.1.31", 63351, "5678", "Study", 20L))
        assertEquals(listOf("192.168.1.31", "192.168.1.20"), store().all().map { it.ip })

        // The same address paired with again: a new record, in the first place, and not a second row.
        store().remember(host("192.168.1.20", 63350, "1235", "Kitchen Renamed", 30L))
        assertEquals("a host paired with twice is one host", 2, store().all().size)
        assertEquals("192.168.1.20", store().all().first().ip)
        assertEquals("1235", store().all().first().code)
        assertEquals("Kitchen Renamed", store().all().first().chainName)
        store().clear()
    }

    @Test
    fun `a phone remembers only the hosts it can show - and the newest ones`() {
        store().clear()
        repeat(SavedHosts.MAX_HOSTS + 4) { index ->
            store().remember(host("10.0.0.${index + 1}", 63350, "1000", "Chain $index", index.toLong()))
        }
        val records = store().all()
        assertEquals(SavedHosts.MAX_HOSTS, records.size)
        assertEquals("10.0.0.${SavedHosts.MAX_HOSTS + 4}", records.first().ip)
        store().clear()
    }

    @Test
    fun `a forgotten host stays forgotten through the next start`() {
        store().clear()
        store().remember(host("172.20.10.4", 63350, "4321", "Hotspot PC", 10L))
        store().remember(host("172.20.10.9", 63350, "8765", "Hotspot Laptop", 20L))
        store().forget("172.20.10.4", 63350)
        assertEquals(listOf("172.20.10.9"), store().all().map { it.ip })
        assertEquals(listOf("172.20.10.9"), SavedHosts(ApplicationProvider.getApplicationContext()).all().map { it.ip })
        store().clear()
    }

    @Test
    fun `a store somebody has written nonsense into is an empty list, not a crash`() {
        val prefs = ApplicationProvider.getApplicationContext<Context>()
            .getSharedPreferences(SavedHosts.PREFERENCES, Context.MODE_PRIVATE)
        prefs.edit().putString(SavedHosts.KEY, "this is not json at all").apply()
        assertTrue(store().all().isEmpty())

        prefs.edit().putString(SavedHosts.KEY, """[{"ip": "1.2.3.4"}, 7, null, {"port": 1}]""").apply()
        assertTrue("a store of junk must not invent a host", store().all().isEmpty())

        // And the store is usable again after the junk, which is the point of reading it defensively.
        store().remember(host("10.5.5.5", 63360, "1111", "After the junk", 5L))
        assertEquals(1, store().all().size)
        store().clear()
    }

    @Test
    fun `a saved host names itself as saved, with the code it pairs with`() {
        val row = host("10.0.2.2", 63350, "6767", "(G)i-dle - HWAA", 1L).row()
        assertTrue("the row must say the host is saved: $row", row.contains("saved"))
        assertTrue("the row must name the address: $row", row.contains("10.0.2.2:63350"))
        assertTrue("the row must name the chain: $row", row.contains("(G)i-dle - HWAA"))
        assertTrue("the row must name the code: $row", row.contains("6767"))
    }
}
