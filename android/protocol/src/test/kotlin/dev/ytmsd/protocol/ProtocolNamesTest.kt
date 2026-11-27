// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.protocol).
//
// The names. Every command, status, discovery type and version rule in this Kotlin copy is compared with
// the Python module it mirrors - `GUI Source Code/yt_msd/sync/protocol.py` - read off the file, on this
// machine, on every run. Two copies of a protocol drift by one word at a time, and a phone that types a word
// a host has renamed is a phone that fails on a network it cannot see.
package dev.ytmsd.protocol

import dev.ytmsd.protocol.testing.PhoneSession
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

class ProtocolNamesTest {

    /** Every `NAME = "value"` the Python module assigns at the top level. */
    private fun pythonAssignments(): Map<String, String> {
        val source = PhoneSession.pythonProtocolSource()
        assumeTrue("this checkout does not have the Python protocol module next to the fixture", source != null)
        val found = mutableMapOf<String, String>()
        source!!.readLines().forEach { line ->
            val match = Regex("^([A-Z][A-Z0-9_]+)\\s*=\\s*\"([^\"]*)\"").find(line.trim())
            if (match != null) found[match.groups[1]!!.value] = match.groups[2]!!.value
        }
        return found
    }

    @Test
    fun `every command a client sends is a command this client knows`() {
        val python = pythonAssignments().filter { (name, _) -> name.startsWith("CMD_") }
        assertTrue("the Python module names no commands - its shape has changed", python.isNotEmpty())
        python.forEach { (name, value) ->
            assertTrue("$name ($value) is not in the phone's command list", Protocol.clientCommands.contains(value))
        }
        assertEquals(
            "the phone knows ${Protocol.clientCommands.size} commands and the host sends ${python.size}",
            python.size,
            Protocol.clientCommands.size,
        )
    }

    @Test
    fun `every status a host answers is a status this client reads`() {
        val python = pythonAssignments().filter { (name, _) -> name.startsWith("STATUS_") }
        assertTrue("the Python module names no statuses - its shape has changed", python.isNotEmpty())
        python.forEach { (name, value) ->
            assertTrue("$name ($value) is not in the phone's status list", Protocol.hostStatuses.contains(value))
        }
        assertEquals(python.size, Protocol.hostStatuses.size)
    }

    @Test
    fun `every discovery frame type is a type this client can name`() {
        val python = pythonAssignments().filter { (name, _) -> name.startsWith("TYPE_") }
        python.forEach { (name, value) ->
            assertTrue("$name ($value) is not in the phone's discovery types", Protocol.discoveryTypes.contains(value))
        }
        assertEquals(python.size, Protocol.discoveryTypes.size)
    }

    @Test
    fun `the version, the key it travels under, the app's own name, and the two lengths agree`() {
        val python = pythonAssignments()
        assertEquals(Protocol.APP_NAME, python["APP_NAME"])
        assertEquals(Protocol.VERSION_KEY, python["PROTOCOL_VERSION_KEY"])

        val numbers = mutableMapOf<String, String>()
        PhoneSession.pythonProtocolSource()!!.readLines().forEach { line ->
            val match = Regex("^([A-Z][A-Z0-9_]+)\\s*=\\s*([0-9]+)").find(line.trim())
            if (match != null) numbers[match.groups[1]!!.value] = match.groups[2]!!.value
        }
        assertEquals(Protocol.VERSION.toLong(), numbers["PROTOCOL_VERSION"]?.toLong())
        assertEquals(Protocol.SYNC_CODE_LENGTH.toLong(), numbers["SYNC_CODE_LENGTH"]?.toLong())
        assertEquals(Protocol.SHA256_HEX_LENGTH.toLong(), numbers["SHA256_HEX_LENGTH"]?.toLong())
    }

    @Test
    fun `the version rules answer the way the host's rules answer`() {
        fun frame(version: Any): kotlinx.serialization.json.JsonObject =
            kotlinx.serialization.json.buildJsonObject { put(Protocol.VERSION_KEY, version.toString()) }

        // A client that names no version is an old client, and old answers this version.
        assertEquals(Protocol.VERSION, Protocol.requestedProtocolVersion(null))
        assertEquals(Protocol.VERSION, Protocol.requestedProtocolVersion(kotlinx.serialization.json.buildJsonObject {
            put("cmd", Protocol.CMD_AUTH)
        }))
        assertEquals(1, Protocol.requestedProtocolVersion(frame(1)))
        assertEquals(2, Protocol.requestedProtocolVersion(frame(2)))
        assertEquals(Protocol.VERSION, Protocol.requestedProtocolVersion(frame("not a number")))
        assertEquals(Protocol.VERSION, Protocol.requestedProtocolVersion(frame(0)))

        assertTrue(Protocol.protocolVersionAccepted(1))
        assertTrue(!Protocol.protocolVersionAccepted(2))
        assertTrue(!Protocol.protocolVersionAccepted(0))

        // The refusal says which of the two machines needs the update.
        assertTrue(Protocol.versionRefusal(2).contains("Update yt-msd on this machine"))
        assertTrue(Protocol.versionRefusal(0).contains("Update yt-msd on the machine that asked"))
        assertEquals(null, Protocol.versionRefusalFor(frame(1)))
        assertTrue((Protocol.versionRefusalFor(frame(2)) ?: "").isNotEmpty())

        // A host that named no version is a 3.0-to-3.5 host. Reading the absence of that fact as the fact
        // itself - "no version means version 1" - is the mistake the Python module warns about, and this
        // copy makes it nowhere.
        assertEquals(null, Protocol.answeredProtocolVersion(null))
        assertEquals(null, Protocol.answeredProtocolVersion(kotlinx.serialization.json.buildJsonObject {
            put("cmd", Protocol.CMD_AUTH)
        }))
        assertEquals(null, Protocol.answeredProtocolVersion(frame(true)))
        assertEquals(1, Protocol.answeredProtocolVersion(frame(1)))
    }
}
