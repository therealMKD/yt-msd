// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.protocol).
//
// One connection to one host, speaking the protocol as `docs/sync-protocol.md` describes it - the Kotlin
// copy of `yt_msd.sync.wire.WireClient`. Every method is one exchange, returns what the host answered, and
// leaves the decisions about what to do next to the caller: a phone makes those decisions in its own
// windows, and this moves files and asks questions and answers with what the host said, and nothing else.
//
// `restore`, `restoreRequest` and the push family are not here yet. A phone's M1 is scan, pair, list, pull,
// play; a rebuild and a push are the next features, and they are the ones the protocol document already
// describes and the desktop suite already records.
package dev.ytmsd.protocol

import java.io.File
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.atomic.AtomicLong
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** What one `PULL_FILE` produced: whether it arrived, and what to say about it. */
data class PullResult(val ok: Boolean, val note: String, val filename: String)

class WireClient(
    val hostIp: String,
    val port: Int,
    val syncCode: String,
    val clientIp: String = Lan.localIp(),
    val trace: FrameTrace? = null,
) {

    private var channel: FrameChannel? = null

    /** What the host calls the chain this machine was let into, as `AUTH` answered it. */
    var chainName: String = ""
        private set

    /** The protocol version the host named in its answer to `AUTH`. Null means it named none, which says a
     *  3.0-to-3.5 host - worth knowing before sending that host a command only newer hosts answer. */
    var hostProtocolVersion: Int? = null
        private set

    val isConnected: Boolean get() = channel != null

    // -- the connection -------------------------------------------------------------------

    /** Open the connection. It says nothing; [authenticate] is what says anything. */
    fun connect(): WireClient {
        val socket = Socket()
        socket.connect(InetSocketAddress(hostIp, port), Protocol.CONNECT_TIMEOUT_MS)
        socket.soTimeout = Protocol.SOCKET_TIMEOUT_MS
        channel = FrameChannel(socket)
        return this
    }

    fun close() {
        channel?.close()
        channel = null
    }

    private fun wire(): FrameChannel =
        channel ?: throw IllegalStateException("WireClient is not connected")

    // -- the door, and the questions every exchange starts with ---------------------------

    /**
     * Say which chain this is, and learn what the host calls it.
     *
     * `AUTH` is the first thing a client that wants anything says, and this names the protocol version in the
     * same breath - the only place in the exchange a version is named, and enough for both ends to know what
     * the other speaks before a single file is offered. A host that turns this away answers once and lets the
     * connection go, so the answer is read once and nothing after it is attempted.
     */
    fun authenticate(): JsonObject {
        val frame = FrameWrite.withProtocolVersion(buildJsonObject {
            put("cmd", Protocol.CMD_AUTH)
            put("sync_code", syncCode)
            put("client_ip", clientIp)
        })
        wire().send(frame, trace)
        val answer = wire().receive(trace) ?: FrameWrite.empty
        if (FrameRead.status(answer) == Protocol.STATUS_OK) {
            chainName = FrameRead.text(answer, "chain_name").trim()
            hostProtocolVersion = Protocol.answeredProtocolVersion(answer)
        }
        return answer
    }

    /** Ask for the host's file list. The long timeout is the desktop client's: answering this means hashing
     *  the whole hosted folder, which is a slow drive working, not a dead connection. */
    fun index(timeoutMs: Int = Protocol.INDEX_TIMEOUT_MS): Pair<List<JsonObject>, String> {
        wire().send(buildJsonObject { put("cmd", Protocol.CMD_GET_INDEX) }, trace)
        val answer = withReadTimeout(timeoutMs) { wire().receive(trace) ?: FrameWrite.empty }
        if (FrameRead.status(answer) != Protocol.STATUS_OK) {
            return emptyList<JsonObject>() to
                FrameRead.reason(answer).ifEmpty { "the host did not answer with a file list" }
        }
        return FrameRead.array(answer, "files").map { it as JsonObject } to ""
    }

    /** Keep this connection warm once, and report the answer. */
    fun ping(): JsonObject {
        wire().send(buildJsonObject { put("cmd", Protocol.CMD_PING) }, trace)
        return wire().receive(trace) ?: FrameWrite.empty
    }

    /** Ask the host for its settings, and bring back what it answers. */
    fun fetchConfig(): Triple<Boolean, String, JsonObject?> {
        wire().send(buildJsonObject {
            put("cmd", Protocol.CMD_GET_CONFIG)
            put("sync_code", syncCode)
            put("client_ip", clientIp)
        }, trace)
        val answer = wire().receive(trace) ?: FrameWrite.empty
        if (FrameRead.status(answer) != Protocol.STATUS_CONFIG) {
            val reason = FrameRead.reason(answer).ifEmpty { "the host refused without a reason" }
            return Triple(false, "Settings refused by the host: $reason. Nothing here was changed.", null)
        }
        val config = FrameRead.obj(answer, "config")
        if (config == null || config.isEmpty()) {
            return Triple(false, "The host answered with no settings. Nothing here was changed.", null)
        }
        return Triple(true, "Settings received from $hostIp:$port.", config)
    }

    // -- taking a file, which is the only way a phone gets a track -------------------------

    /**
     * Ask for one file from the host's folder, and write it here.
     *
     * The host answers `SENDING` with the size and the checksum it is about to send, and the bytes follow that
     * answer on the same socket - so the size and checksum that decide whether the file arrived come from the
     * host's answer and not from the index that named the file. A host is reading its own disk at the moment
     * it answers, and a file can have changed between the two.
     *
     * Nothing is written at [target] until every byte is down and the checksum matches: the bytes land in a
     * `.tmp_sync` beside it, and only a file that hashes to what was promised takes the name. A phone that
     * ends up with a half file with a track's name on it is a phone whose library lies to it.
     */
    fun pull(filename: String, target: File, onProgress: ((Long, Long) -> Unit)? = null): PullResult {
        wire().send(buildJsonObject {
            put("cmd", Protocol.CMD_PULL_FILE)
            put("filename", filename)
        }, trace)
        val answer = wire().receive(trace) ?: FrameWrite.empty
        if (FrameRead.status(answer) != Protocol.STATUS_SENDING) {
            return PullResult(false,
                FrameRead.reason(answer).ifEmpty { "the host would not send $filename" }, filename)
        }
        val size = FrameRead.long(answer, "filesize", 0L)
        val promised = FrameRead.text(answer, "sha256")
        if (size <= 0 || promised.length != Protocol.SHA256_HEX_LENGTH) {
            return PullResult(false, "the host named no size or no checksum for $filename", filename)
        }
        target.parentFile?.mkdirs()
        val arrived = Transfer.receive(wire().stream(), target, size, promised, onProgress)
        trace?.recordBytes(
            "recv_bytes", filename,
            if (target.exists()) target.length() else -1L,
            if (target.exists()) Transfer.sha256Hex(target) else "",
        )
        return PullResult(arrived, if (arrived) "$filename received" else "$filename did not arrive whole", filename)
    }

    // -- keeping a connection warm while a person reads a code off a screen ----------------

    /**
     * Run [block] with this connection kept warm.
     *
     * A host reads the next command with a 30-second timeout, so a client that parks to show a box - a phone
     * waiting for somebody to read a four-character code off another screen - would find its connection
     * closed and its exchange reported as a failure before anybody had answered. Nothing else may touch the
     * socket while this runs: a `PING` sent in the middle of a file transfer is bytes the host reads as its
     * next frame.
     */
    fun <T> keepalive(block: () -> T, intervalMs: Int = Protocol.CONFIRM_PING_INTERVAL_MS): T {
        val keeper = Keepalive(wire(), intervalMs, trace)
        keeper.start()
        try {
            return block()
        } finally {
            keeper.stop()
        }
    }

    /** A read that is allowed to take longer than usual - a whole library hash, a rebuild's shortlist. */
    private fun <T> withReadTimeout(timeoutMs: Int, block: () -> T): T {
        val socket = wire().socket
        val previous = socket.soTimeout
        socket.soTimeout = timeoutMs
        try {
            return block()
        } finally {
            socket.soTimeout = previous
        }
    }
}

