// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.protocol).
//
// The words both ends of a sync chain speak - the Kotlin copy of `GUI Source Code/yt_msd/sync/protocol.py`.
// `ProtocolNamesTest` compares every name here with the Python module it mirrors, so the two copies cannot
// drift in silence. `docs/sync-protocol.md` is the prose over both.
package dev.ytmsd.protocol

import kotlinx.serialization.json.JsonObject

/** The version, the commands, the statuses, and the timeouts, as a phone needs them. */
object Protocol {

    // One number, said at the door, and no negotiation: a client that names no version is an old
    // (3.0-to-3.5) client and must keep working, and a host that names no version in its answer is one of
    // those hosts. `requestedProtocolVersion` and `answeredProtocolVersion` are the two reads, and they are
    // deliberately not the same read - see the Python module for why.
    const val VERSION = 1

    /** The versions this machine answers: dialects somebody wrote, not a range. */
    val supportedVersions: Set<Int> = setOf(VERSION)

    const val VERSION_KEY = "protocol_version"

    /** What a host calls itself to a stranger. A scan finds this word or nothing at all. */
    const val APP_NAME = "yt-msd"

    const val SYNC_CODE_LENGTH = 4

    const val SHA256_HEX_LENGTH = 64

    // -- commands a client sends ---------------------------------------------------------------

    const val CMD_HELLO = "HELLO"
    const val CMD_AUTH = "AUTH"
    const val CMD_GET_INDEX = "GET_INDEX"
    const val CMD_PULL_FILE = "PULL_FILE"
    const val CMD_PING = "PING"
    const val CMD_GET_CONFIG = "GET_CONFIG"
    const val CMD_RESTORE_REQUEST = "RESTORE_REQUEST"
    const val CMD_RESTORE_CONFIRM = "RESTORE_CONFIRM"
    const val CMD_RESTORE_CANCEL = "RESTORE_CANCEL"
    const val CMD_PUSH_REQUEST = "PUSH_REQUEST"
    const val CMD_PUSH_START = "PUSH_START"
    const val CMD_PUSH_CANCEL = "PUSH_CANCEL"
    const val CMD_PUSH_INDEX = "PUSH_INDEX"
    const val CMD_PUSH_FILE = "PUSH_FILE"
    const val CMD_PUSH_DONE = "PUSH_DONE"

    val clientCommands: Set<String> = setOf(
        CMD_HELLO, CMD_AUTH, CMD_GET_INDEX, CMD_PULL_FILE, CMD_PING, CMD_GET_CONFIG,
        CMD_RESTORE_REQUEST, CMD_RESTORE_CONFIRM, CMD_RESTORE_CANCEL,
        CMD_PUSH_REQUEST, CMD_PUSH_START, CMD_PUSH_CANCEL, CMD_PUSH_INDEX, CMD_PUSH_FILE, CMD_PUSH_DONE,
    )

    // -- statuses a host answers with ----------------------------------------------------------

    const val STATUS_OK = "OK"
    const val STATUS_ERROR = "ERROR"
    const val STATUS_SENDING = "SENDING"
    const val STATUS_PONG = "PONG"
    const val STATUS_CONFIG = "CONFIG"
    const val STATUS_CANCELLED = "CANCELLED"
    const val STATUS_WAITING_FOR_CODE = "WAITING_FOR_CODE"
    const val STATUS_CODE_ACCEPTED = "CODE_ACCEPTED"
    const val STATUS_RESTORING = "RESTORING"
    const val STATUS_RECEIVING = "RECEIVING"
    const val STATUS_SYNCED = "SYNCED"
    const val STATUS_WAITING_FOR_PUSH_CODE = "WAITING_FOR_PUSH_CODE"
    const val STATUS_PUSH_ALLOWED = "PUSH_ALLOWED"
    const val STATUS_PUSH_ACCEPTED = "PUSH_ACCEPTED"
    const val STATUS_PUSHING = "PUSHING"
    const val STATUS_RESTORE_CLOSED = "RESTORE_CLOSED"
    const val STATUS_PUSH_CLOSED = "PUSH_CLOSED"

    val hostStatuses: Set<String> = setOf(
        STATUS_OK, STATUS_ERROR, STATUS_SENDING, STATUS_PONG, STATUS_CONFIG, STATUS_CANCELLED,
        STATUS_WAITING_FOR_CODE, STATUS_CODE_ACCEPTED, STATUS_RESTORING, STATUS_RECEIVING,
        STATUS_SYNCED, STATUS_WAITING_FOR_PUSH_CODE, STATUS_PUSH_ALLOWED, STATUS_PUSH_ACCEPTED,
        STATUS_PUSHING, STATUS_RESTORE_CLOSED, STATUS_PUSH_CLOSED,
    )

