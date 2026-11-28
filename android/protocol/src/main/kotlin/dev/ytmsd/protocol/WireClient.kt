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
import java.net.SocketTimeoutException
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
    private var warmer: Keepalive? = null
    private var warmPingsDone = 0L

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
        stopWarm()
        channel?.close()
        channel = null
    }

    /**
     * Keep this connection warm while a person is looking at a screen.
     *
     * A host reads the next command with a 30-second timeout and closes the connection when nothing arrives -
     * `host.py`'s own loop, `recv_json_msg(sock, timeout=30.0)` and a `break`. A phone that has listed 458
     * files and left them on screen while somebody reads them is exactly that, every time, and the phone
     * cannot see the connection go: the next ask writes into a socket nobody is reading. The protocol's answer
     * is a `PING` every 10 seconds, and this runs the same [Keepalive] the desktop runs.
     *
     * It is not running during a file transfer and must not be: a `PING` in the middle of a transfer is bytes
     * the host reads as its next frame. [stopWarm] is what puts it away before an ask, and it joins the thread
     * so no `PONG` is left unread on a socket about to read its next answer.
     */
    fun startWarm(intervalMs: Int = Protocol.CONFIRM_PING_INTERVAL_MS) {
        val wire = channel ?: return
        if (warmer != null) return
        Keepalive(wire, intervalMs, trace).also { warmer = it }.start()
    }

    /** Put the pings away, and leave the socket clean for the next exchange to read its answer from. */
    fun stopWarm() {
        val warmer = warmer ?: return
        warmPingsDone += warmer.sent
        warmer.stop()
        this.warmer = null
    }

    /** The pings this client has sent to keep itself warm. A warmer that sent none is a warmer that only
     *  looks like it is working, which is what a check reads. */
    val warmPings: Long get() = warmPingsDone + (warmer?.sent ?: 0L)

    private fun wire(): FrameChannel =
        channel ?: throw IllegalStateException("WireClient is not connected")

    /**
     * The next answer, with the noticing that goes with it.
     *
     * A frame that is nothing at all is a host that has closed this connection - the clean-close shape
     * `Frames.read` returns null for, which is exactly what a phone gets when it asks a host 40 seconds after
     * the list landed on its screen and the host's 30-second command read hung up. A client that kept that
     * connection would spend its next ask writing into a socket nobody is reading, and report the host as
     * refusing a file it never saw. So the connection is put away here, and every ask after it says the true
     * thing: there is no connection to ask with.
     */
    private fun answer(): JsonObject {
        val frame = try {
            wire().receive(trace)
        } catch (_: SocketTimeoutException) {
            // A host that has not answered inside the time allowed is a host that is still there - a slow
            // drive hashing a library, a chain being rebuilt - and this is the one case a client keeps its
            // connection for. The desktop client reads a timeout as no answer and carries on; a phone that
            // hung up on a host for being slow would have to pair with it again for no reason.
            return FrameWrite.empty
        } catch (_: Exception) {
            // A read the socket refuses - an aborted connection, a reset - is the same host that is gone,
            // told a different way.
            close()
            return FrameWrite.empty
        }
        if (frame == null) {
            close()
            return FrameWrite.empty
        }
        return frame
    }

    /**
     * A frame going out, with the noticing that goes with it.
     *
     * The other half of the same fact: a write the socket refuses - a connection the host aborted, a host that
     * hung up on a phone that stopped to read a screen - is a host that is not there. A client that kept this
     * connection would go on writing into a socket nobody is reading, and would say every time that the host
     * refused a file it never saw. So the connection is put away and the complaint goes back up to be said.
     */
    private fun speak(frame: JsonObject) {
        try {
            wire().send(frame, trace)
        } catch (problem: Exception) {
            close()
            throw problem
        }
    }

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
        speak(frame)
        val answer = answer()
        if (FrameRead.status(answer) == Protocol.STATUS_OK) {
            chainName = FrameRead.text(answer, "chain_name").trim()
            hostProtocolVersion = Protocol.answeredProtocolVersion(answer)
        }
        return answer
    }

    /** Ask for the host's file list. The long timeout is the desktop client's: answering this means hashing
     *  the whole hosted folder, which is a slow drive working, not a dead connection. */
    fun index(timeoutMs: Int = Protocol.INDEX_TIMEOUT_MS): Pair<List<JsonObject>, String> {
        speak(buildJsonObject { put("cmd", Protocol.CMD_GET_INDEX) })
        val answer = withReadTimeout(timeoutMs) { answer() }
        if (FrameRead.status(answer) != Protocol.STATUS_OK) {
            return emptyList<JsonObject>() to
                FrameRead.reason(answer).ifEmpty { "the host did not answer with a file list" }
        }
        return FrameRead.array(answer, "files").map { it as JsonObject } to ""
    }

    /** Keep this connection warm once, and report the answer. */
    fun ping(): JsonObject {
        speak(buildJsonObject { put("cmd", Protocol.CMD_PING) })
        return answer()
    }

    /** Ask the host for its settings, and bring back what it answers. */
    fun fetchConfig(): Triple<Boolean, String, JsonObject?> {
        speak(buildJsonObject {
            put("cmd", Protocol.CMD_GET_CONFIG)
            put("sync_code", syncCode)
            put("client_ip", clientIp)
        })
        val answer = answer()
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
        speak(buildJsonObject {
            put("cmd", Protocol.CMD_PULL_FILE)
            put("filename", filename)
        })
        val answer = answer()
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

