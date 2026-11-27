// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.protocol).
//
// The wire: a frame is a 4-byte big-endian length and then that many bytes of UTF-8 JSON, and a file is
// the raw bytes that follow a host's `SENDING` answer on the same socket. This is `send_json_msg`,
// `recv_json_msg`, `stream_file_to_socket` and `recv_file_from_socket` in `yt_msd.sync.transfer`, put in
// the language the phone is written in.
package dev.ytmsd.protocol

import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.EOFException
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.Socket
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicLong
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.put


/** The bytes above one frame. */
object Frames {

    /** A frame this big is not a frame; it is a machine that has lost the plot. A host reads a length it
     *  was handed without question, so the guard is on the reader that has to survive being lied to. */
    const val MAX_FRAME_BYTES = 32 * 1024 * 1024

    fun encode(frame: JsonElement): ByteArray = frame.toString().toByteArray(Charsets.UTF_8)

    fun write(out: OutputStream, frame: JsonElement) {
        val payload = encode(frame)
        out.write(header(payload.size))
        out.write(payload)
        out.flush()
    }

    /** The length header, big-endian, as `struct.pack('!I', ...)` writes it. */
    fun header(length: Int): ByteArray = byteArrayOf(
        (length ushr 24).toByte(), (length ushr 16).toByte(), (length ushr 8).toByte(), length.toByte()
    )

    fun headerLength(header: ByteArray): Int =
        ((header[0].toInt() and 0xFF) shl 24) or ((header[1].toInt() and 0xFF) shl 16) or
            ((header[2].toInt() and 0xFF) shl 8) or (header[3].toInt() and 0xFF)

    /** Read one frame. Nothing at all - null - is what a clean close looks like. */
    fun read(input: InputStream): JsonObject? {
        val header = readAll(input, 4) ?: return null
        val length = headerLength(header)
        if (length <= 0 || length > MAX_FRAME_BYTES) {
            throw IOException("frame of $length bytes is not a frame")
        }
        val payload = readAll(input, length) ?: throw IOException("frame ended after $length promised bytes")
        return PhoneJson.parseToJsonElement(String(payload, Charsets.UTF_8)).let {
            it as? JsonObject ?: throw IOException("a frame arrived that is not a JSON object")
        }
    }

    fun readAll(input: InputStream, wanted: Int): ByteArray? {
        val buffer = ByteArray(wanted)
        var filled = 0
        while (filled < wanted) {
            val got = input.read(buffer, filled, wanted - filled)
            if (got < 0) return if (filled == 0) null else throw EOFException("connection ended mid-frame")
            filled += got
        }
        return buffer
    }
}

/** One connection, framed. Every frame this client speaks goes through here and gets written down. */
class FrameChannel(val socket: Socket) {

    private val input = DataInputStream(BufferedInputStream(socket.getInputStream()))
    private val output = DataOutputStream(BufferedOutputStream(socket.getOutputStream()))

    fun send(frame: JsonObject, trace: FrameTrace? = null) {
        trace?.record("send", frame)
        Frames.write(output, frame)
    }

    /** The next frame, or null when the other end has closed. */
    fun receive(trace: FrameTrace? = null): JsonObject? = Frames.read(input).also { trace?.record("recv", it) }

    /** The bytes a host sends after its `SENDING` answer, taken straight off this socket. */
    fun stream(): InputStream = input

    fun sink(): OutputStream = output

    fun close() {
        try {
            socket.close()
        } catch (_: IOException) {
            // A socket that is already closed is a socket that is already closed.
        }
    }
}

/**
 * Every frame of one exchange, written down in the order it went and came back.
 *
 * This is what makes a phone testable before the frames it speaks are ever compared: the desktop suite
 * records a whole session into `GUI Test Suite/fixtures/protocol/phone_session.json`, and the acceptance
 * check runs a session here and compares the two, frame for frame. `send` and `recv` are frames on the
 * socket; `send_bytes` and `recv_bytes` are the file bodies that ride between frames, recorded by their
 * size and checksum because the bytes themselves are the library and not the protocol.
 */
class FrameTrace {

    private val records = java.util.concurrent.CopyOnWriteArrayList<JsonObject>()
    private val pings = AtomicLong()

    fun record(direction: String, frame: JsonElement?) {
        val entry = kotlinx.serialization.json.buildJsonObject {
            put("dir", direction)
            put("frame", frame ?: FrameWrite.empty)
        }
        records.add(entry)
    }

    fun recordBytes(direction: String, filename: String, size: Long, sha256: String) {
        val entry = kotlinx.serialization.json.buildJsonObject {
            put("dir", direction)
            put("frame", kotlinx.serialization.json.buildJsonObject {
                put("filename", filename)
                put("size", size)
                put("sha256", sha256)
            })
        }
        records.add(entry)
    }

    fun notePing() = pings.incrementAndGet()

    fun pingCount(): Long = pings.get()

    fun frames(): List<JsonObject> = records.toList()

    fun size(): Int = records.size
}
