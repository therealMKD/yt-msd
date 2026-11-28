// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.protocol, test fixtures).
//
// A host that answers out of the recording and reads what a client asks for. It walks the recorded frames in
// order: where the recording says a client sends, it reads a frame and compares it with what was recorded;
// where the recording says the host answers, it answers; where the recording says bytes arrived, it sends
// those bytes. A client that asks for the wrong thing is caught by [mismatches], which names the frame and
// the difference.
package dev.ytmsd.protocol.testing

import dev.ytmsd.protocol.FrameChannel
import dev.ytmsd.protocol.FrameRead
import dev.ytmsd.protocol.JsonCompat
import dev.ytmsd.protocol.Protocol
import dev.ytmsd.protocol.Transfer
import java.io.File
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.security.MessageDigest
import java.util.concurrent.CopyOnWriteArrayList
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class ScriptedHost(private val session: PhoneSession, private val library: File) {

    private val server = ServerSocket(0, 20, InetAddress.getByName("127.0.0.1"))

    val port: Int get() = server.localPort

    /** Every frame a client asked for, in the order it asked. */
    val asked = CopyOnWriteArrayList<JsonObject>()

    /** The frames a client spoke that are not the frames the recording says it speaks. */
    val mismatches = CopyOnWriteArrayList<String>()

    /** The bytes a client sent between frames, hashed - what a push test reads. */
    val arrivals = CopyOnWriteArrayList<Pair<String, Long>>()

    /** The `PING`s this host answered. A phone that keeps a host warm is a phone that sends these. */
    val pingsAnswered = java.util.concurrent.atomic.AtomicInteger()

    var servedConnections = 0
        private set

    @Volatile private var running = true
    private var thread: Thread? = null
    private var served: FrameChannel? = null

    /**
     * Hang up on the client this host is serving, the way the real host hangs up when its 30-second command
     * read finds nothing there. A test uses this to stand in for the gap between a list landing on a phone's
     * screen and a person pressing Take half a minute later.
     */
    fun hangUp() {
        served?.close()
    }

    fun start() {
        thread = Thread {
            while (running) {
                val socket = try {
                    server.accept()
                } catch (_: Exception) {
                    // The server was closed from the outside: this host has finished serving.
                    break
                }
                servedConnections++
                try {
                    serve(socket)
                } catch (_: Exception) {
                    // A client that hung up mid-exchange is a client whose test fails on the frame count.
                }
            }
        }.apply { isDaemon = true; start() }
    }

    private fun serve(socket: Socket) {
        val channel = FrameChannel(socket)
        served = channel
        val records = session.frames
        var position = 0
        while (position < records.size) {
            val record = records[position]
            when (FrameRead.text(record, "dir")) {
                "send" -> {
                    val wanted = FrameRead.obj(record, "frame") ?: return
                    val spoken = channel.receive() ?: return
                    asked.add(spoken)
                    if (FrameRead.text(spoken, "cmd") == Protocol.CMD_HELLO) {
                        // A `HELLO` is not part of the recorded session - a host answers it out of what it
                        // knows about itself, and a phone that is scanning asks one before it says anything.
                        // So it is answered and the record is left where it is: the frame the client has to
                        // speak next is still the frame this record names.
                        channel.send(helloAnswer())
                    } else if (FrameRead.text(spoken, "cmd") == Protocol.CMD_PING) {
                        // A `PING` is not a step of the session either. It is what a client sends to keep a
                        // host's 30-second command read from timing out while a person reads a screen, and a
                        // real host answers `PONG` and carries on with whatever it was doing - so this answers
                        // `PONG`, counts it, and leaves the record where it stands.
                        pingsAnswered.incrementAndGet()
                        channel.send(buildJsonObject { put("status", Protocol.STATUS_PONG) })
                    } else {
                        if (!JsonCompat.equal(wanted, spoken)) {
                            mismatches.add(
                                "the client said ${JsonCompat.describe(spoken)} where the recording has " +
                                    JsonCompat.describe(wanted)
                            )
                        }
                        position++
                    }
                }
                "recv" -> {
                    val frame = FrameRead.obj(record, "frame") ?: return
                    channel.send(frame)
                    // A host that answers `SENDING` sends the file next, on the same socket - every time,
                    // which is what PW18 proves on the Python side. The recording traces a body only for the
                    // pulls the desktop probe chose to hash, so a `SENDING` answer with no body recorded
                    // after it is answered here the way the real host answers it.
                    if (FrameRead.status(frame) == Protocol.STATUS_SENDING) {
                        val next = records.getOrNull(position + 1)
                        val bodyAlreadyRecorded = next != null && FrameRead.text(next, "dir") == "recv_bytes"
                        if (!bodyAlreadyRecorded) {
                            val file = File(library, FrameRead.text(frame, "filename"))
                            if (file.exists()) Transfer.send(channel.sink(), file)
                        }
                    }
                    position++
                }
                "recv_bytes" -> {
                    val file = File(library, FrameRead.text(FrameRead.obj(record, "frame")!!, "filename"))
                    if (file.exists()) Transfer.send(channel.sink(), file)
                    position++
                }
                "send_bytes" -> {
                    val size = FrameRead.long(FrameRead.obj(record, "frame")!!, "size", 0L)
                    if (size > 0) arrivals.add(takeBytes(channel, size))
                    position++
                }
            }
        }
        channel.close()
    }

    /**
     * What a host answers a `HELLO` with, in the shape [dev.ytmsd.protocol.Lan.probeHost] reads and
     * `yt_msd.sync.host.hello_reply` writes: `status`, `app`, `host_name`, `port`, the protocol version, and
     * the chains it hosts as `{sync_code, name, visible}`. A recording of a session starts at `AUTH` - a
     * `HELLO` is what happens before a session - so the chains and the version are composed from the `AUTH`
     * answer the recording does carry.
     */
    private fun helloAnswer(): JsonObject {
        val authAnswer = session.framesOf("recv")
            .firstOrNull { FrameRead.command(it) == Protocol.CMD_AUTH }
            ?: session.framesOf("recv").firstOrNull()
        val chain = (authAnswer?.let { FrameRead.text(it, "chain_name") } ?: "").ifEmpty { session.chain }
        val version = authAnswer?.let { Protocol.answeredProtocolVersion(it) } ?: Protocol.VERSION
        return buildJsonObject {
            put("status", Protocol.STATUS_OK)
            put("app", Protocol.APP_NAME)
            put("host_name", "scripted-host")
            put("port", port)
            put(Protocol.VERSION_KEY, version)
            put(
                "chains",
                JsonArray(listOf(buildJsonObject {
                    put("sync_code", session.chain)
                    put("name", chain)
                    put("visible", true)
                })),
            )
        }
    }

    private fun takeBytes(channel: FrameChannel, size: Long): Pair<String, Long> {
        val digest = MessageDigest.getInstance("SHA-256")
        var taken = 0L
        while (taken < size) {
            val byte = channel.stream().read()
            if (byte < 0) break
            digest.update(byte.toByte())
            taken++
        }
        return digest.digest().joinToString("") { "%02x".format(it) } to taken
    }

    fun stop() {
        running = false
        try {
            server.close()
        } catch (_: Exception) {
            // A server that is already closed is a server that is already stopped.
        }
        thread?.interrupt()
    }
}
