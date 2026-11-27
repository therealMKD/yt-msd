// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.protocol).
//
// Moving files over a socket that is already carrying frames: the bytes a host sends after its `SENDING`
// answer, and the bytes a host takes after its `RECEIVING` answer. Nothing is written under a file's real
// name until every byte is down and the checksum matches - the mirror of `recv_file_from_socket`.
package dev.ytmsd.protocol

import java.io.File
import java.io.InputStream
import java.io.OutputStream
import java.security.MessageDigest

object Transfer {

    const val CHUNK_BYTES = 1024 * 1024

    /** The temporary a half file lives in, which is never the name the finished file ends up with. */
    fun temporaryFor(target: File): File = File(target.parentFile, target.name + ".tmp_sync")

    fun sha256Hex(path: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        path.inputStream().use { stream ->
            val buffer = ByteArray(CHUNK_BYTES)
            while (true) {
                val got = stream.read(buffer)
                if (got <= 0) break
                digest.update(buffer, 0, got)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    /**
     * Take [expectedSize] bytes and keep them only if they hash to [expectedSha256].
     *
     * The size and the checksum come from the host's answer, not from the index that named the file: a host
     * is reading its own disk at the moment it answers, and the file can have changed between the two.
     */
    fun receive(stream: InputStream, target: File, expectedSize: Long, expectedSha256: String,
                onProgress: ((Long, Long) -> Unit)? = null): Boolean {
        if (expectedSize <= 0) return false
        if (expectedSha256.length != Protocol.SHA256_HEX_LENGTH) return false
        target.parentFile?.mkdirs()
        val temporary = temporaryFor(target)
        val digest = MessageDigest.getInstance("SHA-256")
        var received = 0L
        temporary.outputStream().use { sink ->
            val buffer = ByteArray(CHUNK_BYTES)
            while (received < expectedSize) {
                val want = minOf(buffer.size.toLong(), expectedSize - received).toInt()
                val got = stream.read(buffer, 0, want)
                if (got <= 0) break
                sink.write(buffer, 0, got)
                digest.update(buffer, 0, got)
                received += got
                onProgress?.invoke(received, expectedSize)
            }
            sink.flush()
        }
        val arrived = digest.digest().joinToString("") { "%02x".format(it) }
        if (received != expectedSize || arrived != expectedSha256.lowercase()) {
            temporary.delete()
            return false
        }
        if (target.exists()) target.delete()
        return temporary.renameTo(target)
    }

    /** Send a file's bytes, and answer with the checksum the bytes that went out add up to. */
    fun send(stream: OutputStream, path: File, onProgress: ((Long, Long) -> Unit)? = null): String {
        val total = path.length()
        val digest = MessageDigest.getInstance("SHA-256")
        var sent = 0L
        path.inputStream().use { source ->
            val buffer = ByteArray(CHUNK_BYTES)
            while (true) {
                val got = source.read(buffer)
                if (got <= 0) break
                stream.write(buffer, 0, got)
                digest.update(buffer, 0, got)
                sent += got
                onProgress?.invoke(sent, total)
            }
            stream.flush()
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    /** The names of the audio files a folder offers, in the order a folder lists them. */
    val AUDIO_SUFFIXES = setOf("mp3", "m4a", "m4b", "aac", "flac", "ogg", "oga", "opus", "wav", "mp4")

    fun audioFiles(folder: File): List<File> =
        (folder.listFiles() ?: emptyArray()).filter {
            it.isFile && it.extension.lowercase() in AUDIO_SUFFIXES
        }.sortedBy { it.name }
}