    // -- the UDP discovery frames, which carry a "type" and not a "cmd" ------------------------

    const val TYPE_BEACON = "BEACON"
    const val TYPE_PROBE = "PROBE"
    const val TYPE_PROBE_ALL = "PROBE_ALL"
    const val TYPE_PROBE_REPLY = "PROBE_REPLY"
    const val TYPE_CHAIN_UPDATED = "CHAIN_UPDATED"
    const val TYPE_CHAIN_SYNC_REQUEST = "CHAIN_SYNC_REQUEST"

    val discoveryTypes: Set<String> = setOf(
        TYPE_BEACON, TYPE_PROBE, TYPE_PROBE_ALL, TYPE_PROBE_REPLY, TYPE_CHAIN_UPDATED,
        TYPE_CHAIN_SYNC_REQUEST,
    )

    // -- shapes both ends rely on --------------------------------------------------------------

    val indexEntryKeys: List<String> = listOf("name", "size", "mtime", "sha256", "artist", "title")

    val pushIndexEntryKeys: List<String> = listOf("name", "size", "mtime", "sha256")

    // -- the numbers a connection is run with --------------------------------------------------
    //
    // These are `yt_msd.sync.lan`'s, in milliseconds. A phone that gave up on a library hash after twelve
    // seconds is a phone that cannot use a big library; a phone that waits forever on a code nobody is
    // going to read is a phone sitting on a dead exchange.

    const val SYNC_PORT_START = 63350
    const val SYNC_PORT_END = 63370
    const val UDP_BEACON_PORT = 63350

    const val CONNECT_TIMEOUT_MS = 3_000
    const val SOCKET_TIMEOUT_MS = 12_000
    const val INDEX_TIMEOUT_MS = 25_000
    const val HANDSHAKE_TIMEOUT_MS = 300_000
    const val CONFIRM_PING_INTERVAL_MS = 10_000

    const val SCAN_CONNECT_TIMEOUT_MS = 350
    const val SCAN_READ_TIMEOUT_MS = 1_500
    const val SCAN_MAX_CONCURRENCY = 128
    const val SCAN_BUDGET_MS = 14_000L
    const val SCAN_MAX_NETWORKS = 4
    const val SCAN_MAX_TARGETS = 1024

    // -- the version rules ---------------------------------------------------------------------

    /**
     * The version the machine on the other end says it speaks. A missing key, a boolean, text that is not a
     * number and a number that is not a version all answer [VERSION]: naming no version is not announcing no
     * protocol, it is announcing that the machine is old, and old is the case that has to keep working.
     */
    fun requestedProtocolVersion(message: JsonObject?): Int {
        val raw = message?.get(VERSION_KEY) ?: return VERSION
        val value = NumberRead.whole(raw) ?: return VERSION
        return if (value > 0) value else VERSION
    }

    /** Will this machine answer a client that asked for [requested]? */
    fun protocolVersionAccepted(requested: Int): Boolean = requested in supportedVersions

    /** What to tell a machine this program will not speak with - and which end needs the update. */
    fun versionRefusal(requested: Int): String {
        val wanted = if (requested > 0) requested else VERSION
        if (wanted > VERSION) {
            return "This host speaks sync protocol version $VERSION; it cannot answer version $wanted. " +
                "Update yt-msd on this machine."
        }
        return "This host speaks sync protocol version $VERSION; it no longer answers version $wanted. " +
            "Update yt-msd on the machine that asked."
    }

    /** Nothing at all if this machine should answer, or the sentence telling it not to. */
    fun versionRefusalFor(message: JsonObject?): String? {
        val requested = requestedProtocolVersion(message)
        return if (protocolVersionAccepted(requested)) null else versionRefusal(requested)
    }

    /**
     * The version a host named in its answer, or null when it named none - which says a 3.0-to-3.5 host,
     * worth knowing before sending that host a command only newer hosts answer. Reading the absence of a
     * fact as the fact itself is not what this does.
     */
    fun answeredProtocolVersion(message: JsonObject?): Int? {
        val raw = message?.get(VERSION_KEY) ?: return null
        val value = NumberRead.whole(raw) ?: return null
        return if (value > 0) value else null
    }

    /** Is this string shaped like a sync code? Four digits, as text, never as a number. */
    fun isSyncCode(text: String): Boolean = text.length == SYNC_CODE_LENGTH && text.all { it.isDigit() }
}