/**
 * Pings a host while the machine on the other end of a socket has stopped to ask a question.
 *
 * It sleeps first and sends second on purpose: a question answered at once stops this before it has sent
 * anything, which is what keeps an ordinary exchange free of extra frames. It stops reading as soon as the
 * host stops answering, because writing on into a connection nobody is reading is a way to make a lost
 * connection look like a slow one. [stop] waits for the send/read pair in flight to finish - stopping short
 * leaves a `PONG` unread on a socket its exchange is about to read its next answer from.
 */
class Keepalive(
    private val channel: FrameChannel,
    private val intervalMs: Int = Protocol.CONFIRM_PING_INTERVAL_MS,
    private val trace: FrameTrace? = null,
) {

    @Volatile private var running = false
    private var thread: Thread? = null
    private val sentCount = AtomicLong()

    /** The pings that went out. A keepalive that ran and sent nothing is a keepalive that only looks like
     *  it is working, which is what a check reads. */
    val sent: Long get() = sentCount.get()

    fun start() {
        if (running) return
        running = true
        thread = Thread {
            while (running) {
                try {
                    Thread.sleep(intervalMs.toLong())
                } catch (_: InterruptedException) {
                    break
                }
                if (!running) break
                try {
                    channel.send(buildJsonObject { put("cmd", Protocol.CMD_PING) }, trace)
                    sentCount.incrementAndGet()
                    channel.receive(trace)
                } catch (_: Exception) {
                    break
                }
            }
        }.apply { isDaemon = true; start() }
    }

    fun stop() {
        running = false
        thread?.join(intervalMs + 1_000L)
        thread = null
    }
}

